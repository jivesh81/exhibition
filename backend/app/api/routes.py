"""
SafeSight AI — API Routes
=========================
Organized API endpoints by domain.
"""
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import time
import os
from pathlib import Path

from app.core.config import settings
from app.core.logging import (
    setup_logging, DATABASE_LOGGER, ALERT_LOGGER, VOICE_LOGGER
)
from app.services.voice_service import get_voice_service, VoiceGenerationResult
from app.websocket.manager import get_websocket_manager
from app.alerts.engine import get_alert_engine, SafetyEvent, AlertDecisionEngine
from app.events.engine import get_safety_event_engine, SafetyEventEngine
from app.core.logging import FRONTEND_LOGGER
from app.globals import (
    PROVIDERS, RISK_MODEL, FUSION_ENGINE, FEATURE_EXTRACTOR,
    WORKER_TRACKER, VOICE_SYSTEM, VOICE_SERVICE, WS_MANAGER,
    ALERT_ENGINE, EVENT_ENGINE, DEMO, SCENARIOS,
)
from voice import VoiceAlertSystem, VoiceAlert, AlertPriority

import database as db
from risk_engine import assess_risk
from risk_config import RISK_CONFIG, SEVERITY_COLORS

# Voice audio directory
VOICE_AUDIO_DIR = Path(settings.VOICE_AUDIO_DIR)
VOICE_AUDIO_DIR.mkdir(exist_ok=True)


# Pydantic models
class ZoneIn(BaseModel):
    name: str
    label: str = "ZONE"
    severity: str = "danger"
    polygon: Optional[List[List[float]]] = None
    camera_id: str = "CAM-01"
    active: bool = True


class VoiceAlertIn(BaseModel):
    worker_id: str = "TEST"
    worker_name: str = "Test Worker"
    severity: str = "WARNING"
    root_cause: str = "TEST"
    zone: str = "Test Zone"
    message: Optional[str] = None


class VoiceTestIn(BaseModel):
    text: str = "SafeSight voice alert system is operational."


class VoiceToggleIn(BaseModel):
    enabled: bool


class DemoStartIn(BaseModel):
    scenario: str = "crane_approach"


# Helper functions
def _row_json(row: dict) -> dict:
    out = dict(row)
    for key in ("ppe_status", "breakdown"):
        if out.get(key) and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                pass
    return out


def _build_timeline(inc: dict, base_hm: str) -> list:
    def _t(offset: int) -> str:
        return f"-{offset}s {base_hm}" if offset else base_hm
    tl = [
        {"time": _t(5), "event": "Worker detected in camera view"},
        {"time": _t(3), "event": f"Entered {inc.get('zone_name') or 'hazard zone'}" if inc.get("zone_id") else "Zone monitored"},
        {"time": _t(2), "event": "PPE compliance checked"},
        {"time": _t(1), "event": f"Risk score reached {inc.get('risk_score')}"},
        {"time": _t(0), "event": f"{inc.get('severity')} risk generated — {inc.get('root_cause')}"},
        {"time": _t(0), "event": "Supervisor alert sent"},
        {"time": _t(0), "event": "Incident automatically logged to database"},
    ]
    if inc.get("voice_alert"):
        tl.append({"time": _t(0), "event": f"Voice alert: '{inc.get('voice_message')}'"})
    if inc.get("status") in ("RESOLVED", "AUTO_RESOLVED"):
        tl.append({"time": base_hm, "event": f"Incident {inc.get('status').replace('_', '').lower()}"})
    return tl


def _build_explanation(inc: dict) -> dict:
    breakdown = inc.get("breakdown", [])
    if isinstance(breakdown, str):
        try:
            breakdown = json.loads(breakdown)
        except Exception:
            breakdown = []

    ml_component = None
    rule_component = None
    temporal_component = None
    overrides = []

    for f in breakdown:
        cat = f.get("category", "")
        if cat == "ml":
            ml_component = f
        elif cat == "rule":
            rule_component = f
        elif cat == "temporal":
            temporal_component = f
        elif cat == "override":
            overrides.append(f)

    return {
        "ml_risk": ml_component.get("points", 0) if ml_component else None,
        "rule_risk": rule_component.get("points", 0) if rule_component else None,
        "temporal_risk": temporal_component.get("points", 0) if temporal_component else None,
        "overrides": overrides,
        "root_cause": inc.get("root_cause"),
        "final_score": inc.get("risk_score"),
        "severity": inc.get("severity"),
        "contributing_factors": [
            {"factor": f.get("factor"), "points": f.get("points"), "category": f.get("category")}
            for f in breakdown if f.get("category") not in ("ml", "rule", "temporal", "override")
        ],
    }


