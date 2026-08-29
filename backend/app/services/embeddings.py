"""
Turns a session transcript + its metrics into a single embedding vector.

Actian VectorAI DB is a filing cabinet + search engine for vectors -- it
deliberately doesn't ship an embedding model of its own (see the sponsor
quickstart guide's "bring your own" note). This module is that translator.

Runs a sentence-transformers model LOCALLY (downloaded once, cached
on-disk after that) rather than calling out to a cloud embedding API.
That's a deliberate choice, not just a convenience: VectorAI DB itself is
built to run at the edge/on-prem/disconnected, and a coaching app with no
API-key requirement for its core "understand what I said" loop matches
that story end to end.
"""

import os
from typing import List, Optional

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Must match whatever model EMBEDDING_MODEL resolves to -- all-MiniLM-L6-v2
# outputs 384-dim vectors. Change both together if you swap models (e.g.
# all-mpnet-base-v2 -> 768). A mismatch here fails loudly on the VectorAI DB
# side (DIMENSION_MISMATCH), not silently.
EMBEDDING_DIM = 384

_model = None


def _get_model():
    """Loads the sentence-transformers model once and caches it -- loading
    it per-request would make every /api/speech/analyze call pay a multi-
    second model-load tax. Returns None (not an exception) if the package
    isn't installed, so callers can degrade gracefully."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
        _model = SentenceTransformer(model_name)
    except Exception:
        _model = False  # sentinel: "tried and failed," don't retry every call
    return _model or None


def build_embedding_text(
    transcript: str,
    scenario_type: Optional[str] = None,
    words_per_minute: Optional[float] = None,
    filler_word_rate: Optional[float] = None,
) -> str:
    """Folds a few metrics into the embedded text so the vector captures
    *how* the session went, not just what was said -- pure transcript text
    alone loses concepts like "spoke too fast" or "lots of hesitation."""
    parts = []
    if scenario_type:
        parts.append(f"Scenario: {scenario_type}.")
    if words_per_minute is not None:
        pace = "fast" if words_per_minute > 160 else "slow" if words_per_minute < 110 else "moderate"
        parts.append(f"Speaking pace was {pace} ({round(words_per_minute)} wpm).")
    if filler_word_rate is not None:
        fillers = "frequent" if filler_word_rate > 0.06 else "occasional" if filler_word_rate > 0.02 else "minimal"
        parts.append(f"Filler word usage was {fillers}.")
    parts.append(f"Transcript: {transcript.strip()}")
    return " ".join(parts)


def embed_text(text: str) -> Optional[List[float]]:
    """Returns a 384-dim embedding, or None (never raises) if the model
    isn't available -- same graceful-degradation pattern as the rest of
    the app (Whisper, MediaPipe, Wolfram all do this too)."""
    model = _get_model()
    if model is None or not text:
        return None
    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception:
        return None
