"""
Inference wrapper for the nervousness model trained by
train_nervousness_model.py. Loads once and caches; scores a single audio
file into a 0-1 nervousness probability plus a human-readable label.

If nervousness_model.pkl doesn't exist yet (not trained), scoring returns
None rather than crashing -- so the rest of the app degrades gracefully
until you run the training script.
"""

import os
from typing import Optional

import joblib
import numpy as np

from app.ml.extract_features import extract_features

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "ml", "nervousness_model.pkl"
)

_cached = None
_load_attempted = False


def _load_model():
    global _cached, _load_attempted
    if _load_attempted:
        return _cached
    _load_attempted = True
    if os.path.exists(MODEL_PATH):
        _cached = joblib.load(MODEL_PATH)
    return _cached


def score_nervousness(audio_path: str, window_seconds: Optional[float] = None):
    """
    Returns {"nervousness_score": float 0-1, "label": str} or None if the
    model hasn't been trained yet.

    window_seconds: passed through to extract_features -- score only the
    trailing N seconds of audio_path instead of the whole file. Used for
    live, in-session scoring; leave None for the final, whole-clip score.
    """
    bundle = _load_model()
    if bundle is None:
        return None

    model = bundle["model"]
    scaler = bundle["scaler"]

    features = extract_features(audio_path, window_seconds=window_seconds).reshape(1, -1)
    features_scaled = scaler.transform(features)

    probability = float(model.predict_proba(features_scaled)[0][1])  # P(nervous)

    if probability >= 0.66:
        label = "notably nervous"
    elif probability >= 0.4:
        label = "somewhat tense"
    else:
        label = "steady"

    return {"nervousness_score": round(probability, 3), "label": label}