# Create routers
health_router = APIRouter(prefix="/api", tags=["Health"])
dashboard_router = APIRouter(prefix="/api", tags=["Dashboard"])
workers_router = APIRouter(prefix="/api", tags=["Workers"])
incidents_router = APIRouter(prefix="/api", tags=["Incidents"])
analytics_router = APIRouter(prefix="/api", tags=["Analytics"])
zones_router = APIRouter(prefix="/api", tags=["Zones"])
demo_router = APIRouter(prefix="/api", tags=["Demo"])
risk_router = APIRouter(prefix="/api", tags=["Risk"])
detection_router = APIRouter(prefix="/api", tags=["Detection"])
pipeline_router = APIRouter(prefix="/api", tags=["Pipeline"])
voice_router = APIRouter(prefix="/api/voice", tags=["Voice"])
tracking_router = APIRouter(prefix="/api", tags=["Tracking"])
ml_router = APIRouter(prefix="/api", tags=["ML"])
websocket_router = APIRouter(tags=["WebSocket"])


# Health endpoints
@health_router.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "group": settings.GROUP,
        "database": "connected" if db.query_one("SELECT 1 AS ok") else "error",
        "version": settings.APP_VERSION,
    }


# Dashboard endpoints
@dashboard_router.get("/dashboard")
def dashboard():
    today = db.query_one("SELECT date('now','localtime') AS d")["d"]
    today_incs = db.query("SELECT severity, COUNT(*) n FROM incidents WHERE date(timestamp)=? GROUP BY severity", (today,))
    by_sev = {r["severity"]: r["n"] for r in today_incs}
    ppe = db.query_one("SELECT AVG(compliant)*100 AS rate FROM ppe_events")
    avg_risk = db.query_one("SELECT AVG(risk_score) AS a FROM incidents WHERE date(timestamp)=?", (today,))
    workers = db.query("SELECT COUNT(*) n FROM workers")
    cams = db.query("SELECT COUNT(*) n FROM cameras WHERE status='ONLINE'")
    open_alerts = db.query_one("SELECT COUNT(*) n FROM incidents WHERE status='OPEN'")["n"]
    near = db.query_one("SELECT COUNT(*) n FROM incidents WHERE near_miss=1")["n"]

    return {
        "total_workers": workers[0]["n"],
        "active_cameras": cams[0]["n"],
        "open_alerts": open_alerts,
        "today_incidents": sum(by_sev.values()),
        "critical": by_sev.get("CRITICAL", 0),
        "high": by_sev.get("HIGH", 0),
        "warning": by_sev.get("WARNING", 0),
        "safe_events": by_sev.get("SAFE", 0),
        "ppe_compliance": round(ppe["rate"] or 0, 1),
        "avg_risk_score": round(avg_risk["a"] or 0, 1),
        "near_misses": near,
        "ai_mode": DEMO._ai_mode(),
        "demo_running": DEMO.running,
        "ml_model_loaded": RISK_MODEL.is_model_loaded(),
        "voice_enabled": VOICE_SYSTEM.enabled,
        "voice_provider": VOICE_SYSTEM.get_status()["active_provider"],
    }


@dashboard_router.get("/system-status")
def system_status():
    ppe, pose, prox = PROVIDERS["ppe"], PROVIDERS["pose"], PROVIDERS["proximity"]
    fusion_status = FUSION_ENGINE.get_system_status()
    voice_status = VOICE_SYSTEM.get_status()

    return {
        "camera_input": "ONLINE",
        "camera_id": "CAM-01",
        "person_detector": "READY (OpenCV HOG)" if prox["provider"].real_vision else "READY (Mock fallback)",
        "ppe_model": "READY (YOLO)" if ppe["available"] else "READY (Mock fallback)",
        "ppe_available": ppe["available"],
        "ppe_error": ppe["provider"].error if hasattr(ppe["provider"], "error") else None,
        "pose_model": "READY (YOLO-POSE)" if pose["available"] else "READY (Mock fallback)",
        "pose_available": pose["available"],
        "pose_error": pose["provider"].error if hasattr(pose["provider"], "error") else None,
        "tracking_engine": "READY (ByteTrack-inspired)",
        "tracking_active": len(WORKER_TRACKER.get_confirmed_tracks()) > 0,
        "hybrid_risk_model": "READY" if RISK_MODEL.is_model_loaded() else "RULE_ONLY",
        "hybrid_risk_model_info": fusion_status["ml_model_info"],
        "rule_engine": "ACTIVE",
        "voice_engine": voice_status["active_provider"] if voice_status["active_provider"] != "NONE" else "UNAVAILABLE",
        "voice_enabled": VOICE_SYSTEM.enabled,
        "voice_queue_size": voice_status["queue_size"],
        "database": "CONNECTED",
        "websocket": "CONNECTED",
        "inference_fps": DEMO.TICK_SECONDS and round(1.0 / DEMO.TICK_SECONDS, 1),
        "deployment": "LOCAL / EDGE",
        "cloud_video_transfer": "DISABLED",
        "ai_mode": "HYBRID" if RISK_MODEL.is_model_loaded() else DEMO._ai_mode(),
        "demo_running": DEMO.running,
        "severity_colors": SEVERITY_COLORS,
        "providers": {k: {"name": v["name"], "available": v["available"], "mode": v["mode"]} for k, v in PROVIDERS.items()},
        "ml_components": {
            "feature_extractor": "ACTIVE",
            "risk_fusion": "ACTIVE",
            "worker_tracker": "ACTIVE",
            "voice_alerts": "ACTIVE" if VOICE_SYSTEM.enabled else "DISABLED",
        },
    }


