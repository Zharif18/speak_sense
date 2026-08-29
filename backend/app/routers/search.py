from fastapi import APIRouter, Query

from app.services import vector_store

router = APIRouter()


@router.get("/sessions")
def search_sessions(
    user_id: str = Query(..., description="Only this user's sessions are searched"),
    query: str = Query(..., min_length=1, description="Natural-language search, e.g. 'times I rambled in interviews'"),
    top_k: int = Query(5, ge=1, le=20),
):
    """
    Semantic search over a user's own past sessions via Pinecone -- matches
    on MEANING, not keywords (e.g. "went blank" also surfaces a session
    where the transcript says "lost my train of thought"). Returns an
    empty list (not an error) if Pinecone isn't configured yet.
    """
    results = vector_store.search_sessions(user_id=user_id, query=query, top_k=top_k)
    return {"query": query, "results": results}
