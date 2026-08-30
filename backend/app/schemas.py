from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ---------- Sessions ----------

class SessionCreate(BaseModel):
    user_id: str
    scenario_type: str
    prompt_text: Optional[str] = None


class SessionOut(BaseModel):
    id: str
    user_id: str
    scenario_type: str
    prompt_text: Optional[str]
    audio_url: Optional[str]
    duration_seconds: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Speech analysis ----------

class VocabularySuggestion(BaseModel):
    word: str
    context: str
    alternatives: List[str]


class SpeechMetricsOut(BaseModel):
    transcript: Optional[str]
    words_per_minute: Optional[float]
    pause_count: Optional[int]
    avg_pause_seconds: Optional[float]
    longest_pause_seconds: Optional[float]
    filler_word_count: Optional[int]
    filler_word_rate: Optional[float]
    repetition_count: Optional[int]
    unique_word_ratio: Optional[float]
    vocabulary_suggestions: Optional[List[VocabularySuggestion]] = None
    nervousness_score: Optional[float] = None
    nervousness_label: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Video / body language ----------

class VideoMetricsOut(BaseModel):
    video_url: Optional[str] = None
    frames_analyzed: Optional[int]
    face_detection_rate: Optional[float]
    eye_contact_percent: Optional[float]
    eye_contact_breaks: Optional[int]
    posture_openness_score: Optional[float]
    posture_variability: Optional[float]
    gesture_rate_per_min: Optional[float]
    gesture_variability: Optional[float]
    head_movement_index: Optional[float]
    smile_percent: Optional[float]
    body_language_label: Optional[str]

    class Config:
        from_attributes = True


# ---------- Wearables ----------

class WearableReadingIn(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    device_type: str
    metric_type: str
    value: float
    unit: str
    recorded_at: datetime


class WearableReadingOut(WearableReadingIn):
    id: str
    ingested_at: datetime

    class Config:
        from_attributes = True


class WearableConnectionOut(BaseModel):
    user_id: str
    device_type: Optional[str] = None
    connected: bool
    connected_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None


class WearableDisconnectRequest(BaseModel):
    delete_history: bool = False


# ---------- Coaching ----------

class CoachingRequest(BaseModel):
    session_id: str


class CoachingFeedbackOut(BaseModel):
    summary: Optional[str]
    strengths: Optional[List[str]]
    improvement_tips: Optional[List[str]]
    stress_index: Optional[float]
    stress_index_raw: Optional[float] = None
    stress_confidence: Optional[float] = None
    stress_reasons: Optional[List[str]] = None
    confidence_score: Optional[float]

    class Config:
        from_attributes = True


# ---------- Progress ----------

class ProgressPoint(BaseModel):
    session_id: str
    created_at: datetime
    words_per_minute: Optional[float]
    filler_word_rate: Optional[float]
    confidence_score: Optional[float]


class ProgressOut(BaseModel):
    user_id: str
    points: List[ProgressPoint]
    trend_summary: str


# ---------- Combined session detail (for the dashboard) ----------

class SessionFullOut(BaseModel):
    id: str
    user_id: str
    scenario_type: str
    prompt_text: Optional[str]
    status: str
    duration_seconds: Optional[float]
    created_at: datetime
    speech_metrics: Optional[SpeechMetricsOut] = None
    video_metrics: Optional[VideoMetricsOut] = None
    coaching_feedback: Optional[CoachingFeedbackOut] = None

    class Config:
        from_attributes = True