# Worker endpoints
@workers_router.get("/workers")
def workers():
    workers_out = []
    for w in db.query("SELECT * FROM workers ORDER BY id"):
        ppe = json.loads(w["ppe_status"]) if isinstance(w["ppe_status"], str) else w["ppe_status"]
        track = WORKER_TRACKER.get_track_by_worker_id(w["id"])
        tracking_id = track.tracking_id if track else None
        workers_out.append({
            "id": w["id"], "name": w["name"], "role": w["role"], "status": w["status"],
            "current_zone": w["current_zone"], "ppe": ppe,
            "distance": w["distance"], "risk_score": w["risk_score"],
            "severity": w["severity"], "posture": w["posture"],
            "last_seen": w["last_seen"], "exposure_time": w["exposure_time"],
            "tracking_id": tracking_id,
            "track_state": track.state if track else None,
        })
    return workers_out


@workers_router.get("/workers/{worker_id}")
def worker_detail(worker_id: str):
    w = db.query_one("SELECT * FROM workers WHERE id=?", (worker_id,))
    if not w:
        raise HTTPException(404, "Worker not found")
    ppe = json.loads(w["ppe_status"]) if isinstance(w["ppe_status"], str) else w["ppe_status"]
    today = db.query_one("SELECT date('now','localtime') AS d")["d"]
    recent = [_row_json(r) for r in db.query(
        "SELECT * FROM incidents WHERE worker_id=? ORDER BY timestamp DESC LIMIT 10", (worker_id,))]
    stats = db.query_one("""SELECT COUNT(*) n, AVG(risk_score) a FROM incidents WHERE worker_id=?""", (worker_id,))
    crit = db.query_one("SELECT COUNT(*) n FROM incidents WHERE worker_id=? AND severity='CRITICAL'", (worker_id,))

    track = WORKER_TRACKER.get_track_by_worker_id(worker_id)
    track_info = None
    if track:
        track_info = {
            "tracking_id": track.tracking_id,
            "state": track.state,
            "age": track.age,
            "hits": track.hits,
            "time_since_update": track.time_since_update,
            "bbox": track.bbox,
            "confidence": track.confidence,
        }

    cooldown_status = VOICE_SYSTEM.cooldown.get_status(worker_id)

    return {
        "id": w["id"], "name": w["name"], "role": w["role"], "status": w["status"],
        "current_zone": w["current_zone"], "ppe": ppe, "distance": w["distance"],
        "risk_score": w["risk_score"], "severity": w["severity"], "posture": w["posture"],
        "last_seen": w["last_seen"], "exposure_time": w["exposure_time"],
        "recent_alerts": recent,
        "total_incidents": stats["n"] or 0,
        "avg_risk": round(stats["a"] or 0, 1),
        "critical_count": crit["n"] or 0,
        "today": today,
        "tracking": track_info,
        "voice_cooldown": cooldown_status,
    }


# Incident endpoints
@incidents_router.get("/incidents")
def incidents(
    severity: str = None, date: str = None, worker: str = None,
    zone: str = None, root_cause: str = None, status: str = None,
    limit: int = 200
):
    sql = "SELECT * FROM incidents WHERE 1=1"
    params: list = []
    if severity:
        sql += " AND severity=?"
        params.append(severity.upper())
    if date:
        sql += " AND date(timestamp)=?"
        params.append(date)
    if worker:
        sql += " AND worker_id=?"
        params.append(worker.upper())
    if zone:
        sql += " AND zone_id=?"
        params.append(zone)
    if root_cause:
        sql += " AND root_cause LIKE ?"
        params.append(f"%{root_cause.upper()}%")
    if status:
        sql += " AND status=?"
        params.append(status.upper())
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(min(limit, 1000))
    return [_row_json(r) for r in db.query(sql, tuple(params))]


