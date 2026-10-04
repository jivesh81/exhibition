"""
SafeSight AI — Risk Fusion Engine (rule-based decision layer)
=============================================================
Group 173 Prototype

This is the CORE INNOVATION of the project:
    PPE + PROXIMITY + FACING ANGLE + CLOSING SPEED + POSTURE
        -> ONE explainable risk score -> root-cause tag -> safety decision.

Every score is actually computed here from detection data (never hardcoded),
and every point in the final score is traceable to a named factor.
"""

from risk_config import RISK_CONFIG

FACTORS = RISK_CONFIG


def _classify(score: float):
    """Map a 0-100 score to (risk_level, severity) using configured thresholds."""
    for band in FACTORS["classification"]:
        if score < band["max_score"]:
            return band["risk_level"], band["severity"]
    return "CRITICAL", "CRITICAL"


def _ppe_risk(ppe: dict, factors: list):
    """Sum configured points for each missing PPE item."""
    weights = FACTORS["ppe"]
    total = 0
    labels = {"helmet": "Helmet missing", "vest": "Safety vest missing", "gloves": "Gloves missing"}
    for item, weight in weights.items():
        if ppe and not ppe.get(item, True):
            total += weight
            factors.append({"factor": labels.get(item, item.capitalize() + " missing"),
                            "category": "ppe", "points": weight})
    return total


def _proximity_risk(distance, in_zone: bool, factors: list):
    """Distance-band risk to the hazard source (closest band wins)."""
    if distance is None:
        return 0
    for band in FACTORS["proximity"]:
        if distance <= band["max_distance"]:
            factors.append({"factor": band["label"] + f" ({distance:.1f}m)",
                            "category": "proximity", "points": band["points"]})
            return band["points"]
    if in_zone:
        factors.append({"factor": "Inside hazard zone (far from source)",
                        "category": "proximity", "points": 5})
        return 5
    return 0


def _facing_risk(facing_hazard: bool, facing_away: bool, factors: list):
    """Facing the hazard raises urgency; facing away lowers it."""
    if facing_hazard:
        factors.append({"factor": "Facing hazard", "category": "facing",
                        "points": FACTORS["facing"]["facing_hazard"]})
        return FACTORS["facing"]["facing_hazard"]
    if facing_away:
        factors.append({"factor": "Facing away from hazard", "category": "facing",
                        "points": FACTORS["facing"]["facing_away"]})
        return FACTORS["facing"]["facing_away"]
    return 0


def _closing_speed_risk(speed, factors: list):
    """Additional risk proportional to speed of approach toward hazard."""
    if speed is None or speed <= 0:
        return 0
    cfg = FACTORS["closing_speed"]
    points = min(cfg["max"], max(0, round((speed - cfg["free_speed"]) * cfg["per_ms"])))
    if points > 0:
        label = "High closing speed" if speed >= 1.5 else "Closing speed increasing"
        factors.append({"factor": f"{label} ({speed:.1f} m/s)",
                        "category": "closing_speed", "points": points})
    return points


def _posture_risk(posture, factors: list):
    """Posture / unsafe-act risk."""
    points = FACTORS["posture"].get(posture, 0)
    if points:
        factors.append({"factor": f"{posture} posture", "category": "posture", "points": points})
    return points


def _zone_bonus(zone_severity, factors: list):
    """Worker inside a hazard zone -> zone severity raises risk."""
    points = FACTORS["zone_bonus"].get((zone_severity or "safe").lower(), 0)
    if points:
        factors.append({"factor": f"Inside {str(zone_severity).upper()} hazard zone",
                        "category": "zone", "points": points})
    return points


def _root_cause(factors: list) -> str:
    """
    Build a human-readable root-cause tag from the contributing categories,
    ordered by their contribution weight, e.g.:
        "PPE NON-COMPLIANCE + INATTENTIVENESS"
    Category -> tag mapping:
        ppe           -> PPE NON-COMPLIANCE
        proximity/zone-> UNSAFE PROXIMITY
        facing        -> INATTENTIVENESS
        closing_speed -> HIGH CLOSING SPEED
        posture       -> UNSAFE POSTURE
    """
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
    if len(tags) >= 2:
        return " + ".join(tags)
    return tags[0] if tags else "NO RISK DETECTED"


def _recommendation(root_cause: str, factors: list) -> str:
    recs = FACTORS["recommendations"]
    if len(factors) >= 3:
        return recs["COMBINED"]
    tag_map = {
        "PPE NON-COMPLIANCE": "PPE NON-COMPLIANCE",
        "UNSAFE PROXIMITY": "UNSAFE PROXIMITY",
        "INATTENTIVENESS": "INATTENTIVENESS",
        "HIGH CLOSING SPEED": "HIGH CLOSING SPEED",
        "UNSAFE POSTURE": "UNSAFE POSTURE",
    }
    return recs.get(tag_map.get(root_cause, "COMBINED"), recs["COMBINED"])


def assess_risk(detection: dict) -> dict:
    """
    THE risk-fusion function.

    Input `detection` dict:
        ppe           {"helmet": bool, "vest": bool, "gloves": bool}
        distance      float meters to hazard source (None = unknown)
        in_zone       bool  worker currently inside a hazard polygon
        zone_severity str   "danger" | "critical" | "warning" | "safe"
        facing_hazard bool  looking toward hazard
        facing_away   bool  looking away
        closing_speed float m/s toward hazard
        posture       str   "Normal" | "Unsafe" | "Severe"

    Output:
        risk_score, risk_level, severity, breakdown[], root_cause, recommendation
    """
    factors: list = []

    ppe_pts   = _ppe_risk(detection.get("ppe") or {}, factors)
    prox_pts  = _proximity_risk(detection.get("distance"), bool(detection.get("in_zone")), factors)
    face_pts  = _facing_risk(bool(detection.get("facing_hazard")), bool(detection.get("facing_away")), factors)
    speed_pts = _closing_speed_risk(detection.get("closing_speed"), factors)
    pos_pts   = _posture_risk(detection.get("posture"), factors)
    zone_pts  = _zone_bonus(detection.get("zone_severity") if detection.get("in_zone") else None, factors)

    raw = ppe_pts + prox_pts + face_pts + speed_pts + pos_pts + zone_pts
    score = max(0, min(100, raw))          # clamp to 0-100
    risk_level, severity = _classify(score)

    return {
        "risk_score": score,
        "raw_score": raw,
        "risk_level": risk_level,
        "severity": severity,
        "breakdown": factors,
        "root_cause": _root_cause(factors),
        "recommendation": _recommendation(_root_cause(factors), factors),
    }


# ----------------------------------------------------------------------
# Quick self-test:  python risk_engine.py
# ----------------------------------------------------------------------
if __name__ == "__main__":
    demo_critical = {
        "ppe": {"helmet": False, "vest": True, "gloves": True},
        "distance": 3.2, "in_zone": True, "zone_severity": "danger",
        "facing_hazard": True, "closing_speed": 2.1, "posture": "Unsafe",
    }
    r = assess_risk(demo_critical)
    print(f"RISK SCORE: {r['risk_score']} — {r['severity']}  (raw {r['raw_score']})")
    for f in r["breakdown"]:
        print(f"  {f['factor']:<42} +{f['points']}")
    print("ROOT CAUSE:", r["root_cause"])
    print("RECOMMENDATION:", r["recommendation"])
