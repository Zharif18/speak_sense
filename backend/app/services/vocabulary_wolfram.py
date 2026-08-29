"""
Vocabulary enrichment: flags repeated/weak words from a transcript (using
the type-token stats already computed in speech_analysis.py) and looks up
context-appropriate synonyms.

Synonym lookup tries three sources in order, each one a fallback for the
last:
  1. Datamuse (https://api.datamuse.com) -- free, no API key, purpose-built
     for synonym lookup, and has real coverage of ordinary English words.
     This is the primary source now.
  2. Wolfram|Alpha (sponsor integration) -- kept as a secondary source so
     the sponsor tech still gets used; Wolfram's plain-result endpoint is
     really built for computation, not lexical lookup, so it's inconsistent
     as a synonym source on its own.
  3. A tiny hardcoded table -- last-resort so the demo still shows *something*
     for a handful of very common "weak vocabulary" words even if both APIs
     are unreachable (e.g. offline demo, no wifi at judging).
"""

import os
import httpx
from collections import Counter
from typing import List, Dict, Any, Optional

WOLFRAM_APP_ID = os.getenv("WOLFRAM_APP_ID", "")
WOLFRAM_BASE_URL = "https://api.wolframalpha.com/v1/result"
DATAMUSE_BASE_URL = "https://api.datamuse.com/words"

# Words too common/functional to bother suggesting alternatives for.
STOPWORDS = {
    "the", "a", "an", "is", "was", "are", "were", "to", "of", "and", "in",
    "on", "for", "it", "i", "you", "we", "they", "that", "this", "be",
}

# Words we deliberately over-flag for demo purposes even at low repeat counts,
# because they're common "weak vocabulary" tells in student speech.
WATCHLIST = {"good", "bad", "nice", "thing", "stuff", "very", "really", "big"}


async def suggest_alternatives(transcript_words: List[str], min_repeats: int = 3) -> List[Dict[str, Any]]:
    counts = Counter(w.lower() for w in transcript_words if w.lower() not in STOPWORDS)
    flagged = [
        word for word, count in counts.items()
        if count >= min_repeats or word in WATCHLIST
    ]

    suggestions = []
    async with httpx.AsyncClient(timeout=8.0) as client:
        for word in flagged[:8]:  # cap external calls per session
            alternatives = await _get_synonyms(client, word)
            if alternatives:
                suggestions.append({
                    "word": word,
                    "context": f"used {counts[word]} times in this session",
                    "alternatives": alternatives,
                })
    return suggestions


async def _get_synonyms(client: httpx.AsyncClient, word: str) -> List[str]:
    alternatives = await _query_datamuse_synonyms(client, word)
    if alternatives:
        return alternatives

    alternatives = await _query_wolfram_synonyms(client, word)
    if alternatives:
        return alternatives

    return _fallback_synonyms(word)


async def _query_datamuse_synonyms(client: httpx.AsyncClient, word: str) -> List[str]:
    try:
        resp = await client.get(DATAMUSE_BASE_URL, params={"rel_syn": word, "max": 8})
        if resp.status_code != 200:
            return []
        results = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    cleaned = []
    for item in results:
        candidate = item.get("word", "").strip().lower()
        # Skip multi-word phrases, the query word itself, and dupes -- keeps
        # suggestions punchy single-word swaps rather than noisy phrases.
        if not candidate or " " in candidate or candidate == word.lower():
            continue
        if candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned[:5]


async def _query_wolfram_synonyms(client: httpx.AsyncClient, word: str) -> List[str]:
    if not WOLFRAM_APP_ID:
        return []

    params = {"appid": WOLFRAM_APP_ID, "i": f"synonyms of {word}"}
    try:
        resp = await client.get(WOLFRAM_BASE_URL, params=params)
        if resp.status_code == 200 and resp.text:
            # Wolfram's plain-result endpoint returns a comma-separated string.
            return [w.strip() for w in resp.text.split(",") if w.strip()][:5]
    except httpx.HTTPError:
        pass
    return []


def _fallback_synonyms(word: str) -> List[str]:
    """Last-resort local table so the demo still shows something offline."""
    table = {
        "good": ["effective", "compelling", "well-executed"],
        "bad": ["ineffective", "weak", "unclear"],
        "nice": ["pleasant", "well-received", "polished"],
        "thing": ["factor", "element", "aspect"],
        "stuff": ["material", "content", "points"],
        "very": ["notably", "significantly", "particularly"],
        "really": ["genuinely", "distinctly"],
        "big": ["substantial", "significant", "major"],
    }
    return table.get(word, [])