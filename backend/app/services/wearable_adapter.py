"""
Universal wearable layer.

Every device/source implements `.fetch(user_token, start, end) -> list[NormalizedReading]`.
The rest of the app (DB, coaching engine) only ever deals with NormalizedReading,
so adding a new watch is a matter of writing one adapter, not touching anything else.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List
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
