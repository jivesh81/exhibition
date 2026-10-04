"""
SafeSight AI — Hybrid Risk Model
================================
Combines ML-based risk prediction with deterministic safety rules.
The ML model provides a probability, while rules enforce hard safety constraints.
"""

import os
import json
import joblib
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    lgb = None

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    xgb = None

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from .features import FeatureExtractor, WorkerFeatures, WORKER_FEATURES, FEATURE_METADATA, get_feature_extractor


# Model artifacts directory
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

MODEL_PATH = ARTIFACTS_DIR / "hybrid_risk_model.pkl"
SCALER_PATH = ARTIFACTS_DIR / "feature_scaler.pkl"
METADATA_PATH = ARTIFACTS_DIR / "model_metadata.json"


@dataclass
class ModelMetadata:
    """Metadata about the trained model."""
    model_type: str
    version: str
    feature_version: str
    training_dataset: str
    training_date: str
    n_features: int
    feature_names: List[str]
    metrics: Dict[str, float]
    thresholds: Dict[str, float]


@dataclass
class RiskAssessment:
    """Complete risk assessment output."""
    ml_probability: float
    ml_risk_score: float  # 0-100
    rule_risk_score: float  # 0-100
    temporal_risk_score: float  # 0-100
    final_risk_score: float  # 0-100
    severity: str  # SAFE, WARNING, HIGH, CRITICAL
    risk_level: str  # SAFE, LOW, HIGH, CRITICAL
    root_cause: str
    recommendation: str
    breakdown: List[Dict[str, Any]]
    overrides: List[str]  # hard safety rule overrides applied
    model_version: str
    feature_version: str


