import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SpeakingSession, SpeechMetrics
from app.schemas import SpeechMetricsOut
from app.services.speech_analysis import analyze_transcript
from app.services import vocabulary_wolfram
from app.services import nervousness_detector

router = APIRouter()

# Loaded lazily on first request and cached — loading the model on every
# request would be extremely slow. `base` is a good speed/accuracy
# tradeoff for a hackathon; env WHISPER_MODEL can override.
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper  # local import: keeps startup fast, fails loudly here if missing
        model_name = os.getenv("WHISPER_MODEL", "base")
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model


@router.post("/{session_id}/analyze", response_model=SpeechMetricsOut)
async def analyze_session(session_id: str, audio: UploadFile = File(...), db: Session = Depends(get_db)):
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "processing"
    db.commit()

    # Save once, reuse the same file for transcription AND nervousness
    # scoring (both need real audio on disk), then always clean up.
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        # 1) Transcribe with word-level timestamps.
        words, duration_seconds = _transcribe(tmp_path)

        # 2) Deterministic metrics (pace, pauses, fillers, repetition, TTR).
        metrics = analyze_transcript(words, duration_seconds)

        # 3) Vocabulary enrichment (Datamuse primary, Wolfram secondary).
        transcript_words = [w["word"] for w in words]
        metrics["vocabulary_suggestions"] = await vocabulary_wolfram.suggest_alternatives(transcript_words)

        # 4) Nervousness, from acoustic features via the locally trained
        #    model. Returns None if nervousness_model.pkl hasn't been
        #    trained yet (see app/ml/train_nervousness_model.py) -- degrades
        #    gracefully rather than failing the whole analysis.
        nervousness = nervousness_detector.score_nervousness(tmp_path)
        if nervousness:
            metrics["nervousness_score"] = nervousness["nervousness_score"]
            metrics["nervousness_label"] = nervousness["label"]
    finally:
        os.unlink(tmp_path)

    db_metrics = SpeechMetrics(session_id=session_id, **{
        k: v for k, v in metrics.items() if k != "raw_metrics"
    }, raw_metrics=metrics.get("raw_metrics"))
    db.add(db_metrics)

    session.status = "analyzed"
    session.duration_seconds = duration_seconds
    db.commit()
    db.refresh(db_metrics)

    return db_metrics


def _transcribe(tmp_path: str):
    """
    Transcribes the audio at tmp_path with local Whisper, using
    word_timestamps=True to get the per-word start/end times that
    speech_analysis.analyze_transcript expects.
    Returns (words, duration_seconds).
    """
    try:
        model = _get_whisper_model()
        result = model.transcribe(tmp_path, word_timestamps=True)

        words = [
            {"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
            for segment in result.get("segments", [])
            for w in segment.get("words", [])
            if w.get("word", "").strip()
        ]

        duration_seconds = (
            float(result["segments"][-1]["end"]) if result.get("segments") else 0.0
        )

        return words, duration_seconds
    except FileNotFoundError as e:
        # Raised by whisper/ffmpeg-python when the ffmpeg binary isn't on PATH.
        raise HTTPException(
            status_code=500,
            detail=(
                "Transcription failed: ffmpeg not found. Install ffmpeg and "
                "make sure it's on your system PATH, then restart the backend."
            ),
        ) from e