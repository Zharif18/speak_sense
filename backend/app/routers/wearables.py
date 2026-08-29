from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WearableReading
from app.schemas import WearableReadingIn, WearableReadingOut
from app.services.wearable_adapter import compute_stress_index, NormalizedReading

router = APIRouter()


@router.post("/ingest", response_model=WearableReadingOut)
def ingest_reading(payload: WearableReadingIn, db: Session = Depends(get_db)):
    """
    Called by the client (Android Health Connect bridge, or a NoiseFit sync
    job) with already-normalized readings. This is the single entry point
    every adapter funnels into, which is what keeps SpeakSense device-agnostic.
    """
    reading = WearableReading(**payload.model_dump())
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.get("/user/{user_id}/baseline-hr")
def get_baseline_hr(user_id: str, db: Session = Depends(get_db)):
    """
    Resting HR baseline: median heart rate from readings NOT tied to a
    speaking session, over the last 14 days. Used to compute each session's
    relative stress_index instead of comparing raw HR across users.
    """
    cutoff = datetime.utcnow() - timedelta(days=14)
    readings = (
        db.query(WearableReading)
        .filter(
            WearableReading.user_id == user_id,
            WearableReading.metric_type == "heart_rate",
            WearableReading.session_id.is_(None),
            WearableReading.recorded_at >= cutoff,
        )
        .all()
    )
    if not readings:
        return {"baseline_hr": None, "sample_size": 0}

    values = sorted(r.value for r in readings)
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"baseline_hr": round(median, 1), "sample_size": len(values)}


@router.get("/session/{session_id}/stress-index")
def get_session_stress_index(session_id: str, baseline_hr: float, db: Session = Depends(get_db)):
    readings = db.query(WearableReading).filter(WearableReading.session_id == session_id).all()
    normalized = [
        NormalizedReading(r.device_type, r.metric_type, r.value, r.unit, r.recorded_at)
        for r in readings
    ]
    return {"stress_index": compute_stress_index(normalized, baseline_hr)}