@incidents_router.get("/incidents/{incident_id}")
def incident_detail(incident_id: int):
    inc = db.query_one("SELECT * FROM incidents WHERE id=?", (incident_id,))
    if not inc:
        raise HTTPException(404, "Incident not found")
    inc = _row_json(inc)
    ts = inc.get("timestamp") or ""
    base_hm = ts.split("T")[1] if "T" in ts else ts
    inc["timeline"] = _build_timeline(inc, base_hm)
    zone = db.query_one("SELECT name, label FROM zones WHERE id=?", (inc.get("zone_id"),))
    inc["zone_name"] = zone["name"] if zone else None

    if inc.get("breakdown"):
        inc["explainable_ai"] = _build_explanation(inc)

    return inc


@incidents_router.post("/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: int):
    inc = db.query_one("SELECT id, status FROM incidents WHERE id=?", (incident_id,))
    if not inc:
        raise HTTPException(404, "Incident not found")
    db.update_incident_status(incident_id, "ACKNOWLEDGED")
    return {"status": "ACKNOWLEDGED", "incident_id": incident_id}


@incidents_router.post("/incidents/{incident_id}/resolve")
def resolve(incident_id: int):
    inc = db.query_one("SELECT id, status FROM incidents WHERE id=?", (incident_id,))
    if not inc:
        raise HTTPException(404, "Incident not found")
    db.update_incident_status(incident_id, "RESOLVED")
    DEMO.active_alerts.pop(str(incident_id), None)
    return {"status": "RESOLVED", "incident_id": incident_id}


@incidents_router.delete("/incidents/{incident_id}")
def delete_incident(incident_id: int):
    inc = db.query_one("SELECT id FROM incidents WHERE id=?", (incident_id,))
    if not inc:
        raise HTTPException(404, "Incident not found")
    db.execute("DELETE FROM incidents WHERE id=?", (incident_id,))
    return {"deleted": incident_id}


# Analytics endpoints
@analytics_router.get("/analytics")
def analytics():
    days = [db.query_one("SELECT date('now','localtime', ?) AS d", (f"-{i} days",))["d"] for i in range(6, -1, -1)]
    over_time = []
    for d in days:
        row = db.query_one("SELECT COUNT(*) n FROM incidents WHERE date(timestamp)=?", (d,))
        over_time.append({"date": d[5:], "count": row["n"]})

    by_sev = [{"severity": r["severity"], "count": r["n"]} for r in
              db.query("SELECT severity, COUNT(*) n FROM incidents GROUP BY severity")]

    total_incs = db.query_one("SELECT COUNT(*) n FROM incidents")["n"] or 1
    by_root = [{"cause": r["root_cause"], "count": r["n"],
                "pct": round(r["n"] * 100.0 / total_incs, 1)} for r in
               db.query("SELECT root_cause, COUNT(*) n FROM incidents GROUP BY root_cause ORDER BY n DESC")]

    ppe = db.query_one("SELECT AVG(compliant)*100 AS rate, COUNT(*) n FROM ppe_events")
    ppe_missing = [{"item": "Helmet", "missing": r["n"]} for r in
                   db.query("SELECT COUNT(*) n FROM ppe_events WHERE helmet=0")]
    ppe_missing += [{"item": "Vest", "missing": r["n"]} for r in
                    db.query("SELECT COUNT(*) n FROM ppe_events WHERE vest=0")]
    ppe_missing += [{"item": "Gloves", "missing": r["n"]} for r in
                    db.query("SELECT COUNT(*) n FROM ppe_events WHERE gloves=0")]

    avg_risk = db.query_one("SELECT AVG(risk_score) a FROM incidents")["a"] or 0

    zone_entries = []
    for z in db.query("SELECT id, name, label FROM zones ORDER BY id"):
        row = db.query_one("SELECT COUNT(*) n FROM proximity_events WHERE zone_id=? AND event_type='ZONE_ENTRY'", (z["id"],))
        zone_entries.append({"zone": f"{z['label']} — {z['name']}", "entries": row["n"]})

    exposure = [{"worker": r["worker_id"], "minutes": round(r["exposure_time"] or 0, 1)} for r in
                db.query("SELECT id AS worker_id, exposure_time FROM workers ORDER BY exposure_time DESC LIMIT 8")]

    near = db.query_one("SELECT COUNT(*) n FROM incidents WHERE near_miss=1")["n"]
    near_zone = db.query_one("""SELECT z.name AS name FROM incidents i
                                JOIN zones z ON i.zone_id=z.id
                                WHERE i.near_miss=1 GROUP BY z.name ORDER BY COUNT(*) DESC LIMIT 1""")
    today = db.query_one("SELECT date('now','localtime') AS d")["d"]
    near_today = db.query_one("SELECT COUNT(*) n FROM incidents WHERE near_miss=1 AND date(timestamp)=?", (today,))["n"]
    near_cause = db.query_one("SELECT root_cause FROM incidents WHERE near_miss=1 GROUP BY root_cause ORDER BY COUNT(*) DESC LIMIT 1")

    posture = [{"posture": r["posture"], "count": r["n"]} for r in
               db.query("SELECT posture, COUNT(*) n FROM posture_events GROUP BY posture")]

    return {
        "incidents_over_time": over_time,
        "incidents_by_severity": by_sev,
        "incidents_by_root_cause": by_root,
        "ppe_compliance": round(ppe["rate"] or 0, 1),
        "ppe_events_total": ppe["n"],
        "ppe_missing": ppe_missing,
        "avg_risk_score": round(avg_risk, 1),
        "zone_entries": zone_entries,
        "worker_exposure": exposure,
        "near_misses": near,
        "near_misses_today": near_today,
        "near_most_common_cause": (near_cause["root_cause"] if near_cause else "Unsafe Proximity"),
        "near_highest_risk_zone": (near_zone["name"] if near_zone else "Crane Swing Area"),
        "posture_events": posture,
    }


# Zones endpoints
@zones_router.get("/zones")
def zones():
    cams = db.query("SELECT * FROM cameras")
    zones_out = []
    for z in db.query("SELECT * FROM zones ORDER BY id"):
        zones_out.append({
            "id": z["id"], "name": z["name"], "label": z["label"], "severity": z["severity"],
            "polygon": json.loads(z["polygon"]) if isinstance(z["polygon"], str) else z["polygon"],
            "camera_id": z["camera_id"], "active": bool(z["active"]),
        })
    return {"cameras": cams, "zones": zones_out}


@zones_router.post("/zones")
def create_zone(zone: ZoneIn):
    polygon = zone.polygon or [[0.05, 0.1], [0.35, 0.1], [0.35, 0.4], [0.05, 0.4]]
    zid = db.execute("""INSERT INTO zones (name,label,severity,polygon,camera_id,active,created_at)
                        VALUES (?,?,?,?,?,?,datetime('now','localtime'))""",
                     (zone.name, zone.label, zone.severity, json.dumps(polygon),
                      zone.camera_id, 1 if zone.active else 0))
    DEMO.load_world()
    return {"id": zid, **zone.model_dump(), "polygon": polygon}


@zones_router.put("/zones/{zone_id}")
def update_zone(zone_id: int, zone: ZoneIn):
    existing = db.query_one("SELECT id FROM zones WHERE id=?", (zone_id,))
    if not existing:
        raise HTTPException(404, "Zone not found")
    polygon = zone.polygon or [[0.05, 0.1], [0.35, 0.1], [0.35, 0.4], [0.05, 0.4]]
    db.execute("""UPDATE zones SET name=?, label=?, severity=?, polygon=?, camera_id=?, active=? WHERE id=?""",
               (zone.name, zone.label, zone.severity, json.dumps(polygon),
                zone.camera_id, 1 if zone.active else 0, zone_id))
    DEMO.load_world()
    return {"id": zone_id, **zone.model_dump(), "polygon": polygon}


@zones_router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int):
    existing = db.query_one("SELECT id FROM zones WHERE id=?", (zone_id,))
    if not existing:
        raise HTTPException(404, "Zone not found")
    db.execute("DELETE FROM zones WHERE id=?", (zone_id,))
    DEMO.load_world()
    return {"deleted": zone_id}


