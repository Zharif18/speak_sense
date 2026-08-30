from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WearableReading, SpeakingSession, WearableConnection
from app.schemas import (
    WearableReadingIn,
    WearableReadingOut,
    WearableConnectionOut,
    WearableDisconnectRequest,
)
from app.services.wearable_adapter import (
    compute_stress_index,
    compute_weighted_stress_index,
    fetch_baseline_hr,
    NormalizedReading,
)

router = APIRouter()

# Buffer around a session's [created_at, created_at + duration] window when
# claiming untagged readings -- the watch's clock and the server's clock
# are never perfectly in sync.
CLAIM_WINDOW_BUFFER_SECONDS = 45

# A connection with no synced reading in this long shows as "connected, but
# stale" in the UI rather than "connected" -- catches a bridge app that's
# quietly stopped syncing (auto-sync turned off, phone off, etc).
STALE_AFTER_MINUTES = 60


@router.post("/ingest", response_model=WearableReadingOut)
def ingest_reading(payload: WearableReadingIn, db: Session = Depends(get_db)):
    """
    Called by the client (Android Health Connect bridge, or a NoiseFit sync
    job) with already-normalized readings. This is the single entry point
    every adapter funnels into, which is what keeps SpeakSense device-agnostic.

    Also upserts WearableConnection: the first successful ingest for a user
    marks them "connected" and every ingest after that bumps last_synced_at,
    so the UI's connection status reflects real data flow rather than a
    one-time click.
    """
    reading = WearableReading(**payload.model_dump())
    db.add(reading)

    conn = db.query(WearableConnection).filter(WearableConnection.user_id == payload.user_id).first()
    now = datetime.utcnow()
    if conn is None:
        conn = WearableConnection(
            user_id=payload.user_id,
            device_type=payload.device_type,
            connected=True,
            connected_at=now,
            last_synced_at=now,
        )
        db.add(conn)
    else:
        conn.device_type = payload.device_type
        conn.last_synced_at = now
        if not conn.connected:
            # A reading arrived after an explicit disconnect -- the bridge
            # app must still be auto-syncing. Reconnect rather than silently
            # dropping the data; the UI/README tells users to also pause
            # auto-sync on the phone if they want a disconnect to "stick".
            conn.connected = True
            conn.connected_at = now

    db.commit()
    db.refresh(reading)
    return reading


@router.get("/user/{user_id}/status", response_model=WearableConnectionOut)
def get_connection_status(user_id: str, db: Session = Depends(get_db)):
    conn = db.query(WearableConnection).filter(WearableConnection.user_id == user_id).first()
    if conn is None:
        return WearableConnectionOut(user_id=user_id, connected=False)
    return conn


@router.post("/user/{user_id}/disconnect", response_model=WearableConnectionOut)
def disconnect_wearable(user_id: str, payload: WearableDisconnectRequest, db: Session = Depends(get_db)):
    """
    Marks the user disconnected in-app so future sessions stop factoring in
    heart-rate data, and optionally deletes their stored readings entirely.
    Doesn't (can't) reach into the phone -- pair this with turning off
    auto-sync in the bridge app if the user wants syncing to actually stop.
    """
    conn = db.query(WearableConnection).filter(WearableConnection.user_id == user_id).first()
    if conn is None:
        conn = WearableConnection(user_id=user_id, connected=False)
        db.add(conn)
    else:
        conn.connected = False

    if payload.delete_history:
        db.query(WearableReading).filter(WearableReading.user_id == user_id).delete(synchronize_session=False)

    db.commit()
    db.refresh(conn)
    return conn


@router.get("/user/{user_id}/baseline-hr")
def get_baseline_hr(user_id: str, db: Session = Depends(get_db)):
    """
    Resting HR baseline: median heart rate from readings NOT tied to a
    speaking session, over the last 14 days. Used to compute each session's
    relative stress_index instead of comparing raw HR across users.
    """
    baseline = fetch_baseline_hr(db, user_id)
    if baseline is None:
        return {"baseline_hr": None, "sample_size": 0}

    cutoff = datetime.utcnow() - timedelta(days=14)
    sample_size = (
        db.query(WearableReading)
        .filter(
            WearableReading.user_id == user_id,
            WearableReading.metric_type == "heart_rate",
            WearableReading.session_id.is_(None),
            WearableReading.recorded_at >= cutoff,
        )
        .count()
    )
    return {"baseline_hr": round(baseline, 1), "sample_size": sample_size}


@router.get("/session/{session_id}/stress-index")
def get_session_stress_index(session_id: str, baseline_hr: float, db: Session = Depends(get_db)):
    """
    Diagnostic/manual endpoint -- returns both the raw and corroboration-
    weighted stress index for a session, given an explicit baseline. The
    coaching flow (POST /api/coaching/generate) does this automatically
    using the stored baseline and the session's own speech metrics; this
    endpoint is mainly for inspecting a session's numbers directly.
    """
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    readings = db.query(WearableReading).filter(WearableReading.session_id == session_id).all()
    normalized = [
        NormalizedReading(r.device_type, r.metric_type, r.value, r.unit, r.recorded_at)
        for r in readings
    ]
    metrics = session.speech_metrics
    weighted = compute_weighted_stress_index(
        normalized,
        baseline_hr,
        longest_pause_seconds=metrics.longest_pause_seconds if metrics else None,
        nervousness_score=metrics.nervousness_score if metrics else None,
    )
    return {
        "stress_index": weighted.stress_index,
        "raw_stress_index": weighted.raw_stress_index,
        "confidence": weighted.confidence,
        "reasons": weighted.reasons,
    }


@router.post("/session/{session_id}/claim")
def claim_readings_for_session(session_id: str, db: Session = Depends(get_db)):
    """
    Links any untagged (session_id = NULL) readings for this user that fall
    within the session's recording window to this session_id.

    This is what makes watch integration work without the watch's bridge
    app (e.g. an Android Health Connect sync) ever needing to know the
    web app's session_id: the bridge just keeps posting readings tagged
    only with user_id + timestamp, and the frontend calls this endpoint
    right after a recording finishes to sweep up whatever landed in that
    time window.
    """
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    duration = session.duration_seconds or 0
    window_start = session.created_at - timedelta(seconds=CLAIM_WINDOW_BUFFER_SECONDS)
    window_end = session.created_at + timedelta(seconds=duration + CLAIM_WINDOW_BUFFER_SECONDS)

    claimed = (
        db.query(WearableReading)
        .filter(
            WearableReading.user_id == session.user_id,
            WearableReading.session_id.is_(None),
            WearableReading.recorded_at >= window_start,
            WearableReading.recorded_at <= window_end,
        )
        .update({WearableReading.session_id: session_id}, synchronize_session=False)
    )
    db.commit()
    return {"claimed": claimed}
