"""
SafeSight AI — Safety Event Engine
==================================
Generates structured safety events from risk assessments with temporal stability.
"""
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import defaultdict
import threading

from app.core.logging import EVENT_LOGGER


class EventType(Enum):
    NO_HELMET = "NO_HELMET"
    NO_VEST = "NO_VEST"
    NO_SAFETY_SHOES = "NO_SAFETY_SHOES"
    DANGEROUS_ZONE = "DANGEROUS_ZONE"
    PROXIMITY_HAZARD = "PROXIMITY_HAZARD"
    FALL_DETECTED = "FALL_DETECTED"
    UNSAFE_POSTURE = "UNSAFE_POSTURE"
    HIGH_RISK_BEHAVIOR = "HIGH_RISK_BEHAVIOR"
    MULTIPLE_VIOLATIONS = "MULTIPLE_VIOLATIONS"
    CRITICAL_HAZARD = "CRITICAL_HAZARD"
    ZONE_CLEAR = "ZONE_CLEAR"
    SAFE_EVENT = "SAFE_EVENT"


class Severity(Enum):
    SAFE = "SAFE"
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SafetyEvent:
    """A structured safety event."""
    event_id: str
    timestamp: float
    worker_id: str
    worker_name: str
    event_type: str
    severity: str
    risk_score: float
    confidence: float
    zone_id: Optional[str]
    zone_name: Optional[str]
    position: Dict[str, float]
    evidence: Dict[str, Any]
    root_cause: str
    source: str
    tracking_id: Optional[int] = None
    status: str = "ACTIVE"


class TemporalConfirmator:
    """
    Implements temporal confirmation for safety events.
    Events must be detected continuously for N frames before confirmation.
    """

    def __init__(self, confirmation_frames: int = 3, deconfirmation_frames: int = 5):
        self.confirmation_frames = confirmation_frames
        self.deconfirmation_frames = deconfirmation_frames
        self.detection_history: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.confirmed_events: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def update(self, worker_id: str, event_type: str, detected: bool) -> Optional[str]:
        """
        Update detection state for a worker/event_type.
        Returns 'CONFIRMED', 'DECONFIRMED', or None.
        """
        with self._lock:
            key = f"{worker_id}:{event_type}"

            if detected:
                self.detection_history[key][event_type] += 1
                # Reset deconfirmation counter
                self.detection_history[key]["_deconfirm"] = 0

                if self.detection_history[key][event_type] >= self.confirmation_frames:
                    if key not in self.confirmed_events:
                        self.confirmed_events[key] = {
                            "event_type": event_type,
                            "worker_id": worker_id,
                            "confirmed_at": time.time(),
                            "frames": self.detection_history[key][event_type],
                        }
                        return "CONFIRMED"
            else:
                # Increment deconfirmation counter
                self.detection_history[key]["_deconfirm"] += 1
                self.detection_history[key][event_type] = max(0, self.detection_history[key][event_type] - 1)

                if self.detection_history[key]["_deconfirm"] >= self.deconfirmation_frames:
                    if key in self.confirmed_events:
                        del self.confirmed_events[key]
                        return "DECONFIRMED"

            return None

    def is_confirmed(self, worker_id: str, event_type: str) -> bool:
        with self._lock:
            key = f"{worker_id}:{event_type}"
            return key in self.confirmed_events

    def get_confirmed_events(self, worker_id: str) -> List[str]:
        with self._lock:
            return [
                data["event_type"]
                for key, data in self.confirmed_events.items()
                if data["worker_id"] == worker_id
            ]

    def clear_worker(self, worker_id: str):
        with self._lock:
            keys_to_delete = [k for k in self.detection_history if k.startswith(f"{worker_id}:")]
            for k in keys_to_delete:
                del self.detection_history[k]
            keys_to_delete = [k for k in self.confirmed_events if self.confirmed_events[k]["worker_id"] == worker_id]
            for k in keys_to_delete:
                del self.confirmed_events[k]


