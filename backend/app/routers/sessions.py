from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import SpeakingSession, SpeechMetrics, CoachingFeedback
from app.schemas import SessionCreate, SessionOut, ProgressOut, ProgressPoint, SessionFullOut

router = APIRouter()


@router.post("", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    session = SpeakingSession(
        user_id=payload.user_id,
        scenario_type=payload.scenario_type,
        prompt_text=payload.prompt_text,
        status="recorded",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/full", response_model=SessionFullOut)
def get_session_full(session_id: str, db: Session = Depends(get_db)):
    """
    One call for the dashboard: session + its speech metrics + its coaching
    feedback (either may be None if analysis/coaching hasn't run yet).
    """
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/user/{user_id}", response_model=list[SessionOut])
def list_user_sessions(user_id: str, db: Session = Depends(get_db)):
    return (
        db.query(SpeakingSession)
        .filter(SpeakingSession.user_id == user_id)
        .order_by(desc(SpeakingSession.created_at))
        .all()
    )


@router.get("/user/{user_id}/progress", response_model=ProgressOut)
def get_progress(user_id: str, db: Session = Depends(get_db)):
    sessions = (
        db.query(SpeakingSession)
        .filter(SpeakingSession.user_id == user_id, SpeakingSession.status == "analyzed")
        .order_by(SpeakingSession.created_at)
        .all()
    )

    points = []
    for s in sessions:
        metrics = s.speech_metrics
        feedback = s.coaching_feedback
        points.append(ProgressPoint(
            session_id=s.id,
            created_at=s.created_at,
            words_per_minute=metrics.words_per_minute if metrics else None,
            filler_word_rate=metrics.filler_word_rate if metrics else None,
            confidence_score=feedback.confidence_score if feedback else None,
        ))

    trend_summary = _summarize_trend(points)
    return ProgressOut(user_id=user_id, points=points, trend_summary=trend_summary)


def _summarize_trend(points: list[ProgressPoint]) -> str:
    scored = [p.confidence_score for p in points if p.confidence_score is not None]
    if len(scored) < 2:
        return "Not enough sessions yet to show a trend. Keep practicing!"
    delta = scored[-1] - scored[0]
    if delta > 5:
        return f"Confidence score is trending up (+{round(delta)} pts since your first session)."
    if delta < -5:
        return f"Confidence score has dipped ({round(delta)} pts) — that's normal, try an easier scenario."
    return "Confidence score is holding steady across recent sessions."