# Demo endpoints
@demo_router.post("/demo/start")
def demo_start(scenario: str = "crane_approach"):
    if scenario not in SCENARIOS:
        raise HTTPException(400, f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS)}")
    result = DEMO.start(scenario)
    return {**result, "scenario_info": SCENARIOS[scenario]}


@demo_router.post("/demo/reset")
def demo_reset():
    WORKER_TRACKER.reset()
    FEATURE_EXTRACTOR.worker_history.clear()
    FEATURE_EXTRACTOR.worker_positions.clear()
    return DEMO.reset()


@demo_router.get("/demo/scenarios")
def demo_scenarios():
    return list(SCENARIOS.values())


@demo_router.get("/snapshot")
def snapshot():
    return DEMO.build_snapshot()


# Risk endpoints
@risk_router.post("/risk/score")
def risk_score(detection: dict):
    return assess_risk(detection)


@risk_router.post("/risk/hybrid")
def hybrid_risk_score(detection: dict):
    worker = detection.get("worker", {})
    proximity = detection.get("proximity", {})
    detections = detection.get("detections", [])
    timestamp = time.time()

    assessment = RISK_MODEL.assess(worker, proximity, detections, timestamp)
    return {
        "ml_probability": assessment.ml_probability,
        "ml_risk_score": assessment.ml_risk_score,
        "rule_risk_score": assessment.rule_risk_score,
        "temporal_risk_score": assessment.temporal_risk_score,
        "final_risk_score": assessment.final_risk_score,
        "severity": assessment.severity,
        "risk_level": assessment.risk_level,
        "root_cause": assessment.root_cause,
        "recommendation": assessment.recommendation,
        "breakdown": assessment.breakdown,
        "overrides": assessment.overrides,
        "model_version": assessment.model_version,
        "feature_version": assessment.feature_version,
    }