class HybridRiskModel:
    """
    Hybrid ML + Rule-based risk model.

    Architecture:
    1. ML model predicts probability of unsafe event (0-1)
    2. Rule engine computes deterministic risk score (0-100)
    3. Temporal component adds exposure/escalation risk
    4. Fusion layer combines with hard overrides
    """

    def __init__(self, model_path: Optional[str] = None, scaler_path: Optional[str] = None):
        self.model = None
        self.scaler = None
        self.metadata: Optional[ModelMetadata] = None
        self.feature_extractor = get_feature_extractor()
        self.model_path = model_path or str(MODEL_PATH)
        self.scaler_path = scaler_path or str(SCALER_PATH)

        # Classification thresholds (matching risk_config.py)
        self.classification = [
            {"max_score": 25, "risk_level": "SAFE", "severity": "SAFE"},
            {"max_score": 50, "risk_level": "LOW", "severity": "WARNING"},
            {"max_score": 75, "risk_level": "HIGH", "severity": "HIGH"},
            {"max_score": 101, "risk_level": "CRITICAL", "severity": "CRITICAL"},
        ]

        # Hard safety override rules
        self.override_rules = [
            {
                "name": "critical_zone_no_helmet",
                "condition": lambda f, r: f.inside_hazard_zone and f.zone_severity_encoded >= 3 and not f.helmet_present,
                "severity": "CRITICAL",
                "message": "Worker in critical zone without helmet",
            },
            {
                "name": "critical_zone_proximity",
                "condition": lambda f, r: f.inside_hazard_zone and f.zone_severity_encoded >= 3 and f.distance_to_hazard < 2.0,
                "severity": "CRITICAL",
                "message": "Worker critically close to hazard in critical zone",
            },
            {
                "name": "high_closing_speed_critical_zone",
                "condition": lambda f, r: f.closing_speed > 2.0 and f.zone_severity_encoded >= 2 and f.inside_hazard_zone,
                "severity": "CRITICAL",
                "message": "High closing speed in hazard zone",
            },
            {
                "name": "prolonged_exposure_critical",
                "condition": lambda f, r: f.exposure_duration > 10.0 and f.zone_severity_encoded >= 3,
                "severity": "CRITICAL",
                "message": "Prolonged exposure in critical zone",
            },
            {
                "name": "multiple_violations",
                "condition": lambda f, r: (int(not f.helmet_present) + int(not f.vest_present) +
                                           int(f.posture_encoded >= 1) + int(f.inside_hazard_zone)) >= 3,
                "severity": "HIGH",
                "message": "Multiple simultaneous safety violations",
            },
            {
                "name": "no_helmet_in_danger_zone",
                "condition": lambda f, r: not f.helmet_present and f.zone_severity_encoded >= 2 and f.inside_hazard_zone,
                "severity": "HIGH",
                "message": "No helmet in danger zone",
            },
            {
                "name": "rapid_approach_hazard",
                "condition": lambda f, r: f.closing_speed > 1.5 and f.distance_to_hazard < 5.0,
                "severity": "HIGH",
                "message": "Rapid approach to hazard",
            },
        ]

        self._load_model()

    def _load_model(self):
        """Load trained model and scaler if available."""
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                with open(METADATA_PATH, "r") as f:
                    meta_dict = json.load(f)
                    self.metadata = ModelMetadata(**meta_dict)
                print(f"[HybridRiskModel] Loaded model: {self.metadata.model_type} v{self.metadata.version}")
            except Exception as e:
                print(f"[HybridRiskModel] Failed to load model: {e}")
                self.model = None
                self.scaler = None
        else:
            print("[HybridRiskModel] No trained model found, using rule-only mode")

    def _save_model(self, model, scaler, metadata: ModelMetadata):
        """Save model, scaler, and metadata."""
        joblib.dump(model, self.model_path)
        joblib.dump(scaler, self.scaler_path)
        with open(METADATA_PATH, "w") as f:
            json.dump(asdict(metadata), f, indent=2)
        self.model = model
        self.scaler = scaler
        self.metadata = metadata
        print(f"[HybridRiskModel] Saved model to {self.model_path}")

    def _classify_score(self, score: float) -> Tuple[str, str]:
        """Map 0-100 score to risk level and severity."""
        for band in self.classification:
            if score < band["max_score"]:
                return band["risk_level"], band["severity"]
        return "CRITICAL", "CRITICAL"

    def _apply_overrides(self, features: WorkerFeatures, ml_prob: float, rule_score: float) -> Tuple[float, str, str, List[str]]:
        """
        Apply hard safety overrides. Returns (final_score, severity, risk_level, overrides_applied).
        """
        overrides = []
        final_score = rule_score
        final_severity = None
        final_risk_level = None

        for rule in self.override_rules:
            if rule["condition"](features, rule_score):
                overrides.append(rule["name"])
                # Override to at least the rule's severity
                target_severity = rule["severity"]
                if final_severity is None or self._severity_rank(target_severity) > self._severity_rank(final_severity):
                    final_severity = target_severity
                    # Set score to minimum for that severity
                    if target_severity == "CRITICAL":
                        final_score = max(final_score, 85)
                    elif target_severity == "HIGH":
                        final_score = max(final_score, 65)
                    elif target_severity == "WARNING":
                        final_score = max(final_score, 35)

        if final_severity is None:
            final_risk_level, final_severity = self._classify_score(final_score)
        else:
            # Find risk level for the overridden severity
            for band in self.classification:
                if band["severity"] == final_severity:
                    final_risk_level = band["risk_level"]
                    break

        return final_score, final_severity, final_risk_level, overrides

    def _severity_rank(self, severity: str) -> int:
        ranks = {"SAFE": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}
        return ranks.get(severity, 0)

    def _compute_rule_score(self, features: WorkerFeatures) -> Tuple[float, List[Dict], str, str]:
        """
        Compute deterministic rule-based risk score (replicates risk_engine logic).
        Returns (score, breakdown, root_cause, recommendation).
        """
        from risk_config import RISK_CONFIG
        factors = []

        # PPE risk
        ppe_weights = RISK_CONFIG["ppe"]
        ppe_labels = {"helmet": "Helmet missing", "vest": "Safety vest missing", "gloves": "Gloves missing"}
        ppe_pts = 0
        for item, weight in ppe_weights.items():
            ppe_val = getattr(features, f"{item}_present", 1)
            if not ppe_val:
                ppe_pts += weight
                factors.append({"factor": ppe_labels.get(item, item.capitalize() + " missing"),
                                "category": "ppe", "points": weight})

        # Proximity risk
        prox_pts = 0
        distance = features.distance_to_hazard
        if distance is not None:
            for band in RISK_CONFIG["proximity"]:
                if distance <= band["max_distance"]:
                    prox_pts = band["points"]
                    factors.append({"factor": band["label"] + f" ({distance:.1f}m)",
                                    "category": "proximity", "points": band["points"]})
                    break
        if features.inside_hazard_zone and prox_pts == 0:
            prox_pts = 5
            factors.append({"factor": "Inside hazard zone (far from source)",
                            "category": "proximity", "points": 5})

        # Facing risk
        face_pts = 0
        if features.facing_hazard:
            face_pts = RISK_CONFIG["facing"]["facing_hazard"]
            factors.append({"factor": "Facing hazard", "category": "facing", "points": face_pts})

        # Closing speed risk
        speed_pts = 0
        speed = features.closing_speed
        if speed > 0:
            cfg = RISK_CONFIG["closing_speed"]
            pts = min(cfg["max"], max(0, round((speed - cfg["free_speed"]) * cfg["per_ms"])))
            if pts > 0:
                speed_pts = pts
                label = "High closing speed" if speed >= 1.5 else "Closing speed increasing"
                factors.append({"factor": f"{label} ({speed:.1f} m/s)",
                                "category": "closing_speed", "points": pts})

        # Posture risk
        pos_pts = 0
        posture_map = {0: "Normal", 1: "Unsafe", 2: "Severe"}
        posture_str = posture_map.get(features.posture_encoded, "Normal")
        pos_pts = RISK_CONFIG["posture"].get(posture_str, 0)
        if pos_pts:
            factors.append({"factor": f"{posture_str} posture", "category": "posture", "points": pos_pts})

        # Zone bonus
        zone_pts = 0
        if features.inside_hazard_zone:
            zone_sev_map = {1: "warning", 2: "danger", 3: "critical"}
            zone_str = zone_sev_map.get(features.zone_severity_encoded, "safe")
            zone_pts = RISK_CONFIG["zone_bonus"].get(zone_str, 0)
            if zone_pts:
                factors.append({"factor": f"Inside {zone_str.upper()} hazard zone",
                                "category": "zone", "points": zone_pts})

        raw = ppe_pts + prox_pts + face_pts + speed_pts + pos_pts + zone_pts
        score = max(0, min(100, raw))

        # Root cause
        tag_map = {
            "ppe": "PPE NON-COMPLIANCE",
            "proximity": "UNSAFE PROXIMITY",
            "zone": "UNSAFE PROXIMITY",
            "facing": "INATTENTIVENESS",
            "closing_speed": "HIGH CLOSING SPEED",
            "posture": "UNSAFE POSTURE",
        }
        weights = {}
        for f in factors:
            tag = tag_map[f["category"]]
            weights[tag] = weights.get(tag, 0) + f["points"]
        ordered = sorted(weights.items(), key=lambda kv: -kv[1])
        tags = [tag for tag, _ in ordered]
        root_cause = " + ".join(tags) if len(tags) >= 2 else (tags[0] if tags else "NO RISK DETECTED")

        # Recommendation
        recs = RISK_CONFIG["recommendations"]
        if len(factors) >= 3:
            recommendation = recs["COMBINED"]
        else:
            recommendation = recs.get(root_cause, recs["COMBINED"])

        return score, factors, root_cause, recommendation

    def _compute_temporal_risk(self, features: WorkerFeatures) -> float:
        """Compute temporal/escalation risk component."""
        temporal = 0.0
        # Exposure duration escalation
        if features.exposure_duration > 5:
            temporal += min(15, features.exposure_duration * 1.5)
        # Historical risk escalation
        if features.historical_risk > 50:
            temporal += min(10, (features.historical_risk - 50) * 0.2)
        # Recent incidents
        temporal += features.recent_incident_count * 3
        return min(temporal, 30)  # cap temporal component

    def predict_ml(self, features: WorkerFeatures) -> float:
        """
        Get ML model probability (0-1).
        Returns 0.5 if no model loaded (neutral).
        """
        if self.model is None or self.scaler is None:
            return 0.5  # neutral probability when no model

        try:
            X = features.to_array().reshape(1, -1)
            X_scaled = self.scaler.transform(X)
            if hasattr(self.model, "predict_proba"):
                prob = self.model.predict_proba(X_scaled)[0, 1]  # probability of unsafe
            else:
                # For models without predict_proba, use decision function
                decision = self.model.decision_function(X_scaled)[0]
                prob = 1 / (1 + np.exp(-decision))  # sigmoid
            return float(np.clip(prob, 0.0, 1.0))
        except Exception as e:
            print(f"[HybridRiskModel] ML prediction failed: {e}")
            return 0.5

    def assess(self, worker: Dict[str, Any], proximity: Dict[str, Any],
               detections: List[Dict], timestamp: float) -> RiskAssessment:
        """
        Full hybrid risk assessment for a worker.
        """
        # Extract features
        features = self.feature_extractor.extract(worker, proximity, detections, timestamp)

        # ML prediction
        ml_prob = self.predict_ml(features)
        ml_risk = ml_prob * 100  # convert to 0-100 scale

        # Rule-based score
        rule_score, breakdown, root_cause, recommendation = self._compute_rule_score(features)

        # Temporal risk
        temporal_risk = self._compute_temporal_risk(features)

        # Fusion: weighted combination (ML 30%, Rules 50%, Temporal 20%)
        # But rules can override via hard constraints
        fused_score = 0.3 * ml_risk + 0.5 * rule_score + 0.2 * temporal_risk
        fused_score = max(0, min(100, fused_score))

        # Apply hard overrides
        final_score, severity, risk_level, overrides = self._apply_overrides(
            features, ml_prob, fused_score
        )

        # Build final breakdown with ML component
        final_breakdown = breakdown + [
            {"factor": f"ML Risk Probability ({ml_prob:.2f})", "category": "ml", "points": round(ml_risk * 0.3, 1)},
            {"factor": f"Rule-Based Risk", "category": "rule", "points": round(rule_score * 0.5, 1)},
            {"factor": f"Temporal Risk", "category": "temporal", "points": round(temporal_risk * 0.2, 1)},
        ]

        if overrides:
            final_breakdown.append({
                "factor": f"HARD OVERRIDE: {', '.join(overrides)}",
                "category": "override",
                "points": final_score - fused_score,
            })

        # Update feature extractor history
        self.feature_extractor.update_risk_history(features.worker_id, final_score, severity)

        model_version = self.metadata.version if self.metadata else "rule-only"
        feature_version = self.metadata.feature_version if self.metadata else "1"

        return RiskAssessment(
            ml_probability=ml_prob,
            ml_risk_score=round(ml_risk, 1),
            rule_risk_score=round(rule_score, 1),
            temporal_risk_score=round(temporal_risk, 1),
            final_risk_score=round(final_score, 1),
            severity=severity,
            risk_level=risk_level,
            root_cause=root_cause,
            recommendation=recommendation,
            breakdown=final_breakdown,
            overrides=overrides,
            model_version=model_version,
            feature_version=feature_version,
        )

    def is_model_loaded(self) -> bool:
        return self.model is not None and self.scaler is not None

    def get_model_info(self) -> Dict[str, Any]:
        if self.metadata:
            return asdict(self.metadata)
        return {
            "model_type": "rule-only",
            "version": "1.0",
            "feature_version": "1",
            "training_dataset": "none",
            "training_date": "none",
            "n_features": len(WORKER_FEATURES),
            "feature_names": WORKER_FEATURES,
            "metrics": {},
            "thresholds": {},
        }


# Singleton instance
_default_model = None


def get_risk_model() -> HybridRiskModel:
    global _default_model
    if _default_model is None:
        _default_model = HybridRiskModel()
    return _default_model