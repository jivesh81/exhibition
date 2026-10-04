"""
SafeSight AI — Feature Extraction
=================================
Converts raw detection data into structured feature vectors for the ML risk model.

Feature vector (16 features):
    worker_id (categorical - hashed)
    helmet_present (0/1)
    vest_present (0/1)
    gloves_present (0/1)
    ppe_confidence (0-1)
    posture_encoded (0=Normal, 1=Unsafe, 2=Severe)
    posture_confidence (0-1)
    distance_to_hazard (meters, capped at 50)
    closing_speed (m/s, capped at 5)
    inside_hazard_zone (0/1)
    zone_severity_encoded (0=safe, 1=warning, 2=danger, 3=critical)
    facing_hazard (0/1)
    exposure_duration (minutes, capped at 60)
    movement_speed (m/s, capped at 5)
    hazard_confidence (0-1)
    historical_risk (0-100, rolling average)
    recent_incident_count (0-10, capped)
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import hashlib
import numpy as np


# Feature names in order (must match training)
WORKER_FEATURES = [
    "worker_id_hash",
    "helmet_present",
    "vest_present",
    "gloves_present",
    "ppe_confidence",
    "posture_encoded",
    "posture_confidence",
    "distance_to_hazard",
    "closing_speed",
    "inside_hazard_zone",
    "zone_severity_encoded",
    "facing_hazard",
    "exposure_duration",
    "movement_speed",
    "hazard_confidence",
    "historical_risk",
    "recent_incident_count",
]

# Feature metadata for validation and normalization
FEATURE_METADATA = {
    "worker_id_hash": {"type": "categorical", "min": 0, "max": 999999, "description": "Hashed worker ID"},
    "helmet_present": {"type": "binary", "min": 0, "max": 1, "description": "Helmet detected"},
    "vest_present": {"type": "binary", "min": 0, "max": 1, "description": "Safety vest detected"},
    "gloves_present": {"type": "binary", "min": 0, "max": 1, "description": "Gloves detected"},
    "ppe_confidence": {"type": "continuous", "min": 0.0, "max": 1.0, "description": "Average PPE detection confidence"},
    "posture_encoded": {"type": "categorical", "min": 0, "max": 2, "description": "Posture: 0=Normal, 1=Unsafe, 2=Severe"},
    "posture_confidence": {"type": "continuous", "min": 0.0, "max": 1.0, "description": "Posture detection confidence"},
    "distance_to_hazard": {"type": "continuous", "min": 0.0, "max": 50.0, "description": "Distance to nearest hazard (m)"},
    "closing_speed": {"type": "continuous", "min": 0.0, "max": 5.0, "description": "Speed toward hazard (m/s)"},
    "inside_hazard_zone": {"type": "binary", "min": 0, "max": 1, "description": "Inside hazard zone"},
    "zone_severity_encoded": {"type": "ordinal", "min": 0, "max": 3, "description": "Zone severity: 0=safe, 1=warning, 2=danger, 3=critical"},
    "facing_hazard": {"type": "binary", "min": 0, "max": 1, "description": "Facing toward hazard"},
    "exposure_duration": {"type": "continuous", "min": 0.0, "max": 60.0, "description": "Time in hazard zone (minutes)"},
    "movement_speed": {"type": "continuous", "min": 0.0, "max": 5.0, "description": "Worker movement speed (m/s)"},
    "hazard_confidence": {"type": "continuous", "min": 0.0, "max": 1.0, "description": "Hazard detection confidence"},
    "historical_risk": {"type": "continuous", "min": 0.0, "max": 100.0, "description": "Rolling average risk score"},
    "recent_incident_count": {"type": "continuous", "min": 0, "max": 10, "description": "Recent incidents in last hour"},
}

POSTURE_MAP = {"Normal": 0, "Unsafe": 1, "Severe": 2}
ZONE_SEVERITY_MAP = {"safe": 0, "warning": 1, "danger": 2, "critical": 3}


@dataclass
class WorkerFeatures:
    """Structured feature vector for a single worker."""
    worker_id: str
    worker_id_hash: int
    helmet_present: int
    vest_present: int
    gloves_present: int
    ppe_confidence: float
    posture_encoded: int
    posture_confidence: float
    distance_to_hazard: float
    closing_speed: float
    inside_hazard_zone: int
    zone_severity_encoded: int
    facing_hazard: int
    exposure_duration: float
    movement_speed: float
    hazard_confidence: float
    historical_risk: float
    recent_incident_count: int

    def to_array(self) -> np.ndarray:
        """Convert to numpy array in the correct order."""
        return np.array([
            self.worker_id_hash,
            self.helmet_present,
            self.vest_present,
            self.gloves_present,
            self.ppe_confidence,
            self.posture_encoded,
            self.posture_confidence,
            self.distance_to_hazard,
            self.closing_speed,
            self.inside_hazard_zone,
            self.zone_severity_encoded,
            self.facing_hazard,
            self.exposure_duration,
            self.movement_speed,
            self.hazard_confidence,
            self.historical_risk,
            self.recent_incident_count,
        ], dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: getattr(self, k) for k in WORKER_FEATURES}


class FeatureExtractor:
    """
    Extracts structured features from raw detection + tracking + zone data.
    Maintains worker history for temporal features.
    """

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.worker_history: Dict[str, List[Dict]] = {}  # worker_id -> list of feature dicts
        self.worker_positions: Dict[str, List[tuple]] = {}  # worker_id -> [(x, y, timestamp), ...]

    def _hash_worker_id(self, worker_id: str) -> int:
        """Create a stable hash for worker ID (for categorical encoding)."""
        return int(hashlib.md5(worker_id.encode()).hexdigest()[:6], 16)

    def _get_ppe_confidence(self, ppe: Dict, detections: List[Dict]) -> float:
        """Calculate average PPE detection confidence."""
        if not detections:
            return 0.5  # default moderate confidence
        confs = [d.get("confidence", 0.5) for d in detections if d.get("id") == ppe.get("worker_id")]
        return float(np.mean(confs)) if confs else 0.5

    def _get_movement_speed(self, worker_id: str, x: float, y: float, timestamp: float) -> float:
        """Calculate movement speed from position history."""
        if worker_id not in self.worker_positions:
            self.worker_positions[worker_id] = []
        history = self.worker_positions[worker_id]
        history.append((x, y, timestamp))
        # Keep only last 10 positions
        if len(history) > 10:
            history.pop(0)
        if len(history) < 2:
            return 0.0
        # Calculate speed from last two positions
        x1, y1, t1 = history[-2]
        x2, y2, t2 = history[-1]
        dt = max(t2 - t1, 0.001)
        dist = np.hypot(x2 - x1, y2 - y1)
        # Convert normalized coords to meters (rough approximation)
        return float(min(dist * 30.0 / dt, 5.0))  # cap at 5 m/s

    def _get_historical_risk(self, worker_id: str) -> float:
        """Get rolling average risk score for worker."""
        if worker_id not in self.worker_history:
            return 0.0
        history = self.worker_history[worker_id]
        if not history:
            return 0.0
        risks = [h.get("risk_score", 0) for h in history[-20:]]  # last 20 frames
        return float(np.mean(risks))

    def _get_recent_incidents(self, worker_id: str, db_query_func=None) -> int:
        """Get recent incident count (last hour)."""
        # This would query the database in production
        # For now, return from history
        if worker_id not in self.worker_history:
            return 0
        # Count incidents with severity >= HIGH in recent history
        count = 0
        for h in self.worker_history[worker_id][-50:]:
            if h.get("severity") in ("HIGH", "CRITICAL"):
                count += 1
        return min(count, 10)

    def extract(
        self,
        worker: Dict[str, Any],
        proximity: Dict[str, Any],
        detections: List[Dict],
        timestamp: float,
        db_query_func=None,
    ) -> WorkerFeatures:
        """
        Extract feature vector for a worker.

        Args:
            worker: Worker state dict with id, name, ppe, posture, x, y, facing_vector
            proximity: ProximityProvider output with distance, closing_speed, in_zone, zone_severity, facing_hazard
            detections: Raw detection results from PPE/pose providers
            timestamp: Current timestamp
            db_query_func: Optional function to query database for historical data
        """
        worker_id = worker.get("id", "unknown")
        ppe = worker.get("ppe") or {}
        posture = worker.get("posture", "Normal")

        # PPE features
        helmet = int(bool(ppe.get("helmet", True)))
        vest = int(bool(ppe.get("vest", True)))
        gloves = int(bool(ppe.get("gloves", True)))
        ppe_conf = self._get_ppe_confidence({"worker_id": worker_id}, detections)

        # Posture features
        posture_encoded = POSTURE_MAP.get(posture, 0)
        posture_conf = 0.8 if posture != "Normal" else 0.9  # higher confidence for normal

        # Proximity features
        distance = proximity.get("distance")
        if distance is None:
            distance = 50.0
        distance = min(float(distance), 50.0)
        closing_speed = min(float(proximity.get("closing_speed") or 0.0), 5.0)
        in_zone = int(bool(proximity.get("in_zone", False)))
        zone_sev = ZONE_SEVERITY_MAP.get((proximity.get("zone_severity") or "safe").lower(), 0)
        facing_hazard = int(bool(proximity.get("facing_hazard", False)))

        # Exposure duration
        exposure = float(worker.get("exposure_time") or 0.0)
        exposure = min(exposure, 60.0)

        # Movement speed
        x = float(worker.get("x", 0.5))
        y = float(worker.get("y", 0.5))
        movement_speed = self._get_movement_speed(worker_id, x, y, timestamp)

        # Hazard confidence (from detection confidence)
        hazard_conf = 0.7  # default
        if detections:
            for d in detections:
                if d.get("id") == worker_id:
                    hazard_conf = float(d.get("confidence", 0.7))
                    break

        # Historical features
        hist_risk = self._get_historical_risk(worker_id)
        recent_inc = self._get_recent_incidents(worker_id, db_query_func)

        features = WorkerFeatures(
            worker_id=worker_id,
            worker_id_hash=self._hash_worker_id(worker_id),
            helmet_present=helmet,
            vest_present=vest,
            gloves_present=gloves,
            ppe_confidence=ppe_conf,
            posture_encoded=posture_encoded,
            posture_confidence=posture_conf,
            distance_to_hazard=distance,
            closing_speed=closing_speed,
            inside_hazard_zone=in_zone,
            zone_severity_encoded=zone_sev,
            facing_hazard=facing_hazard,
            exposure_duration=exposure,
            movement_speed=movement_speed,
            hazard_confidence=hazard_conf,
            historical_risk=hist_risk,
            recent_incident_count=recent_inc,
        )

        # Update history
        if worker_id not in self.worker_history:
            self.worker_history[worker_id] = []
        self.worker_history[worker_id].append({
            "risk_score": 0,  # will be updated after risk assessment
            "severity": "SAFE",
            "timestamp": timestamp,
        })
        if len(self.worker_history[worker_id]) > self.max_history:
            self.worker_history[worker_id].pop(0)

        return features

    def update_risk_history(self, worker_id: str, risk_score: float, severity: str):
        """Update the risk score in history after assessment."""
        if worker_id in self.worker_history and self.worker_history[worker_id]:
            self.worker_history[worker_id][-1]["risk_score"] = risk_score
            self.worker_history[worker_id][-1]["severity"] = severity

    def clear_worker(self, worker_id: str):
        """Clear history for a worker (e.g., when they leave the scene)."""
        self.worker_history.pop(worker_id, None)
        self.worker_positions.pop(worker_id, None)

    def validate_features(self, features: WorkerFeatures) -> List[str]:
        """Validate feature values against metadata. Returns list of warnings."""
        warnings = []
        for fname in WORKER_FEATURES:
            val = getattr(features, fname)
            meta = FEATURE_METADATA[fname]
            if val < meta["min"] or val > meta["max"]:
                warnings.append(f"{fname}: value {val} outside range [{meta['min']}, {meta['max']}]")
        return warnings


# Singleton instance for the pipeline
_default_extractor = None


def get_feature_extractor() -> FeatureExtractor:
    """Get or create the default feature extractor."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = FeatureExtractor()
    return _default_extractor