# Detection endpoints
def _read_frame(file: UploadFile):
    import cv2
    import numpy as np
    data = file.file.read()
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@detection_router.post("/detect/ppe")
async def detect_ppe(file: UploadFile = None):
    ppe = PROVIDERS["ppe"]
    frame = await _read_frame(file) if file else None
    if ppe.available() and frame is not None:
        dets = ppe.detect(frame)
        if dets is not None:
            return {"provider": "YOLOPPEProvider", "mode": "YOLO", "available": True, "detections": dets}
    if frame is None and not ppe.available():
        return {"provider": "YOLOPPEProvider", "mode": "MOCK", "available": False,
                "reason": ppe.error or "model unavailable — Demo/Mock mode active"}
    prox = PROVIDERS["proximity"]
    persons = prox.detect_persons(frame) if frame is not None else []
    return {"provider": "OpenCV-HOG", "mode": "OPENCV", "available": True,
            "detections": persons or [], "note": "PPE classification needs YOLO weights"}


@detection_router.post("/detect/pose")
async def detect_pose(file: UploadFile = None):
    pose = PROVIDERS["pose"]
    frame = await _read_frame(file) if file else None
    if pose.available() and frame is not None:
        dets = pose.detect(frame)
        if dets is not None:
            return {"provider": "YOLOPoseProvider", "mode": "YOLO-POSE", "available": True, "detections": dets}
    return {"provider": "YOLOPoseProvider", "mode": "MOCK", "available": False,
            "reason": pose.error or "model unavailable — Demo/Mock mode active"}


@detection_router.post("/detect/proximity")
async def detect_proximity(detection: dict):
    prox = PROVIDERS["proximity"]
    zones = detection.get("zones") or []
    worker = detection.get("worker") or {}
    return {"provider": "ProximityProvider", "mode": "OPENCV", "available": True,
            "proximity": prox.compute_proximity(worker, zones, dt=detection.get("dt", 1.0))}


@detection_router.post("/detect/frame")
async def detect_frame(file: UploadFile = File(...)):
    import cv2
    import numpy as np
    frame = _read_frame(file)
    if frame is None:
        return JSONResponse({"available": False, "reason": "could not decode image"}, status_code=400)
    prox = PROVIDERS["proximity"]
    persons = prox.detect_persons(frame)
    if not persons:
        return {"available": True, "persons": [], "note": "no persons detected in frame"}
    zones = []
    for z in db.query("SELECT * FROM zones WHERE active=1"):
        zones.append({"id": z["id"], "name": z["name"], "severity": z["severity"],
                      "polygon": json.loads(z["polygon"]) if isinstance(z["polygon"], str) else z["polygon"]})
    h, w = frame.shape[:2]
    results = []
    for p in persons:
        box = p["box"]
        cx = (box[0] + box[2]) / 2 / w
        cy = (box[1] + box[3]) / 2 / h
        proxres = prox.compute_proximity({"x": cx, "y": cy, "id": f"cam-{len(results)}"}, zones, dt=1.0)
        assessment = assess_risk({"ppe": None, "distance": proxres["distance"],
                                  "in_zone": proxres["in_zone"],
                                  "zone_severity": proxres["zone_severity"],
                                  "facing_hazard": proxres["facing_hazard"],
                                  "facing_away": proxres["facing_away"],
                                  "closing_speed": 0.0, "posture": None})
        results.append({"box": box, "confidence": p["confidence"], "source": p["source"],
                        "proximity": proxres, "risk": assessment})
    return {"available": True, "persons": results, "mode": DEMO._ai_mode()}