class SafetyEventEngine:
    """
    Main safety event engine.
    Converts risk assessments into structured safety events with temporal stability.
    """

    def __init__(
        self,
        confirmation_frames: int = 3,
        deconfirmation_frames: int = 5,
    ):
        self.temporal = TemporalConfirmator(confirmation_frames, deconfirmation_frames)
        self.worker_states: Dict[str, Dict[str, Any]] = {}
        self.active_events: Dict[str, SafetyEvent] = {}  # event_id -> event
        self.event_history: List[SafetyEvent] = []
        self._lock = threading.RLock()

        # Event type mapping from root causes
        self.root_cause_to_event_type = {
            "PPE NON-COMPLIANCE": self._map_ppe_violation,
            "UNSAFE PROXIMITY": lambda e: EventType.PROXIMITY_HAZARD.value,
            "INATTENTIVENESS": lambda e: EventType.DANGEROUS_ZONE.value,
            "HIGH CLOSING SPEED": lambda e: EventType.PROXIMITY_HAZARD.value,
            "UNSAFE POSTURE": lambda e: EventType.UNSAFE_POSTURE.value,
            "NO RISK DETECTED": lambda e: EventType.SAFE_EVENT.value,
        }

    def _map_ppe_violation(self, evidence: Dict) -> str:
        """Map PPE violation to specific event type."""
        ppe = evidence.get("ppe", {})
        if not ppe.get("helmet", True):
            return EventType.NO_HELMET.value
        if not ppe.get("vest", True):
            return EventType.NO_VEST.value
        if not ppe.get("gloves", True):
            return EventType.NO_SAFETY_SHOES.value
        return EventType.MULTIPLE_VIOLATIONS.value

    def process_risk_assessment(
        self,
        worker: Dict[str, Any],
        risk_assessment: Any,  # RiskAssessment from fusion engine
        proximity: Dict[str, Any],
        source: str = "realtime",
    ) -> List[SafetyEvent]:
        """
        Process a risk assessment and generate safety events.
        Returns list of newly confirmed events.
        """
        worker_id = worker.get("id", "unknown")
        worker_name = worker.get("name", worker_id)
        timestamp = time.time()

        # Get or create worker state
        with self._lock:
            if worker_id not in self.worker_states:
                self.worker_states[worker_id] = {
                    "last_severity": "SAFE",
                    "last_event_types": set(),
                    "in_zone": False,
                    "zone_name": None,
                }
            state = self.worker_states[worker_id]

        # Determine event type from risk assessment
        event_type = self._determine_event_type(risk_assessment, proximity)
        severity = risk_assessment.severity
        root_cause = risk_assessment.root_cause

        # Update temporal confirmation
        is_hazard = severity in ("WARNING", "HIGH", "CRITICAL")
        temporal_result = self.temporal.update(worker_id, event_type, is_hazard)

        # Check for zone clear
        was_in_zone = state.get("in_zone", False)
        now_in_zone = proximity.get("in_zone", False)
        zone_name = proximity.get("zone") or proximity.get("zone_name")

        events = []

        if temporal_result == "CONFIRMED":
            # Create new confirmed event
            event = SafetyEvent(
                event_id=f"{worker_id}-{event_type}-{int(timestamp * 1000)}",
                timestamp=timestamp,
                worker_id=worker_id,
                worker_name=worker_name,
                event_type=event_type,
                severity=severity,
                risk_score=risk_assessment.final_risk_score,
                confidence=risk_assessment.ml_probability if hasattr(risk_assessment, 'ml_probability') else 0.8,
                zone_id=proximity.get("zone_id"),
                zone_name=zone_name,
                position={"x": worker.get("x", 0), "y": worker.get("y", 0)},
                evidence={
                    "ppe": worker.get("ppe", {}),
                    "distance": proximity.get("distance"),
                    "closing_speed": proximity.get("closing_speed"),
                    "facing_hazard": proximity.get("facing_hazard"),
                    "posture": worker.get("posture"),
                    "in_zone": now_in_zone,
                },
                root_cause=root_cause,
                source=source,
                tracking_id=worker.get("tracking_id"),
            )

            with self._lock:
                self.active_events[event.event_id] = event
                self.event_history.append(event)
                state["last_severity"] = severity
                state["last_event_types"].add(event_type)
                state["in_zone"] = now_in_zone
                state["zone_name"] = zone_name

            EVENT_LOGGER.info(
                f"Event confirmed: {event_type}",
                event_id=event.event_id,
                worker_id=worker_id,
                severity=severity,
                risk_score=risk_assessment.final_risk_score,
            )
            events.append(event)

        elif temporal_result == "DECONFIRMED":
            # Event cleared - generate zone clear if was in zone
            if was_in_zone and not now_in_zone:
                clear_event = SafetyEvent(
                    event_id=f"{worker_id}-ZONE_CLEAR-{int(timestamp * 1000)}",
                    timestamp=timestamp,
                    worker_id=worker_id,
                    worker_name=worker_name,
                    event_type=EventType.ZONE_CLEAR.value,
                    severity="SAFE",
                    risk_score=0,
                    confidence=1.0,
                    zone_id=proximity.get("zone_id"),
                    zone_name=state.get("zone_name"),
                    position={"x": worker.get("x", 0), "y": worker.get("y", 0)},
                    evidence={},
                    root_cause="ZONE CLEAR",
                    source=source,
                    tracking_id=worker.get("tracking_id"),
                )
                events.append(clear_event)
                EVENT_LOGGER.info(f"Zone clear for worker {worker_id}", zone=state.get("zone_name"))

            with self._lock:
                state["in_zone"] = now_in_zone
                state["last_severity"] = "SAFE"

        # Update zone state
        with self._lock:
            state["in_zone"] = now_in_zone
            if zone_name:
                state["zone_name"] = zone_name

        return events

    def _determine_event_type(self, risk_assessment: Any, proximity: Dict[str, Any]) -> str:
        """Determine event type from risk assessment."""
        root_cause = risk_assessment.root_cause
        severity = risk_assessment.severity

        # Check for critical hazard overrides
        if hasattr(risk_assessment, 'overrides') and risk_assessment.overrides:
            for override in risk_assessment.overrides:
                if "critical_zone_no_helmet" in override:
                    return EventType.CRITICAL_HAZARD.value
                if "critical_zone_proximity" in override:
                    return EventType.CRITICAL_HAZARD.value
                if "multiple_violations" in override:
                    return EventType.MULTIPLE_VIOLATIONS.value

        # Map from root cause
        for cause_key, mapper in self.root_cause_to_event_type.items():
            if cause_key in root_cause:
                return mapper(risk_assessment.__dict__ if hasattr(risk_assessment, '__dict__') else {})

        # Fallback based on severity and proximity
        if severity == "CRITICAL":
            if proximity.get("in_zone"):
                return EventType.DANGEROUS_ZONE.value
            return EventType.CRITICAL_HAZARD.value
        elif severity == "HIGH":
            if proximity.get("in_zone"):
                return EventType.DANGEROUS_ZONE.value
            return EventType.PROXIMITY_HAZARD.value
        elif severity == "WARNING":
            return EventType.PROXIMITY_HAZARD.value

        return EventType.SAFE_EVENT.value

    def get_worker_state(self, worker_id: str) -> Dict[str, Any]:
        with self._lock:
            return self.worker_states.get(worker_id, {})

    def get_active_events(self, worker_id: str = None) -> List[SafetyEvent]:
        with self._lock:
            if worker_id:
                return [e for e in self.active_events.values() if e.worker_id == worker_id]
            return list(self.active_events.values())

    def clear_worker(self, worker_id: str):
        """Clear all state for a worker (when they leave the scene)."""
        with self._lock:
            self.temporal.clear_worker(worker_id)
            self.worker_states.pop(worker_id, None)
            # Remove active events for this worker
            to_remove = [eid for eid, e in self.active_events.items() if e.worker_id == worker_id]
            for eid in to_remove:
                del self.active_events[eid]

    def get_status(self) -> Dict:
        with self._lock:
            return {
                "active_events": len(self.active_events),
                "tracked_workers": len(self.worker_states),
                "temporal_confirmed": sum(1 for _ in self.temporal.confirmed_events),
            }


# Singleton instance
_default_engine = None


def get_safety_event_engine() -> SafetyEventEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = SafetyEventEngine()
    return _default_engine