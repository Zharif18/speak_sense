from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.services import vocabulary_wolfram

router = APIRouter()


class VocabularyRequest(BaseModel):
    words: List[str]
    min_repeats: int = 3


@router.post("/suggest")
async def suggest(payload: VocabularyRequest):
    suggestions = await vocabulary_wolfram.suggest_alternatives(payload.words, payload.min_repeats)
    return {"suggestions": suggestions}
