"""
Universal wearable layer.

Every device/source implements `.fetch(user_token, start, end) -> list[NormalizedReading]`.
The rest of the app (DB, coaching engine) only ever deals with NormalizedReading,
so adding a new watch is a matter of writing one adapter, not touching anything else.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
import statistics


@dataclass
class NormalizedReading:
    device_type: str
    metric_type: str  # "heart_rate" | "hrv" | "sleep_minutes" | "motion_index"
    value: float
    unit: str
    recorded_at: datetime


class WearableAdapter(ABC):
    device_type: str

    @abstractmethod
    def fetch(self, user_token: str, start: datetime, end: datetime) -> List[NormalizedReading]:
        ...


class HealthConnectAdapter(WearableAdapter):
    """
    Covers most Android-synced watches (including NoiseFit, once it syncs
    through Health Connect) via Android's Health Connect API. On the Android
    client, read raw records and POST them to /api/wearables/ingest in this
    normalized shape -- this class documents/validates that shape server-side.
    """
    device_type = "health_connect"

    def fetch(self, user_token: str, start: datetime, end: datetime) -> List[NormalizedReading]:
        # In production this is called from the mobile client via Health
        # Connect's on-device API (no server-side OAuth exists for Health
        # Connect). Server-side, we only validate + store what the client
        # already normalized and posted to /api/wearables/ingest.
        raise NotImplementedError(
            "Health Connect readings arrive via POST /api/wearables/ingest "
            "from the Android client, not a server-side fetch."
        )


class NoiseFitCloudAdapter(WearableAdapter):
    """Placeholder for direct NoiseFit cloud API access, where available."""
    device_type = "noisefit"

    def fetch(self, user_token: str, start: datetime, end: datetime) -> List[NormalizedReading]:
        # TODO: wire up real NoiseFit API once partner access is granted.
        # Until then, ingestion happens through HealthConnectAdapter's flow.
        return []


ADAPTERS = {
    "health_connect": HealthConnectAdapter(),
    "noisefit": NoiseFitCloudAdapter(),
}


def compute_stress_index(readings: List[NormalizedReading], baseline_hr: float) -> float | None:
    """
    Simple, explainable relative-stress heuristic:
        stress_index = (avg session HR - personal baseline HR) / baseline HR

    Returns None if there isn't enough heart-rate data to compute it.
    This is coaching context, not a clinical or diagnostic measurement --
    keep any user-facing copy framed that way.
    """
    hr_values = [r.value for r in readings if r.metric_type == "heart_rate"]
    if not hr_values or not baseline_hr:
        return None

    avg_hr = statistics.mean(hr_values)
    return round((avg_hr - baseline_hr) / baseline_hr, 3)


def fetch_baseline_hr(db, user_id: str, days: int = 14) -> Optional[float]:
    """
    Shared resting-HR baseline lookup (median heart rate from readings NOT
    tied to a speaking session, over the last `days`). Used by both the
    /wearables/user/{id}/baseline-hr endpoint and the coaching flow, so
    there's exactly one definition of "baseline" in the app.
    """
    from app.models import WearableReading  # local import: avoids a hard/circular dependency at module load

    cutoff = datetime.utcnow() - timedelta(days=days)
    readings = (
        db.query(WearableReading)
        .filter(
            WearableReading.user_id == user_id,
            WearableReading.metric_type == "heart_rate",
            WearableReading.session_id.is_(None),
            WearableReading.recorded_at >= cutoff,
        )
        .all()
    )
    if not readings:
        return None

    values = sorted(r.value for r in readings)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


# --- Weighted stress index -------------------------------------------------
#
# A raw HR-vs-baseline delta treats every bpm the same. But optical (PPG)
# wrist heart-rate sensors -- what NoiseFit and almost every consumer watch
# use -- are notoriously prone to false spikes from wrist motion, a loose
# strap, or a bad skin contact. Trusting that number outright would let a
# false-high reading drive the coaching feedback just as hard as a real
# stress response.
#
# So instead of using the raw delta directly, we scale it down unless
# there's *behavioral* corroboration in the same session:
#   - a long hesitation (from speech_analysis.longest_pause_seconds)
#   - the acoustic nervousness model also flagging the voice
# and discount further if the HR trace itself looks noisy -- big
# back-to-back jumps between consecutive readings are the fingerprint of a
# motion artifact rather than a real physiological trend.
#
# Only elevated readings (raw > 0) get discounted. A below-baseline reading
# was never a "false high" in the first place, so it passes through as-is.

PAUSE_CORROBORATION_SECONDS = 2.0     # a hesitation this long is a strong hesitation signal
VOCAL_CORROBORATION_SCORE = 0.4       # matches nervousness_detector's "somewhat tense" cutoff
HR_VOLATILITY_BPM = 12.0              # avg consecutive-reading jump above this looks like sensor noise
MIN_HR_SAMPLES_FOR_VOLATILITY = 3
BASE_CONFIDENCE = 0.4                 # floor: some trust in the sensor even with zero corroboration
ESTIMATED_BASELINE_CONFIDENCE_CAP = 0.5  # cap when we had to estimate baseline instead of measuring it


@dataclass
class WeightedStressResult:
    stress_index: Optional[float]        # final, corroboration-weighted value -- use this downstream
    raw_stress_index: Optional[float]    # unweighted (avg_hr - baseline) / baseline, kept for transparency
    confidence: float                    # 0-1, how much we trust the raw HR signal as a stress cue
    reasons: List[str] = field(default_factory=list)  # short, user-facing explanation of the weighting


def compute_weighted_stress_index(
    readings: List[NormalizedReading],
    baseline_hr: Optional[float],
    longest_pause_seconds: Optional[float] = None,
    nervousness_score: Optional[float] = None,
    baseline_is_estimated: bool = False,
) -> WeightedStressResult:
    raw = compute_stress_index(readings, baseline_hr)
    if raw is None:
        return WeightedStressResult(None, None, 0.0, [])

    if raw <= 0:
        # Below baseline (or flat) -- nothing to discount.
        return WeightedStressResult(raw, raw, 1.0, [])

    reasons: List[str] = []
    confidence = BASE_CONFIDENCE

    if longest_pause_seconds is not None and longest_pause_seconds >= PAUSE_CORROBORATION_SECONDS:
        confidence += 0.3
        reasons.append(f"a {longest_pause_seconds:.1f}s pause backs up the reading")

    if nervousness_score is not None and nervousness_score >= VOCAL_CORROBORATION_SCORE:
        confidence += 0.3
        reasons.append("the vocal-tension model also flagged this session")

    hr_readings = sorted(
        (r for r in readings if r.metric_type == "heart_rate"),
        key=lambda r: r.recorded_at,
    )
    if len(hr_readings) >= MIN_HR_SAMPLES_FOR_VOLATILITY:
        diffs = [abs(b.value - a.value) for a, b in zip(hr_readings, hr_readings[1:])]
        volatility = statistics.mean(diffs)
        if volatility >= HR_VOLATILITY_BPM:
            confidence *= 0.5
            reasons.append("the heart-rate trace looked noisy (likely a motion artifact, not stress)")

    if baseline_is_estimated:
        confidence = min(confidence, ESTIMATED_BASELINE_CONFIDENCE_CAP)
        reasons.append("baseline was estimated from this session, not a measured resting HR")

    if not reasons:
        reasons.append("no pause or vocal-tension corroboration, so this reading is discounted")

    confidence = round(max(0.0, min(confidence, 1.0)), 2)
    weighted = round(raw * confidence, 3)

    return WeightedStressResult(weighted, raw, confidence, reasons)