# Pipeline endpoints
@pipeline_router.post("/pipeline/process-frame")
async def process_frame_hybrid(file: UploadFile = File(...)):
    import cv2
    import numpy as np
    frame = _read_frame(file)
    if frame is None:
        return JSONResponse({"available": False, "reason": "could not decode image"}, status_code=400)

    prox = PROVIDERS["proximity"]
    persons = prox.detect_persons(frame)
    if not persons:
        return {"available": True, "persons": [], "note": "no persons detected in frame"}

    zones = []
    for z in db.query("SELECT * FROM zones WHERE active=1"):
        zones.append({"id": z["id"], "name": z["name"], "severity": z["severity"],
                      "polygon": json.loads(z["polygon"]) if isinstance(z["polygon"], str) else z["polygon"]})

    h, w = frame.shape[:2]
    timestamp = time.time()

    detections_for_tracker = []
    for p in persons:
        box = p["box"]
        cx = (box[0] + box[2]) / 2 / w
        cy = (box[1] + box[3]) / 2 / h
        detections_for_tracker.append({
            "id": f"det-{len(detections_for_tracker)}",
            "box": box,
            "confidence": p["confidence"],
            "x": cx, "y": cy,
            "ppe": None,
            "posture": "Normal",
            "facing_vector": [0, -1],
        })

    tracks = WORKER_TRACKER.update(detections_for_tracker)

    fusion_results = []
    for track in tracks:
        worker_data = {
            "id": track.worker_id,
            "name": track.worker_id,
            "x": (track.bbox[0] + track.bbox[2]) / 2,
            "y": (track.bbox[1] + track.bbox[3]) / 2,
            "ppe": track.ppe,
            "posture": track.posture,
            "facing_vector": track.facing_vector,
        }

        prox_result = prox.compute_proximity(worker_data, zones, dt=1.0/30.0)
        worker_data.update(prox_result)

        fusion_result = FUSION_ENGINE.process_worker(
            worker_data, prox_result, detections_for_tracker, track.tracking_id
        )

        if fusion_result.voice_alert_triggered:
            VOICE_SYSTEM.create_alert(
                worker_id=fusion_result.worker_id,
                worker_name=fusion_result.worker_name,
                severity=fusion_result.risk_assessment.severity,
                root_cause=fusion_result.risk_assessment.root_cause,
                zone=fusion_result.worker_data.get("zone", "Unknown") if hasattr(fusion_result, "worker_data") else "Unknown",
                message=fusion_result.voice_message,
            )

        fusion_results.append({
            "worker_id": fusion_result.worker_id,
            "worker_name": fusion_result.worker_name,
            "tracking_id": fusion_result.tracking_id,
            "risk_score": fusion_result.risk_assessment.final_risk_score,
            "severity": fusion_result.risk_assessment.severity,
            "risk_level": fusion_result.risk_assessment.risk_level,
            "root_cause": fusion_result.risk_assessment.root_cause,
            "recommendation": fusion_result.risk_assessment.recommendation,
            "breakdown": fusion_result.risk_assessment.breakdown,
            "overrides": fusion_result.risk_assessment.overrides,
            "proximity": fusion_result.proximity,
            "ppe": fusion_result.ppe_status,
            "posture": fusion_result.posture,
            "voice_alert": fusion_result.voice_alert_triggered,
            "voice_message": fusion_result.voice_message,
            "model_version": fusion_result.risk_assessment.model_version,
        })

    return {
        "available": True,
        "mode": "HYBRID" if RISK_MODEL.is_model_loaded() else "RULE_ONLY",
        "tracks": len(tracks),
        "results": fusion_results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp)),
    }


# Voice endpoints
@voice_router.post("/alert")
def trigger_voice_alert(alert: VoiceAlertIn):
    message = alert.message or f"{alert.worker_id}, this is a test alert."
    voice_alert = VOICE_SYSTEM.create_alert(
        worker_id=alert.worker_id,
        worker_name=alert.worker_name,
        severity=alert.severity,
        root_cause=alert.root_cause,
        zone=alert.zone,
        message=message,
    )
    if voice_alert:
        return {"status": "queued", "alert_id": voice_alert.alert_id}
    else:
        return {"status": "suppressed", "reason": "cooldown active"}


