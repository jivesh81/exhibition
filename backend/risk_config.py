"""
SafeSight AI — Risk Fusion Configuration
=========================================
Group 173 Prototype

Single source of truth for ALL risk-engine weights and thresholds.
Edit these values to tune the decision engine — nothing else needs to change.
"""

RISK_CONFIG = {
    # -------------------------------------------------------------
    # PPE non-compliance points (added per missing item)
    # -------------------------------------------------------------
    "ppe": {
        "helmet": 30,
        "vest": 20,
        "gloves": 10,
    },

    # -------------------------------------------------------------
    # Proximity risk — based on distance (meters) to hazard source
    # (distance_to_hazard <= threshold) => points
    # Evaluated from the largest (closest) threshold downwards.
    # -------------------------------------------------------------
    "proximity": [
        {"max_distance": 3.0,  "points": 40, "label": "Very close to hazard (<3m)"},
        {"max_distance": 5.0,  "points": 25, "label": "Close to hazard (3-5m)"},
        {"max_distance": 10.0, "points": 10, "label": "Near hazard (5-10m)"},
    ],  # > 10m  => 0 points

    # -------------------------------------------------------------
    # Facing angle risk
    #   facing_hazard=True  -> worker looking toward the hazard
    #   facing_away=True    -> worker looking away (lower urgency)
    # -------------------------------------------------------------
    "facing": {
        "facing_hazard": 10,
        "facing_away": -5,
        "neutral": 0,
    },

    # -------------------------------------------------------------
    # Closing-speed risk (m/s toward the hazard)
    #   points = clamp((speed - free_speed) * per_ms, 0, max)
    # -------------------------------------------------------------
    "closing_speed": {
        "free_speed": 0.5,   # walking pace considered non-threatening
        "per_ms": 6.0,       # points per m/s above free speed
        "max": 15,
    },

    # -------------------------------------------------------------
    # Posture / unsafe-act risk
    # -------------------------------------------------------------
    "posture": {
        "Unsafe": 20,
        "Severe": 30,
        "Normal": 0,
    },

    # -------------------------------------------------------------
    # Zone containment bonus — entering a hazard zone raises risk
    # -------------------------------------------------------------
    "zone_bonus": {
        "danger": 10,
        "critical": 15,
        "warning": 5,
        "safe": 0,
    },

    # -------------------------------------------------------------
    # Risk classification (final score clamped to 0-100)
    #   score < threshold => class
    # -------------------------------------------------------------
    "classification": [
        {"max_score": 25,  "risk_level": "SAFE",     "severity": "SAFE"},
        {"max_score": 50,  "risk_level": "LOW",      "severity": "WARNING"},
        {"max_score": 75,  "risk_level": "HIGH",     "severity": "HIGH"},
        {"max_score": 101, "risk_level": "CRITICAL", "severity": "CRITICAL"},
    ],

    # -------------------------------------------------------------
    # Safety recommendations (per root-cause category)
    # -------------------------------------------------------------
    "recommendations": {
        "PPE NON-COMPLIANCE": "Stop worker entry until helmet/PPE compliance is restored.",
        "UNSAFE PROXIMITY":   "Supervisor intervention recommended.",
        "INATTENTIVENESS":    "Alert worker — attention directed toward hazard.",
        "HIGH CLOSING SPEED": "Warn worker and restrict access to active hazard zone.",
        "UNSAFE POSTURE":     "Review worker posture and task ergonomics.",
        "COMBINED":           "Immediate supervisor intervention recommended.",
    },
}

# Severity color mapping shared by frontend legend / overlays
SEVERITY_COLORS = {
    "SAFE":     "#22c55e",
    "WARNING":  "#f59e0b",
    "HIGH":     "#f97316",
    "CRITICAL": "#ef4444",
}
