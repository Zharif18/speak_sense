import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, JSON, Text, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("SpeakingSession", back_populates="user")


class SpeakingSession(Base):
    """One recorded practice attempt: interview, presentation, impromptu, etc."""
    __tablename__ = "speaking_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    scenario_type = Column(
        Enum("interview", "presentation", "impromptu", "introduction", "custom",
             name="scenario_type"),
        nullable=False,
    )
    prompt_text = Column(Text, nullable=True)  # the challenge/question given to the user
    audio_url = Column(String, nullable=True)  # Supabase Storage path
    duration_seconds = Column(Float, nullable=True)

    status = Column(
        Enum("recorded", "processing", "analyzed", "failed", name="session_status"),
        default="recorded",
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    speech_metrics = relationship("SpeechMetrics", back_populates="session", uselist=False)
    video_metrics = relationship("VideoMetrics", back_populates="session", uselist=False)
    wearable_readings = relationship("WearableReading", back_populates="session")
    coaching_feedback = relationship("CoachingFeedback", back_populates="session", uselist=False)


class SpeechMetrics(Base):
    """Deterministic metrics extracted from the transcript + audio timing."""
    __tablename__ = "speech_metrics"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("speaking_sessions.id"), nullable=False)

    transcript = Column(Text, nullable=True)
    words_per_minute = Column(Float, nullable=True)
    pause_count = Column(Integer, nullable=True)
    avg_pause_seconds = Column(Float, nullable=True)
    longest_pause_seconds = Column(Float, nullable=True)
    filler_word_count = Column(Integer, nullable=True)
    filler_word_rate = Column(Float, nullable=True)  # fillers per 100 words
    repetition_count = Column(Integer, nullable=True)
    unique_word_ratio = Column(Float, nullable=True)  # type-token ratio
    vocabulary_suggestions = Column(JSON, nullable=True)  # [{word, context, alternatives:[...]}]
    nervousness_score = Column(Float, nullable=True)  # 0-1, from the trained acoustic model
    nervousness_label = Column(String, nullable=True)  # "steady" | "somewhat tense" | "notably nervous"
    raw_metrics = Column(JSON, nullable=True)  # anything extra, kept flexible

    session = relationship("SpeakingSession", back_populates="speech_metrics")


class VideoMetrics(Base):
    """
    Deterministic body-language metrics extracted from a session's video,
    on top of (not instead of) the audio-based SpeechMetrics. Computed by
    app/services/video_analysis.py from face-mesh + pose landmarks --
    coaching context, not a clinical read on the user's emotional state.
    """
    __tablename__ = "video_metrics"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("speaking_sessions.id"), nullable=False)

    video_url = Column(String, nullable=True)  # Supabase Storage path, once wired up

    frames_analyzed = Column(Integer, nullable=True)
    face_detection_rate = Column(Float, nullable=True)  # % of frames a face was found in

    eye_contact_percent = Column(Float, nullable=True)  # % of on-camera frames looking ~at lens
    eye_contact_breaks = Column(Integer, nullable=True)  # count of look-away episodes >0.5s

    posture_openness_score = Column(Float, nullable=True)  # 0-100, shoulder/head levelness+centering
    posture_variability = Column(Float, nullable=True)     # stddev of torso lean, lower = steadier

    gesture_rate_per_min = Column(Float, nullable=True)   # hand movement events per minute
    gesture_variability = Column(Float, nullable=True)    # 0-1, stillness vs. animated

    head_movement_index = Column(Float, nullable=True)    # 0-1, fidget/nod proxy from head pose jitter
    smile_percent = Column(Float, nullable=True)           # % of frames with a detected smile

    body_language_label = Column(String, nullable=True)  # "open & engaged" | "guarded" | "restless" | ...
    raw_metrics = Column(JSON, nullable=True)  # per-second timeline + anything extra

    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SpeakingSession", back_populates="video_metrics")


class WearableReading(Base):
    """Normalized reading from any wearable, via the universal adapter layer."""
    __tablename__ = "wearable_readings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("speaking_sessions.id"), nullable=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    device_type = Column(String, nullable=False)      # e.g. "noisefit", "health_connect_generic"
    metric_type = Column(String, nullable=False)       # e.g. "heart_rate", "hrv", "sleep_minutes"
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)               # e.g. "bpm", "ms"
    recorded_at = Column(DateTime, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SpeakingSession", back_populates="wearable_readings")


class CoachingFeedback(Base):
    """LLM-generated coaching output for a session (the Context Engine's result)."""
    __tablename__ = "coaching_feedback"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("speaking_sessions.id"), nullable=False)

    summary = Column(Text, nullable=True)
    strengths = Column(JSON, nullable=True)      # list[str]
    improvement_tips = Column(JSON, nullable=True)  # list[str]
    stress_index = Column(Float, nullable=True)   # relative-to-baseline physio signal, may be null
    confidence_score = Column(Float, nullable=True)  # 0-100 composite, heuristic not diagnostic
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SpeakingSession", back_populates="coaching_feedback")


class DailyChallenge(Base):
    __tablename__ = "daily_challenges"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    scenario_type = Column(String, nullable=False)
    difficulty = Column(String, default="beginner")  # beginner/intermediate/advanced
    active_date = Column(DateTime, default=datetime.utcnow)