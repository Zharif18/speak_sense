import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SpeakingSession, VideoMetrics
from app.schemas import VideoMetricsOut
from app.services import video_analysis

router = APIRouter()


@router.post("/{session_id}/analyze", response_model=VideoMetricsOut)
async def analyze_session_video(
    session_id: str, video: UploadFile = File(...), db: Session = Depends(get_db)
):
    """
    Runs body-language analysis (eye contact, posture, gesture, head
    movement) on the session's recorded video. Video is written to a temp
    file, analyzed, then discarded -- swap in a real upload to Supabase
    Storage first (see speech.py's audio handling for the same pattern)
    if you want the raw video kept around for playback.
    """
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    suffix = os.path.splitext(video.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await video.read())
        tmp_path = tmp.name

    try:
        result = video_analysis.analyze_video(tmp_path)
    finally:
        os.unlink(tmp_path)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Video analysis unavailable: opencv-python-headless and mediapipe "
                "must be installed (see backend/requirements.txt), and the uploaded "
                "clip must contain at least one readable frame with a visible face."
            ),
        )

    existing = (
        db.query(VideoMetrics).filter(VideoMetrics.session_id == session_id).first()
    )
    if existing:
        for key, value in result.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    db_metrics = VideoMetrics(session_id=session_id, **result)
    db.add(db_metrics)
    db.commit()
    db.refresh(db_metrics)
    return db_metrics


@router.get("/{session_id}", response_model=VideoMetricsOut)
def get_video_metrics(session_id: str, db: Session = Depends(get_db)):
    metrics = (
        db.query(VideoMetrics).filter(VideoMetrics.session_id == session_id).first()
    )
    if not metrics:
        raise HTTPException(status_code=404, detail="No video metrics for this session yet")
    return metrics
