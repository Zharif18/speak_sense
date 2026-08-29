"""
Actian VectorAI DB-backed session memory. Sponsor tech for PEC Hacks 4.0's
"Best Use of Actian VectorAI DB" track.

Every analyzed session gets embedded (see embeddings.py) and upserted here,
tagged with user_id + scenario_type + a few scalar metrics as payload.
Two things read from it, and both are genuinely load-bearing -- neither
has a fallback path that works without this database:
  1. routers/search.py    -- semantic search over a user's own past sessions
  2. coaching_engine.py   -- pulls the most SIMILAR past sessions as coaching
                             context, not just the most recent ones

Talks to a self-hosted VectorAI DB container over gRPC (see the sponsor
quickstart: `docker run ... actian/vectorai:latest`, client connects on
port 6574). Follows the same graceful-degradation pattern as every other
integration in this app: if the container isn't running, or the SDK isn't
installed, every function here becomes a safe no-op instead of raising --
the rest of SpeakSense works identically without it, just without
search/similarity.
"""

import os
from typing import Any, Dict, List, Optional

from app.services.embeddings import EMBEDDING_DIM, build_embedding_text, embed_text

# gRPC endpoint (port 6574) -- NOT the REST port (6573) or dashboard (6575).
ACTIAN_VECTORAI_URL = os.getenv("ACTIAN_VECTORAI_URL", "localhost:6574")
COLLECTION_NAME = os.getenv("ACTIAN_VECTORAI_COLLECTION", "speaksense_sessions")

try:
    from actian_vectorai import VectorAIClient, VectorParams, Distance, PointStruct
    from actian_vectorai.models import Filter, FieldCondition, Match

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

_client = None
_init_attempted = False


def _get_client():
    """Lazily connects once, caches the client, and ensures the collection
    exists (get_or_create -- see the quickstart's "Collection already
    exists (409)" gotcha, this sidesteps it entirely) before first use."""
    global _client, _init_attempted
    if _init_attempted:
        return _client
    _init_attempted = True

    if not _SDK_AVAILABLE:
        return None

    try:
        client = VectorAIClient(ACTIAN_VECTORAI_URL)
        client.connect()
        client.collections.get_or_create(
            COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.Cosine),
        )
        _client = client
    except Exception:
        _client = None
    return _client


def upsert_session(
    session_id: str,
    user_id: str,
    transcript: str,
    scenario_type: Optional[str] = None,
    words_per_minute: Optional[float] = None,
    filler_word_rate: Optional[float] = None,
    confidence_score: Optional[float] = None,
) -> bool:
    """Embeds and stores one session. Returns False (not an exception) on
    any failure -- called right after speech analysis, and must never be
    allowed to break that request."""
    client = _get_client()
    if client is None or not transcript:
        return False

    text = build_embedding_text(transcript, scenario_type, words_per_minute, filler_word_rate)
    vector = embed_text(text)
    if vector is None:
        return False

    payload: Dict[str, Any] = {"user_id": user_id, "text_preview": transcript[:300]}
    if scenario_type:
        payload["scenario_type"] = scenario_type
    if words_per_minute is not None:
        payload["words_per_minute"] = words_per_minute
    if filler_word_rate is not None:
        payload["filler_word_rate"] = filler_word_rate
    if confidence_score is not None:
        payload["confidence_score"] = confidence_score

    try:
        client.points.upsert(
            COLLECTION_NAME,
            [PointStruct(id=session_id, vector=vector, payload=payload)],
        )
        return True
    except Exception:
        return False


def _user_filter(user_id: str) -> "Filter":
    return Filter(must=[FieldCondition(key="user_id", match=Match(keyword=user_id))])


def search_sessions(user_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Semantic search over one user's own sessions. Always scoped to
    user_id via a payload filter -- one user's practice history is never
    visible in another's search results."""
    client = _get_client()
    if client is None:
        return []

    vector = embed_text(query)
    if vector is None:
        return []

    try:
        results = client.points.search(
            COLLECTION_NAME,
            vector=vector,
            limit=top_k,
            filter=_user_filter(user_id),
        )
        return [
            {"session_id": str(r.id), "score": round(r.score, 4), **(r.payload or {})}
            for r in results
        ]
    except Exception:
        return []


def find_similar_sessions(
    session_id: str, user_id: str, transcript: str, top_k: int = 3
) -> List[Dict[str, Any]]:
    """Used by the coaching engine: given the CURRENT session's transcript,
    find the most semantically similar PAST sessions from this same user
    (excluding itself) to use as coaching context -- e.g. "you also
    struggled with rambling answers in your last salary-negotiation
    practice" instead of only ever looking at the most recent session."""
    client = _get_client()
    if client is None or not transcript:
        return []

    vector = embed_text(transcript)
    if vector is None:
        return []

    try:
        results = client.points.search(
            COLLECTION_NAME,
            vector=vector,
            limit=top_k + 1,  # +1 since this session itself may already be indexed
            filter=_user_filter(user_id),
        )
        filtered = [r for r in results if str(r.id) != str(session_id)]
        return [
            {"session_id": str(r.id), "similarity": round(r.score, 3), **(r.payload or {})}
            for r in filtered[:top_k]
        ]
    except Exception:
        return []
