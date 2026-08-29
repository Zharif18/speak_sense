"""
Live scoring for an in-progress recording, over a WebSocket.

Replaces the old flow of "record the whole thing -> upload -> batch Whisper
transcription -> compute everything" for the record page. Instead:

  - The BROWSER runs speech-to-text itself (Web Speech API, in record/page.tsx)
    -- this is what makes the transcript itself feel instant; there's no
    faster ASR than one that already runs locally in the browser with no
    upload step at all. As each phrase is finalized, the client sends the
    words (with client-side timestamps) here as a `words` message.
  - This socket re-runs the SAME deterministic metrics function the old
    batch endpoint used (`analyze_transcript`) on the growing word list, so
    wpm/pauses/fillers are always the authoritative numbers, not a
    duplicated client-side approximation that could drift from them.
  - The client also streams small raw audio chunks (binary frames) from
    MediaRecorder as they're produced. We keep a rolling buffer and re-score
    nervousness (acoustic features -> trained classifier) every few seconds
    on just the trailing window, so it updates live instead of only once at
    the end.
  - Vocabulary suggestions re-query as new (repeated/watchlisted) words show
    up, capped the same way the batch version was.
  - A `finalize` message (sent when the user stops recording) computes one
    last full-clip pass (whole transcript, whole-audio nervousness score --
    more reliable than any single windowed read) and persists it, exactly
    mirroring what POST /api/speech/{id}/analyze used to write.

Trade-off worth knowing: MediaRecorder's later chunks aren't independently
decodable webm/opus (only the first chunk carries the container header), so
the rolling audio buffer here is "everything received so far", not a true
constant-size ring buffer -- decode cost grows with session length. Fine for
a few-minutes practice session; if sessions get much longer, periodically
restarting MediaRecorder (new header each restart) would bound this.
"""

import asyncio
import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import SpeakingSession, SpeechMetrics
from app.services import vector_store, vocabulary_wolfram
from app.services import nervousness_detector
from app.services.speech_analysis import analyze_transcript

router = APIRouter()

NERVOUSNESS_WINDOW_SECONDS = 8
NERVOUSNESS_MIN_INTERVAL_SECONDS = 3
VOCAB_MIN_NEW_WORDS = 6


@router.websocket("/{session_id}")
async def live_session(websocket: WebSocket, session_id: str):
    await websocket.accept()

    db = SessionLocal()
    session = db.query(SpeakingSession).filter(SpeakingSession.id == session_id).first()
    if not session:
        await websocket.close(code=4404, reason="Session not found")
        db.close()
        return

    words: List[Dict[str, Any]] = []
    audio_chunks: List[bytes] = []
    mime_type = "audio/webm"
    session_start = time.monotonic()
    last_nervousness_at = 0.0
    words_at_last_vocab_check = 0
    nervousness_lock = asyncio.Lock()

    async def score_nervousness_now(window_seconds: Optional[float]) -> Optional[dict]:
        if not audio_chunks:
            return None
        suffix = ".webm" if "webm" in mime_type else ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in audio_chunks:
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            return await asyncio.to_thread(
                nervousness_detector.score_nervousness, tmp_path, window_seconds
            )
        except Exception:
            # Acoustic scoring is a nice-to-have on the live path -- never
            # take the socket down over it.
            return None
        finally:
            os.unlink(tmp_path)

    async def maybe_push_nervousness():
        nonlocal last_nervousness_at
        now = time.monotonic()
        if now - last_nervousness_at < NERVOUSNESS_MIN_INTERVAL_SECONDS:
            return
        if nervousness_lock.locked():
            return  # a scoring pass is already in flight, skip this tick
        last_nervousness_at = now
        async with nervousness_lock:
            result = await score_nervousness_now(NERVOUSNESS_WINDOW_SECONDS)
        if result:
            await websocket.send_json({"type": "nervousness", **result})

    async def maybe_push_vocab():
        nonlocal words_at_last_vocab_check
        if len(words) - words_at_last_vocab_check < VOCAB_MIN_NEW_WORDS:
            return
        words_at_last_vocab_check = len(words)
        suggestions = await vocabulary_wolfram.suggest_alternatives([w["word"] for w in words])
        await websocket.send_json({"type": "vocabulary", "suggestions": suggestions})

    try:
        while True:
            message = await websocket.receive()

            if message.get("bytes") is not None:
                audio_chunks.append(message["bytes"])
                await maybe_push_nervousness()
                continue

            if message.get("text") is None:
                continue

            payload = json.loads(message["text"])
            msg_type = payload.get("type")

            if msg_type == "mime":
                mime_type = payload.get("mime_type") or mime_type

            elif msg_type == "words":
                new_words = payload.get("words", [])
                if not new_words:
                    continue
                words.extend(new_words)

                elapsed = time.monotonic() - session_start
                metrics = analyze_transcript(words, elapsed)
                await websocket.send_json({
                    "type": "metrics",
                    **{k: v for k, v in metrics.items() if k != "raw_metrics"},
                })
                await maybe_push_vocab()

            elif msg_type == "finalize":
                elapsed = time.monotonic() - session_start
                metrics = analyze_transcript(words, elapsed)
                metrics["vocabulary_suggestions"] = await vocabulary_wolfram.suggest_alternatives(
                    [w["word"] for w in words]
                )

                async with nervousness_lock:
                    nervousness = await score_nervousness_now(None)  # full clip, most reliable
                if nervousness:
                    metrics["nervousness_score"] = nervousness["nervousness_score"]
                    metrics["nervousness_label"] = nervousness["label"]

                db_metrics = SpeechMetrics(session_id=session_id, **{
                    k: v for k, v in metrics.items() if k != "raw_metrics"
                }, raw_metrics=metrics.get("raw_metrics"))
                db.add(db_metrics)

                session.status = "analyzed"
                session.duration_seconds = elapsed
                db.commit()
                db.refresh(db_metrics)

                if db_metrics.transcript:
                    try:
                        vector_store.upsert_session(
                            session_id=session_id,
                            user_id=session.user_id,
                            transcript=db_metrics.transcript,
                            scenario_type=session.scenario_type,
                            words_per_minute=db_metrics.words_per_minute,
                            filler_word_rate=db_metrics.filler_word_rate,
                        )
                    except Exception:
                        pass  # same "never block on this" contract as the old batch endpoint

                await websocket.send_json({"type": "finalized", "session_id": session_id})
                break

    except WebSocketDisconnect:
        pass
    finally:
        db.close()
