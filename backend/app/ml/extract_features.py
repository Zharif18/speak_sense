"""
Extracts a fixed-length feature vector from a speech audio clip, capturing
the acoustic signals speech science associates with nervousness/stress:

  - Pitch (F0) mean and std       -- nervous speech tends to have a higher,
                                      more erratic pitch (voice "shaking")
  - Jitter                        -- cycle-to-cycle pitch instability
  - RMS energy mean and std       -- shaky/uneven loudness
  - Shimmer                       -- cycle-to-cycle amplitude instability
  - Speaking rate proxy           -- (voiced frames / total frames) ratio
  - MFCC means + stds (13 coeffs) -- general timbre/vocal-tract shape,
                                      lets the classifier pick up patterns
                                      beyond the hand-picked features above

This is deliberately built on librosa (pretrained-signal-processing, not a
trained model itself) so the ONLY thing that needs training is the small
classifier in train_nervousness_model.py -- keeping this reusable for both
training (on the public dataset) and inference (on a user's real session).
"""

import os
import shutil
import subprocess
import tempfile

import numpy as np
import librosa

SAMPLE_RATE = 16000
FEATURE_NAMES = [
    "pitch_mean", "pitch_std", "jitter",
    "energy_mean", "energy_std", "shimmer",
    "voiced_ratio",
] + [f"mfcc{i}_mean" for i in range(13)] + [f"mfcc{i}_std" for i in range(13)]


def _to_wav(audio_path: str) -> str:
    """
    librosa/soundfile can only decode formats libsndfile understands (wav,
    flac, ogg, ...) -- not webm/opus, which is what the browser's
    MediaRecorder produces for recorded sessions. RAVDESS files are already
    .wav, so this is a no-op for training; it only matters at inference
    time on real session recordings.
    Returns a path to a 16kHz mono wav -- a new temp file if conversion was
    needed, or audio_path unchanged if it was already a wav.
    """
    if audio_path.lower().endswith(".wav"):
        return audio_path

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH -- required to decode recorded audio "
            "for nervousness scoring (same requirement as Whisper transcription)."
        )

    wav_path = tempfile.mktemp(suffix=".wav")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ar", str(SAMPLE_RATE), "-ac", "1", wav_path],
        capture_output=True,
    )
    if result.returncode != 0 or not os.path.exists(wav_path):
        raise RuntimeError(f"ffmpeg failed to convert {audio_path}: {result.stderr.decode(errors='ignore')[-500:]}")
    return wav_path


def extract_features(audio_path: str) -> np.ndarray:
    wav_path = _to_wav(audio_path)
    converted = wav_path != audio_path
    try:
        y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
    finally:
        if converted:
            os.unlink(wav_path)

    if len(y) < sr * 0.3:  # too short to extract anything meaningful
        return np.zeros(len(FEATURE_NAMES), dtype=np.float32)

    # --- Pitch (F0) via pYIN, a standard pitch-tracking algorithm ---
    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
    )
    f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])

    if len(f0_voiced) > 1:
        pitch_mean = float(np.mean(f0_voiced))
        pitch_std = float(np.std(f0_voiced))
        # Jitter: average absolute frame-to-frame pitch change, normalized.
        diffs = np.abs(np.diff(f0_voiced))
        jitter = float(np.mean(diffs) / pitch_mean) if pitch_mean > 0 else 0.0
    else:
        pitch_mean = pitch_std = jitter = 0.0

    voiced_ratio = float(np.mean(voiced_flag)) if voiced_flag is not None and len(voiced_flag) else 0.0

    # --- Energy (RMS) ---
    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    # Shimmer: average absolute frame-to-frame amplitude change, normalized.
    if len(rms) > 1 and energy_mean > 0:
        rms_diffs = np.abs(np.diff(rms))
        shimmer = float(np.mean(rms_diffs) / energy_mean)
    else:
        shimmer = 0.0

    # --- MFCCs: general vocal-tract/timbre shape ---
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_means = np.mean(mfccs, axis=1)
    mfcc_stds = np.std(mfccs, axis=1)

    features = np.concatenate([
        [pitch_mean, pitch_std, jitter, energy_mean, energy_std, shimmer, voiced_ratio],
        mfcc_means,
        mfcc_stds,
    ]).astype(np.float32)

    return np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)