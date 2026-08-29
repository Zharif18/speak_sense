"""
Turns a transcript with word-level timestamps into the deterministic speech
metrics shown in the dashboard. This intentionally does NOT use an ML model:
pace, pauses, fillers and repetition are all directly computable and more
trustworthy / explainable to users than a black-box "confidence" model.

Expected input shape (from Whisper word_timestamps=True, or Gemini's
equivalent output normalized to this shape):

    words = [
        {"word": "so", "start": 0.00, "end": 0.32},
        {"word": "um", "start": 0.35, "end": 0.61},
        ...
    ]
"""

import re
from collections import Counter
from typing import List, Dict, Any

FILLER_WORDS = {
    "um", "uh", "uhh", "umm", "like", "you know", "so", "actually",
    "basically", "literally", "i mean", "kind of", "sort of", "right",
}

# Pauses shorter than this are just natural articulation gaps, not hesitation.
MIN_PAUSE_SECONDS = 0.6


def analyze_transcript(words: List[Dict[str, Any]], duration_seconds: float) -> Dict[str, Any]:
    if not words:
        return _empty_metrics()

    tokens = [w["word"].strip().lower() for w in words]
    transcript = " ".join(w["word"] for w in words)

    word_count = len(tokens)
    minutes = max(duration_seconds / 60, 1e-6)
    wpm = round(word_count / minutes, 1)

    # --- Pauses: gaps between consecutive word end/start times ---
    pauses = []
    for prev, curr in zip(words, words[1:]):
        gap = curr["start"] - prev["end"]
        if gap >= MIN_PAUSE_SECONDS:
            pauses.append(gap)

    pause_count = len(pauses)
    avg_pause = round(sum(pauses) / pause_count, 2) if pauses else 0.0
    longest_pause = round(max(pauses), 2) if pauses else 0.0

    # --- Filler words (single + bigram) ---
    filler_count = 0
    for i, tok in enumerate(tokens):
        clean = re.sub(r"[^\w\s]", "", tok)
        if clean in FILLER_WORDS:
            filler_count += 1
        if i < len(tokens) - 1:
            bigram = f"{clean} {re.sub(r'[^\w\s]', '', tokens[i + 1])}"
            if bigram in FILLER_WORDS:
                filler_count += 1

    filler_rate = round((filler_count / word_count) * 100, 1) if word_count else 0.0

    # --- Repetition: immediate word/short-phrase repeats ("I I", "the the") ---
    repetition_count = sum(
        1 for a, b in zip(tokens, tokens[1:])
        if a == b and a.isalpha()
    )

    # --- Vocabulary richness: type-token ratio ---
    clean_tokens = [re.sub(r"[^\w']", "", t) for t in tokens if re.sub(r"[^\w']", "", t)]
    unique_ratio = round(len(set(clean_tokens)) / len(clean_tokens), 2) if clean_tokens else 0.0

    return {
        "transcript": transcript,
        "words_per_minute": wpm,
        "pause_count": pause_count,
        "avg_pause_seconds": avg_pause,
        "longest_pause_seconds": longest_pause,
        "filler_word_count": filler_count,
        "filler_word_rate": filler_rate,
        "repetition_count": repetition_count,
        "unique_word_ratio": unique_ratio,
        "raw_metrics": {
            "word_count": word_count,
            "duration_seconds": duration_seconds,
            "most_common_words": Counter(clean_tokens).most_common(10),
        },
    }


def _empty_metrics() -> Dict[str, Any]:
    return {
        "transcript": "",
        "words_per_minute": 0,
        "pause_count": 0,
        "avg_pause_seconds": 0,
        "longest_pause_seconds": 0,
        "filler_word_count": 0,
        "filler_word_rate": 0,
        "repetition_count": 0,
        "unique_word_ratio": 0,
        "raw_metrics": {},
    }
