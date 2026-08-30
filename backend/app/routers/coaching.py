from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import SpeakingSession, CoachingFeedback, WearableConnection
from app.schemas import CoachingRequest, CoachingFeedbackOut
from app.services.coaching_engine import generate_coaching_feedback
from app.services.wearable_adapter import (
    compute_weighted_stress_index,
    fetch_baseline_hr,
    NormalizedReading,
)
from app.services.n8n_notify import notify_session_analyzed

router = APIRouter()


@router.post("/generate", response_model=CoachingFeedbackOut)
async def generate_feedback(payload: CoachingRequest, db: Session = Depends(get_db)):
    session = db.query(SpeakingSession).filter(SpeakingSession.id == payload.session_id).first()
    if not session or not session.speech_metrics:
        raise HTTPException(status_code=404, detail="Session or its speech metrics not found")

    # Pull last 5 analyzed sessions for this user as trend context.
    past = (
        db.query(SpeakingSession)
        .filter(
            SpeakingSession.user_id == session.user_id,
            SpeakingSession.status == "analyzed",
            SpeakingSession.id != session.id,
        )
        .order_by(desc(SpeakingSession.created_at))
        .limit(5)
        .all()
    )
    past_summaries = [
        {
            "scenario_type": s.scenario_type,
            "words_per_minute": s.speech_metrics.words_per_minute if s.speech_metrics else None,
            "filler_word_rate": s.speech_metrics.filler_word_rate if s.speech_metrics else None,
        }
        for s in past
    ]

    weighted_stress = None
    connection = db.query(WearableConnection).filter(WearableConnection.user_id == session.user_id).first()
    wearable_connected = connection is not None and connection.connected

    if wearable_connected and session.wearable_readings:
        normalized = [
            NormalizedReading(r.device_type, r.metric_type, r.value, r.unit, r.recorded_at)
            for r in session.wearable_readings
        ]
        hr_values = [r.value for r in normalized if r.metric_type == "heart_rate"]
        if hr_values:
            # Real resting baseline from this user's non-session readings, when
            # we have one. If the watch was only just connected and there's no
            # 14-day resting history yet, fall back to a same-session estimate --
            # but that estimate is far less trustworthy, so it's flagged and the
            # weighting engine caps confidence accordingly rather than treating
            # it like a measured baseline.
            baseline = fetch_baseline_hr(db, session.user_id)
            baseline_is_estimated = baseline is None
            if baseline is None:
                baseline = sum(hr_values) / len(hr_values) * 0.9

            weighted_stress = compute_weighted_stress_index(
                normalized,
                baseline,
                longest_pause_seconds=session.speech_metrics.longest_pause_seconds,
                nervousness_score=session.speech_metrics.nervousness_score,
                baseline_is_estimated=baseline_is_estimated,
            )

    metrics_dict = {
        "words_per_minute": session.speech_metrics.words_per_minute,
        "pause_count": session.speech_metrics.pause_count,
        "avg_pause_seconds": session.speech_metrics.avg_pause_seconds,
        "filler_word_rate": session.speech_metrics.filler_word_rate,
        "repetition_count": session.speech_metrics.repetition_count,
        "unique_word_ratio": session.speech_metrics.unique_word_ratio,
        "nervousness_score": session.speech_metrics.nervousness_score,
        "nervousness_label": session.speech_metrics.nervousness_label,
    }

    video_metrics_dict = None
    if session.video_metrics:
        v = session.video_metrics
        video_metrics_dict = {
            "eye_contact_percent": v.eye_contact_percent,
            "eye_contact_breaks": v.eye_contact_breaks,
            "posture_openness_score": v.posture_openness_score,
            "gesture_rate_per_min": v.gesture_rate_per_min,
            "body_language_label": v.body_language_label,
        }

    result = generate_coaching_feedback(
        scenario_type=session.scenario_type,
        prompt_text=session.prompt_text,
        speech_metrics=metrics_dict,
        weighted_stress=weighted_stress,
        past_sessions=past_summaries,
        video_metrics=video_metrics_dict,
    )

    feedback = CoachingFeedback(
        session_id=session.id,
        summary=result.get("summary"),
        strengths=result.get("strengths"),
        improvement_tips=result.get("improvement_tips"),
        stress_index=weighted_stress.stress_index if weighted_stress else None,
        stress_index_raw=weighted_stress.raw_stress_index if weighted_stress else None,
        stress_confidence=weighted_stress.confidence if weighted_stress else None,
        stress_reasons=weighted_stress.reasons if weighted_stress else None,
        confidence_score=result.get("confidence_score"),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Hand off to n8n: recap notification, Slack/email, logging, whatever
    # the workflow does with it. Never blocks or fails the API response.
    await notify_session_analyzed({
        "session_id": session.id,
        "user_id": session.user_id,
        "scenario_type": session.scenario_type,
        "confidence_score": feedback.confidence_score,
        "summary": feedback.summary,
        "filler_word_rate": session.speech_metrics.filler_word_rate,
        "words_per_minute": session.speech_metrics.words_per_minute,
    })

    return feedback


@router.get("/{session_id}", response_model=CoachingFeedbackOut)
def get_feedback(session_id: str, db: Session = Depends(get_db)):
    feedback = (
        db.query(CoachingFeedback)
        .filter(CoachingFeedback.session_id == session_id)
        .first()
    )
    if not feedback:
        raise HTTPException(status_code=404, detail="No feedback generated yet for this session")
    return feedback