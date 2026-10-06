"""
SafeSight AI — Risk Fusion Engine
=================================
High-level fusion engine that combines all risk components and provides
the main interface for the real-time pipeline.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import time

from .model import HybridRiskModel, RiskAssessment, get_risk_model
from .features import FeatureExtractor, WorkerFeatures, get_feature_extractor
from risk_engine import assess_risk as rule_assess_risk
from risk_config import RISK_CONFIG, SEVERITY_COLORS


@dataclass
class FusionResult:
    """Complete fusion result for a worker."""
    worker_id: str
    worker_name: str
    tracking_id: Optional[int]
    risk_assessment: RiskAssessment
    proximity: Dict[str, Any]
    ppe_status: Dict[str, bool]
    posture: str
    timestamp: str
    voice_alert_triggered: bool
    voice_message: Optional[str]


class RiskFusionEngine:
    """
    Main fusion engine for real-time risk assessment.
    Integrates ML model, rule engine, tracking, and voice alerts.
    """

    def __init__(self):
        self.ml_model = get_risk_model()
        self.feature_extractor = get_feature_extractor()
        self.frame_count = 0
        self.last_timestamp = time.time()

    def process_worker(
        self,
        worker: Dict[str, Any],
        proximity: Dict[str, Any],
        detections: List[Dict],
        tracking_id: Optional[int] = None,
    ) -> FusionResult:
        """
        Process a single worker through the full fusion pipeline.
        """
        timestamp = time.time()
        self.frame_count += 1

        # Get ML + hybrid risk assessment
        risk_assessment = self.ml_model.assess(worker, proximity, detections, timestamp)

        # Also get rule-only assessment for comparison/fallback
        rule_result = rule_assess_risk({
            "ppe": worker.get("ppe"),
            "distance": proximity.get("distance"),
            "in_zone": proximity.get("in_zone"),
            "zone_severity": proximity.get("zone_severity"),
            "facing_hazard": proximity.get("facing_hazard"),
            "facing_away": proximity.get("facing_away"),
            "closing_speed": proximity.get("closing_speed"),
            "posture": worker.get("posture"),
        })

        # Determine if voice alert should trigger
        voice_triggered = self._should_trigger_voice(risk_assessment, worker)
        voice_message = self._generate_voice_message(risk_assessment, worker) if voice_triggered else None

        return FusionResult(
            worker_id=worker.get("id", "unknown"),
            worker_name=worker.get("name", "Unknown"),
            tracking_id=tracking_id,
            risk_assessment=risk_assessment,
            proximity=proximity,
            ppe_status=worker.get("ppe", {}),
            posture=worker.get("posture", "Normal"),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp)),
            voice_alert_triggered=voice_triggered,
            voice_message=voice_message,
        )

    def _should_trigger_voice(self, assessment: RiskAssessment, worker: Dict) -> bool:
        """Determine if a voice alert should be triggered."""
        # Trigger on HIGH or CRITICAL severity
        if assessment.severity in ("HIGH", "CRITICAL"):
            print(f"[VOICE TRACE 0] voice_triggered=True: severity={assessment.severity}, root_cause={assessment.root_cause}, worker={worker.get('id')}")
            return True
        # Trigger on WARNING if it's a new escalation
        if assessment.severity == "WARNING" and assessment.overrides:
            print(f"[VOICE TRACE 0] voice_triggered=True (WARNING with overrides): severity={assessment.severity}, root_cause={assessment.root_cause}, worker={worker.get('id')}")
            return True
        print(f"[VOICE TRACE 0] voice_triggered=False: severity={assessment.severity}, root_cause={assessment.root_cause}, overrides={assessment.overrides}, worker={worker.get('id')}")
        return False

    def _generate_voice_message(self, assessment: RiskAssessment, worker: Dict) -> str:
        """Generate a natural language voice message for the worker."""
        worker_id = worker.get("id", "Worker")
        severity = assessment.severity
        root_cause = assessment.root_cause
        zone = worker.get("current_zone", "the area")
        distance = worker.get("distance")

        # Short, clear messages for real-time safety
        if severity == "CRITICAL":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                return f"{worker_id}, critical danger. Safety helmet required in this area. Leave immediately."
            if "proximity" in root_cause.lower() or "closing" in root_cause.lower():
                return f"{worker_id}, critical danger detected. You are too close to the hazard. Leave this area immediately."
            if "posture" in root_cause.lower():
                return f"{worker_id}, critical safety violation. Unsafe posture detected in hazard zone. Move to safety immediately."
            return f"{worker_id}, critical danger detected. Please leave this area immediately."

        elif severity == "HIGH":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                missing = []
                ppe = worker.get("ppe", {})
                if not ppe.get("helmet"): missing.append("helmet")
                if not ppe.get("vest"): missing.append("vest")
                if not ppe.get("gloves"): missing.append("gloves")
                items = ", ".join(missing)
                return f"{worker_id}, {items} required in this area. Please comply immediately."
            if "proximity" in root_cause.lower():
                dist_msg = f" at {distance:.1f} meters" if distance else ""
                return f"{worker_id}, high risk. You are approaching a hazardous area{dist_msg}. Please maintain safe distance."
            if "posture" in root_cause.lower():
                return f"{worker_id}, unsafe posture detected. Please correct your posture for safety."
            return f"{worker_id}, high risk detected in {zone}. Exercise caution."

        elif severity == "WARNING":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                missing = []
                ppe = worker.get("ppe", {})
                if not ppe.get("helmet"): missing.append("helmet")
                if not ppe.get("vest"): missing.append("vest")
                if not ppe.get("gloves"): missing.append("gloves")
                items = ", ".join(missing)
                return f"{worker_id}, warning. {items} required in this zone."
            if "proximity" in root_cause.lower():
                return f"{worker_id}, warning. You are approaching a hazardous area. Please be cautious."
            return f"{worker_id}, warning. Safety violation detected in {zone}."

        return f"{worker_id}, status updated."

    def process_frame(
        self,
        workers: List[Dict[str, Any]],
        proximities: List[Dict[str, Any]],
        detections: List[Dict],
        tracking_ids: Optional[List[int]] = None,
    ) -> List[FusionResult]:
        """
        Process a full frame of workers.
        """
        results = []
        tracking_ids = tracking_ids or [None] * len(workers)

        for i, (worker, proximity) in enumerate(zip(workers, proximities)):
            tid = tracking_ids[i] if i < len(tracking_ids) else None
            result = self.process_worker(worker, proximity, detections, tid)
            results.append(result)

        return results

    def get_system_status(self) -> Dict[str, Any]:
        """Get status of the fusion engine and ML model."""
        return {
            "ml_model_loaded": self.ml_model.is_model_loaded(),
            "ml_model_info": self.ml_model.get_model_info(),
            "rule_engine": "ACTIVE",
            "feature_extractor": "ACTIVE",
            "frame_count": self.frame_count,
            "fusion_mode": "HYBRID" if self.ml_model.is_model_loaded() else "RULE_ONLY",
        }


# Singleton
_default_fusion = None


def get_fusion_engine() -> RiskFusionEngine:
    global _default_fusion
    if _default_fusion is None:
        _default_fusion = RiskFusionEngine()
    return _default_fusion