@voice_router.post("/test")
def test_voice(test_in: VoiceTestIn):
    filename = VOICE_SYSTEM.speak_immediate(test_in.text)
    if filename:
        return {"status": "generated", "provider": VOICE_SYSTEM.get_status()["active_provider"], "audio_url": f"/api/voice/audio/{filename}"}
    else:
        return {"status": "failed", "provider": VOICE_SYSTEM.get_status()["active_provider"]}


@voice_router.get("/audio/hardware-test")
def get_hardware_test_audio():
    """Serve the hardware test tone (1000 Hz beep)."""
    file_path = VOICE_AUDIO_DIR / "hardware-test.wav"
    if not file_path.exists():
        raise HTTPException(404, "Hardware test tone not found")
    return FileResponse(file_path, media_type="audio/wav", filename="hardware-test.wav")


@voice_router.get("/audio/test-speech")
def get_test_speech_audio():
    """Generate and serve a test speech audio file."""
    filename = VOICE_SYSTEM.speak_immediate("SafeSight voice alert system is operational. This is a test.")
    if not filename:
        raise HTTPException(500, "Failed to generate test speech")
    file_path = VOICE_AUDIO_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "Test speech file not found")
    return FileResponse(file_path, media_type="audio/wav", filename=filename)


@voice_router.get("/audio/test-speech-static")
def get_test_speech_static_audio():
    """Serve a pre-generated static test speech audio file."""
    file_path = VOICE_AUDIO_DIR / "test-speech-static.wav"
    if not file_path.exists():
        raise HTTPException(404, "Static test speech file not found")
    return FileResponse(file_path, media_type="audio/wav", filename="test-speech-static.wav")


@voice_router.get("/audio/{filename}")
def get_voice_audio(filename: str):
    file_path = VOICE_AUDIO_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "Audio file not found")

    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    else:
        media_type = "application/octet-stream"

    return FileResponse(file_path, media_type=media_type, filename=filename)


@voice_router.get("/status")
def voice_status():
    return VOICE_SYSTEM.get_status()


@voice_router.post("/toggle")
def toggle_voice(toggle_in: VoiceToggleIn):
    VOICE_SYSTEM.enabled = toggle_in.enabled
    return {"enabled": VOICE_SYSTEM.enabled}


@voice_router.get("/validate/{filename}")
def validate_audio(filename: str):
    result = VOICE_SERVICE.validate_audio_file(filename)
    return result


# Tracking endpoints
@tracking_router.get("/tracking/status")
def tracking_status():
    tracks = WORKER_TRACKER.get_all_tracks()
    confirmed = WORKER_TRACKER.get_confirmed_tracks()
    return {
        "total_tracks": len(tracks),
        "confirmed_tracks": len(confirmed),
        "tracks": [
            {
                "tracking_id": t.tracking_id,
                "worker_id": t.worker_id,
                "state": t.state,
                "age": t.age,
                "hits": t.hits,
                "time_since_update": t.time_since_update,
                "bbox": t.bbox,
                "confidence": t.confidence,
                "severity": t.severity,
                "risk_score": t.risk_score,
            }
            for t in tracks
        ],
    }


@tracking_router.post("/tracking/reset")
def tracking_reset():
    WORKER_TRACKER.reset()
    return {"status": "reset"}


# ML endpoints
@ml_router.get("/ml/model-info")
def ml_model_info():
    return RISK_MODEL.get_model_info()


@ml_router.post("/ml/reload")
def reload_ml_model():
    global RISK_MODEL, FUSION_ENGINE
    RISK_MODEL = HybridRiskModel()
    FUSION_ENGINE = RiskFusionEngine()
    return {"status": "reloaded", "model_loaded": RISK_MODEL.is_model_loaded()}


# WebSocket endpoint
@websocket_router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    client = await WS_MANAGER.connect(ws)
    try:
        await ws.send_text(json.dumps({"type": "connected", "app": "SafeSight AI", "client_id": client.client_id}))
        while True:
            data = await ws.receive_text()
            # Handle client messages if needed
    except WebSocketDisconnect:
        await WS_MANAGER.disconnect(client.client_id)
    except Exception:
        await WS_MANAGER.disconnect(client.client_id)


# Collect all routers
def get_all_routers():
    return [
        health_router,
        dashboard_router,
        workers_router,
        incidents_router,
        analytics_router,
        zones_router,
        demo_router,
        risk_router,
        detection_router,
        pipeline_router,
        voice_router,
        tracking_router,
        ml_router,
        websocket_router,
    ]