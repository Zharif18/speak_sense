"""
Trains your own nervousness classifier on RAVDESS (a free, public,
labeled emotion-speech dataset) using the acoustic features from
extract_features.py.

--- Setup ---
1. Download RAVDESS "Audio_Speech_Actors_01-24.zip" (~200 MB) from:
   https://zenodo.org/record/1188976
   (Look for "Audio-only files" -> Speech.)
2. Unzip it. You'll get folders like Actor_01/, Actor_02/, ... each full of
   .wav files named like: 03-01-06-01-02-01-12.wav
   The 3rd number in the filename is the emotion code:
     01=neutral 02=calm 03=happy 04=sad 05=angry 06=fearful 07=disgust 08=surprised
3. Run:
     python -m app.ml.train_nervousness_model --data-dir "C:/path/to/RAVDESS"

--- What "nervous" means here ---
We label "fearful" as the positive (nervous) class -- it's the closest
proxy RAVDESS has to nervous/anxious speech. "calm" and "neutral" are the
negative class. Other emotions (happy/sad/angry/disgust/surprised) are
excluded from training since they're not on the nervous<->calm axis and
would just add label noise.

This gives you a real binary classifier trained on human-labeled data,
not a heuristic.
"""

import argparse
import glob
import os
import sys

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import joblib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.ml.extract_features import extract_features, FEATURE_NAMES

RAVDESS_EMOTION_CODES = {
    "01": "neutral", "02": "calm", "03": "happy", "04": "sad",
    "05": "angry", "06": "fearful", "07": "disgust", "08": "surprised",
}
POSITIVE_EMOTIONS = {"fearful"}   # -> nervous
NEGATIVE_EMOTIONS = {"calm", "neutral"}  # -> not nervous

MODEL_OUT_PATH = os.path.join(os.path.dirname(__file__), "nervousness_model.pkl")


def label_from_filename(path: str):
    name = os.path.basename(path)
    parts = name.split("-")
    if len(parts) < 3:
        return None
    emotion = RAVDESS_EMOTION_CODES.get(parts[2])
    if emotion in POSITIVE_EMOTIONS:
        return 1
    if emotion in NEGATIVE_EMOTIONS:
        return 0
    return None  # excluded emotion, skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Path to unzipped RAVDESS root (contains Actor_01/, Actor_02/, ...)")
    args = parser.parse_args()

    wav_files = glob.glob(os.path.join(args.data_dir, "**", "*.wav"), recursive=True)
    if not wav_files:
        print(f"No .wav files found under {args.data_dir}. Check the path.")
        return

    print(f"Found {len(wav_files)} audio files. Extracting features (this takes a few minutes)...")

    X, y = [], []
    for i, path in enumerate(wav_files):
        label = label_from_filename(path)
        if label is None:
            continue
        try:
            feats = extract_features(path)
        except Exception as e:
            print(f"  skipping {os.path.basename(path)}: {e}")
            continue
        X.append(feats)
        y.append(label)
        if (i + 1) % 50 == 0:
            print(f"  processed {i + 1}/{len(wav_files)}")

    X = np.array(X)
    y = np.array(y)
    print(f"\nUsable samples: {len(y)} (nervous={sum(y)}, calm={len(y) - sum(y)})")

    if len(set(y)) < 2:
        print("Need both classes present -- check your data-dir and label mapping.")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, class_weight="balanced")
    clf.fit(X_train_scaled, y_train)

    y_pred = clf.predict(X_test_scaled)
    print("\n--- Evaluation on held-out test set ---")
    print(classification_report(y_test, y_pred, target_names=["calm", "nervous"]))

    joblib.dump({"model": clf, "scaler": scaler, "feature_names": FEATURE_NAMES}, MODEL_OUT_PATH)
    print(f"\nSaved trained model to {MODEL_OUT_PATH}")


if __name__ == "__main__":
    main()