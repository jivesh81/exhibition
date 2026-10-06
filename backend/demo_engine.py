"""
SafeSight AI — Demo Engine (scripted safety scenario)
=====================================================
Group 173 Prototype

Simulates a camera feed by driving worker states through a realistic safety
scenario, pushing every tick through the REAL detection pipeline
(MockDetectionProvider + ProximityProvider) and the HYBRID risk fusion engine.

NEW: Integrates with Hybrid ML + Rule risk model, Worker Tracking, and Voice Alerts.

Scenario (crane approach — repeats automatically):
    IDLE -> APPROACH -> PPE_LOSS -> UNSAFE_POSTURE -> CRITICAL -> EXIT -> COMPLETE
    1.  Worker W-002 appears in safe zone
    2.  Worker moves toward Crane Swing Area
    3.  Distance decreases / closing speed increases
    4.  Worker faces hazard
    5.  Helmet becomes missing
    6.  Pose becomes unsafe
    7.  Risk score increases -> WARNING -> CRITICAL
    8.  Alert broadcast + incident automatically saved to SQLite
    9.  Worker exits zone -> risk drops -> alert auto-resolves (near-miss logged)
    10. Voice alerts announce worker-specific warnings

Callbacks (wired in main.py):
    on_event(event)      -> WebSocket broadcast + incident/event logging
    on_snapshot(snap)    -> WebSocket live frame for the monitoring panel
"""

import json
import threading
import time
import traceback
from datetime import datetime
from typing import List, Dict, Any

from risk_engine import assess_risk
import database as db
from detection.mock import MockDetectionProvider
from detection.proximity import ProximityProvider

# New hybrid AI components
from ml.model import get_risk_model
from ml.fusion import get_fusion_engine
from tracking import get_worker_tracker
from voice import get_voice_system


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _now_hm() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ----------------------------------------------------------------------
# Scenario definition (edit to create new scenarios)
# ----------------------------------------------------------------------
SCENARIOS = {
    "crane_approach": {
        "id": "crane_approach",
        "name": "RUN SAFETY SCENARIO",
        "description": "Worker approaches crane hazard without helmet",
        "worker": "W-002",
        "camera": "CAM-01",
        "stages": [
            {"id": "IDLE",           "ticks": 2, "label": "Idle — workers in safe zones",
             "move": None,           "ppe": {},                  "posture": "Normal", "facing_hazard": False},
            {"id": "APPROACH",       "ticks": 8, "label": "W-002 approaching Crane Swing Area",
             "move": [0.70, 0.36],   "ppe": {},                  "posture": "Normal", "facing_hazard": True},
            {"id": "PPE_LOSS",       "ticks": 2, "label": "Helmet removed — PPE violation",
             "move": None,           "ppe": {"helmet": False},   "posture": "Normal", "facing_hazard": True},
            {"id": "UNSAFE_POSTURE", "ticks": 2, "label": "Unsafe posture detected",
             "move": None,           "ppe": {"helmet": False},   "posture": "Unsafe", "facing_hazard": True},
            {"id": "CRITICAL",       "ticks": 3, "label": "CRITICAL — alert generated",
             "move": None,           "ppe": {"helmet": False},   "posture": "Unsafe", "facing_hazard": True},
            {"id": "EXIT",           "ticks": 6, "label": "W-002 exiting hazard zone",
             "move": [0.48, 0.50],   "ppe": {"helmet": True},    "posture": "Normal", "facing_hazard": False},
            {"id": "COMPLETE",       "ticks": 2, "label": "Scenario complete — incident logged",
             "move": None,           "ppe": {},                  "posture": "Normal", "facing_hazard": False},
        ],
    },
    "multi_worker": {
        "id": "multi_worker",
        "name": "MULTI-WORKER SCENARIO",
        "description": "5 workers with independent scenarios: safe, danger zone, PPE violation, proximity, critical",
        "worker": "W-001",
        "camera": "CAM-01",
        "stages": [
            {"id": "IDLE", "ticks": 4, "label": "All workers in safe zones",
             "move": {"W-001": [0.25, 0.35], "W-002": [0.65, 0.39], "W-003": [0.18, 0.40], "W-004": [0.50, 0.68], "W-005": [0.12, 0.30]},
             "ppe": {}, "posture": "Normal", "facing_hazard": False},
            {"id": "W002_DANGER", "ticks": 10, "label": "W-002 approaches Crane Swing Area (danger zone)",
             "move": {"W-001": [0.25, 0.35], "W-002": [0.75, 0.36], "W-003": [0.30, 0.60], "W-004": [0.55, 0.70], "W-005": [0.15, 0.35]},
             "ppe": {}, "posture": "Normal", "facing_hazard": {"W-002": True, "W-004": True}},
            {"id": "W003_PPE", "ticks": 6, "label": "W-003 loses helmet in Machine Operating Area (warning zone)",
             "move": {"W-001": [0.28, 0.38], "W-002": [0.78, 0.34], "W-003": [0.35, 0.58], "W-004": [0.60, 0.72], "W-005": [0.18, 0.38]},
             "ppe": {"W-003": {"helmet": False}}, "posture": "Normal", "facing_hazard": {"W-003": True}},
            {"id": "W004_PROXIMITY", "ticks": 8, "label": "W-004 approaches W-001 creating proximity hazard in Restricted Area",
             "move": {"W-001": [0.28, 0.38], "W-002": [0.80, 0.32], "W-003": [0.38, 0.55], "W-004": [0.65, 0.70], "W-005": [0.20, 0.40]},
             "ppe": {"W-003": {"helmet": False}}, "posture": "Normal", "facing_hazard": {"W-004": True}},
            {"id": "W004_CRITICAL", "ticks": 6, "label": "W-004 enters Restricted Area (critical zone) with unsafe posture",
             "move": {"W-001": [0.30, 0.40], "W-002": [0.82, 0.30], "W-003": [0.40, 0.52], "W-004": [0.72, 0.72], "W-005": [0.22, 0.42]},
             "ppe": {"W-003": {"helmet": False}, "W-004": {"helmet": True}}, "posture": "Unsafe", "facing_hazard": {"W-004": True}},
            {"id": "W002_CRITICAL", "ticks": 6, "label": "W-002 enters Crane Swing Area without helmet - CRITICAL",
             "move": {"W-001": [0.32, 0.42], "W-002": [0.72, 0.36], "W-003": [0.42, 0.50], "W-004": [0.75, 0.70], "W-005": [0.24, 0.44]},
             "ppe": {"W-002": {"helmet": False}, "W-003": {"helmet": False}}, "posture": "Unsafe", "facing_hazard": {"W-002": True}},
            {"id": "ALL_EXIT", "ticks": 8, "label": "All workers exit hazard zones, PPE restored",
             "move": {"W-001": [0.20, 0.35], "W-002": [0.50, 0.40], "W-003": [0.25, 0.45], "W-004": [0.55, 0.55], "W-005": [0.15, 0.35]},
             "ppe": {"W-002": {"helmet": True}, "W-003": {"helmet": True}}, "posture": "Normal", "facing_hazard": {}},
            {"id": "COMPLETE", "ticks": 3, "label": "Scenario complete — all incidents logged",
             "move": None, "ppe": {}, "posture": "Normal", "facing_hazard": False},
        ],
    },
}

SEVERITY_RANK = {"SAFE": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}


class DemoEngine:
    TICK_SECONDS = 1.2

    def __init__(self, providers: dict, on_event=None, on_snapshot=None):
        self.providers = providers
        self.on_event = on_event or (lambda e: None)
        self.on_snapshot = on_snapshot or (lambda s: None)

        self._lock = threading.RLock()
        self._thread = None
        self._stop_evt = threading.Event()

        self.running = False
        self.tick_count = 0
        self.loop = 0
        self.scenario_id = "crane_approach"
        self.stage_index = 0
        self.stage_tick = 0

        self.mock = providers["mock"]["provider"] if "mock" in providers else MockDetectionProvider()
        self.prox = providers["proximity"]["provider"] if "proximity" in providers else ProximityProvider()

        # Initialize hybrid AI systems
        self.risk_model = get_risk_model()
        self.fusion_engine = get_fusion_engine()
        self.worker_tracker = get_worker_tracker()
        self.voice_system = get_voice_system()

        self.world = {}           # worker_id -> live worker state
        self.zone_list = []       # parsed zone dicts
        self.active_alerts = {}   # worker_id -> {"incident_id", "severity", "root_cause"}
        self._ppe_prev = {}       # worker_id -> last ppe dict (change detection)
        self._in_zone_prev = {}   # worker_id -> last in_zone bool

    # ------------------------------------------------------------------
    # World state (loaded from DB — single source of truth)
    # ------------------------------------------------------------------
    def load_world(self):
        self.zone_list = []
        for z in db.query("SELECT * FROM zones WHERE active=1 ORDER BY id"):
            self.zone_list.append({
                "id": z["id"], "name": z["name"], "label": z["label"],
                "severity": z["severity"], "polygon": json.loads(z["polygon"]) if isinstance(z["polygon"], str) else z["polygon"],
            })
        self.world = {}
        for w in db.query("SELECT * FROM workers"):
            self.world[w["id"]] = {
                "id": w["id"], "name": w["name"], "role": w["role"],
                "x": w["x"], "y": w["y"],
                "ppe": json.loads(w["ppe_status"]) if isinstance(w["ppe_status"], str) else w["ppe_status"],
                "posture": w["posture"] or "Normal",
                "status": w["status"], "risk_score": w["risk_score"], "severity": w["severity"],
                "exposure_time": w["exposure_time"] or 0,
                "facing_vector": [0.3, -0.8] if int(w["id"].split("-")[1]) % 2 else [-0.4, -0.7],
            }

    def _reset_world_to_seed(self):
        """Restore workers to seed/initial state and clear active alerts."""
        self.load_world()
        self.active_alerts = {}
        self._ppe_prev = {}
        self._in_zone_prev = {}
        self.prox._prev = {}
        self.worker_tracker.reset()
        for wid, w in self.world.items():
            db.update_worker_state(wid, status=w["status"], risk_score=w["risk_score"],
                                   severity=w["severity"], x=w["x"], y=w["y"],
                                   posture="Normal", distance=None, closing_speed=0.0,
                                   ppe_status=__import__("json").dumps(w["ppe"]))

    # ------------------------------------------------------------------
    # Scenario control
    # ------------------------------------------------------------------
    @property
    def scenario(self) -> dict:
        return SCENARIOS.get(self.scenario_id, SCENARIOS["crane_approach"])

    def start(self, scenario_id: str = "crane_approach") -> dict:
        with self._lock:
            if scenario_id in SCENARIOS:
                self.scenario_id = scenario_id
            if self.running:
                return {"status": "already_running", "scenario": self.scenario_id}
            self._reset_world_to_seed()
            self.tick_count = 0
            self.loop = 0
            self.stage_index = 0
            self.stage_tick = 0
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="safesight-demo")
            self._thread.start()
            self.running = True
            return {"status": "started", "scenario": self.scenario_id}

    def reset(self) -> dict:
        with self._lock:
            was_running = self.running
            self._stop_evt.set()
            if self._thread:
                self._thread.join(timeout=3)
            self._thread = None
            self.running = False
            self._reset_world_to_seed()
            self.tick_count = 0
            self.stage_index = 0
            self.stage_tick = 0
            for inc in db.query("SELECT id FROM incidents WHERE status IN ('OPEN','ACKNOWLEDGED')"):
                db.update_incident_status(inc["id"], "AUTO_RESOLVED")
            return {"status": "reset", "was_running": was_running}

    def _run(self):
        """Background loop — one scenario pass, then repeats until stopped."""
        try:
            while not self._stop_evt.is_set():
                self._tick()
                self._stop_evt.wait(self.TICK_SECONDS)
        except Exception:
            traceback.print_exc()
        finally:
            self.running = False

    # ------------------------------------------------------------------
    # One processing tick — the full hybrid pipeline
    # ------------------------------------------------------------------
    def _advance_scenario(self) -> dict:
        stages = self.scenario["stages"]
        stage = stages[self.stage_index]
        self.stage_tick += 1
        if self.stage_tick > stage["ticks"]:
            self.stage_index += 1
            self.stage_tick = 1
            if self.stage_index >= len(stages):
                self.stage_index = 0
                self.stage_tick = 1
                self.loop += 1
            stage = stages[self.stage_index]
        return stage

    def _apply_stage(self, stage: dict):
        """Apply scenario stage effects to workers."""
        stage_data = stage.get("move")
        ppe_data = stage.get("ppe", {})
        posture_data = stage.get("posture", "Normal")
        facing_data = stage.get("facing_hazard", False)

        # Determine if multi-worker format (values are dicts)
        def is_multi_worker(data):
            return isinstance(data, dict) and data and all(isinstance(v, dict) for v in data.values())

        # Handle movement
        if is_multi_worker(stage_data):
            for wid, target in stage_data.items():
                w = self.world.get(wid)
                if not w:
                    continue
                dx, dy = target[0] - w["x"], target[1] - w["y"]
                w["x"] = round(w["x"] + dx * 0.2, 4)
                w["y"] = round(w["y"] + dy * 0.2, 4)
        elif stage_data:
            wid = self.scenario["worker"]
            w = self.world.get(wid)
            if w:
                dx, dy = stage_data[0] - w["x"], stage_data[1] - w["y"]
                if stage["id"] == "APPROACH":
                    progress = self.stage_tick / max(1, stage["ticks"])
                    frac = (2 * progress - progress * progress) - (2 * (progress - 1 / max(1, stage["ticks"])) - (progress - 1 / max(1, stage["ticks"])) ** 2)
                    frac = max(0.05, frac)
                else:
                    frac = 1.0 / max(1, stage["ticks"])
                w["x"] = round(w["x"] + dx * min(1.0, frac), 4)
                w["y"] = round(w["y"] + dy * min(1.0, frac), 4)

        # Apply PPE changes
        if is_multi_worker(ppe_data):
            for wid, ppe_changes in ppe_data.items():
                w = self.world.get(wid)
                if w:
                    for item, val in ppe_changes.items():
                        w["ppe"][item] = val
        elif ppe_data:
            wid = self.scenario["worker"]
            w = self.world.get(wid)
            if w:
                for item, val in ppe_data.items():
                    w["ppe"][item] = val

        # Apply posture
        if is_multi_worker(posture_data):
            for wid, post in posture_data.items():
                w = self.world.get(wid)
                if w:
                    w["posture"] = post
        else:
            wid = self.scenario["worker"]
            w = self.world.get(wid)
            if w:
                w["posture"] = posture_data

        # Apply facing
        if is_multi_worker(facing_data):
            for wid, face_hazard in facing_data.items():
                w = self.world.get(wid)
                if w and face_hazard and self.zone_list:
                    nearest = min(self.zone_list, key=lambda z: (z["polygon"][0][0] - w["x"]) ** 2 + (z["polygon"][0][1] - w["y"]) ** 2)
                    poly = nearest["polygon"]
                    cx = sum(p[0] for p in poly) / len(poly)
                    cy = sum(p[1] for p in poly) / len(poly)
                    fx, fy = cx - w["x"], cy - w["y"]
                    mag = max(1e-6, (fx * fx + fy * fy) ** 0.5)
                    w["facing_vector"] = [round(fx / mag, 3), round(fy / mag, 3)]
                elif w:
                    w["facing_vector"] = [0.3, -0.8] if int(wid.split("-")[1]) % 2 else [-0.4, -0.7]
        elif facing_data:
            wid = self.scenario["worker"]
            w = self.world.get(wid)
            if w and self.zone_list:
                nearest = min(self.zone_list, key=lambda z: (z["polygon"][0][0] - w["x"]) ** 2 + (z["polygon"][0][1] - w["y"]) ** 2)
                poly = nearest["polygon"]
                cx = sum(p[0] for p in poly) / len(poly)
                cy = sum(p[1] for p in poly) / len(poly)
                fx, fy = cx - w["x"], cy - w["y"]
                mag = max(1e-6, (fx * fx + fy * fy) ** 0.5)
                w["facing_vector"] = [round(fx / mag, 3), round(fy / mag, 3)]
            elif w:
                w["facing_vector"] = [0.3, -0.8] if int(wid.split("-")[1]) % 2 else [-0.4, -0.7]

    def _tick(self):
        with self._lock:
            if not self.running:
                return
            self.tick_count += 1
            stage = self._advance_scenario()
            self._apply_stage(stage)

            dt = self.TICK_SECONDS
            workers_out = []
            all_detections = []

            # Prepare detections for tracker
            for wid, w in self.world.items():
                # Create mock detection for tracker
                x, y = w["x"], w["y"]
                bbox = [x - 0.04, y - 0.09, x + 0.04, y + 0.09]
                all_detections.append({
                    "id": wid,
                    "box": bbox,
                    "confidence": 0.9,
                    "x": x, "y": y,
                    "ppe": w["ppe"],
                    "posture": w["posture"],
                    "facing_vector": w["facing_vector"],
                })

            # Update tracker
            tracks = self.worker_tracker.update(all_detections)

            # Process each worker through hybrid fusion engine
            for wid, w in self.world.items():
                # Compute proximity
                prox = self.prox.compute_proximity(
                    {"id": wid, "x": w["x"], "y": w["y"], "facing_vector": w["facing_vector"]},
                    self.zone_list, dt=dt)

                # Run hybrid risk assessment
                fusion_result = self.fusion_engine.process_worker(
                    w, prox, all_detections,
                    tracking_id=self.worker_tracker.get_track_by_worker_id(wid).tracking_id if self.worker_tracker.get_track_by_worker_id(wid) else None
                )

                # Exposure time
                if prox["in_zone"]:
                    w["exposure_time"] = round(w["exposure_time"] + dt / 60.0, 2)

                # Merge data
                merged = dict(w)
                merged.update(prox)
                merged.update({
                    "risk_score": fusion_result.risk_assessment.final_risk_score,
                    "severity": fusion_result.risk_assessment.severity,
                    "risk_level": fusion_result.risk_assessment.risk_level,
                    "breakdown": fusion_result.risk_assessment.breakdown,
                    "root_cause": fusion_result.risk_assessment.root_cause,
                    "recommendation": fusion_result.risk_assessment.recommendation,
                    "ml_probability": fusion_result.risk_assessment.ml_probability,
                    "overrides": fusion_result.risk_assessment.overrides,
                })
                workers_out.append(merged)

                # DEMO TRACE: Log worker position and risk
                print(f"[DEMO TRACE] worker={wid} pos=({w['x']:.2f},{w['y']:.2f}) zone={prox.get('zone')} in_zone={prox.get('in_zone')} dist={prox.get('distance')} risk={fusion_result.risk_assessment.final_risk_score:.1f} severity={fusion_result.risk_assessment.severity} voice_triggered={fusion_result.voice_alert_triggered}")

                # Persist state
                db.update_worker_state(wid, x=w["x"], y=w["y"],
                                       risk_score=fusion_result.risk_assessment.final_risk_score,
                                       severity=fusion_result.risk_assessment.severity,
                                       posture=w["posture"],
                                       distance=prox["distance"],
                                       closing_speed=prox["closing_speed"],
                                       facing_angle=prox["facing_angle"],
                                       status=fusion_result.risk_assessment.severity,
                                       current_zone=prox["zone"] or "Assembly Zone",
                                       exposure_time=w["exposure_time"],
                                       last_seen=_now())
                self._log_events(wid, merged, prox)

                # Handle alerts with voice
                self._handle_alerts(merged, prox, fusion_result)

            # Broadcast snapshot
            self.on_snapshot(self.build_snapshot(workers_out, stage))

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------
    def _log_events(self, wid: str, merged: dict, prox: dict):
        cam = self.scenario["camera"]
        ppe = merged["ppe"]
        prev_ppe = self._ppe_prev.get(wid)
        changed = prev_ppe != ppe
        if changed:
            self._ppe_prev[wid] = dict(ppe)
        compliant = all(ppe.get(item, True) for item in ("helmet", "vest", "gloves"))
        if changed or not compliant:
            db.execute("""INSERT INTO ppe_events (timestamp,worker_id,camera_id,helmet,vest,gloves,compliant)
                          VALUES (?,?,?,?,?,?,?)""",
                       (_now(), wid, cam, int(bool(ppe.get("helmet"))), int(bool(ppe.get("vest"))),
                        int(bool(ppe.get("gloves"))), int(compliant)))
            self.on_event({"type": "ppe_event", "worker_id": wid, "ppe": ppe, "compliant": compliant,
                           "time": _now_hm()})

        if prox["in_zone"] or (prox["distance"] is not None and prox["distance"] < 10):
            db.execute("""INSERT INTO proximity_events (timestamp,worker_id,camera_id,zone_id,
                          distance,closing_speed,facing_angle,event_type)
                          VALUES (?,?,?,?,?,?,?,?)""",
                       (_now(), wid, cam, prox["zone_id"], prox["distance"],
                        prox["closing_speed"], prox["facing_angle"],
                        "ZONE_ENTRY" if prox["in_zone"] else "PROXIMITY"))

        if merged["posture"] != "Normal":
            db.execute("""INSERT INTO posture_events (timestamp,worker_id,camera_id,posture,severity)
                          VALUES (?,?,?,?,?)""",
                       (_now(), wid, cam, merged["posture"], "HIGH" if merged["posture"] == "Severe" else "WARNING"))
            self.on_event({"type": "posture_event", "worker_id": wid, "posture": merged["posture"],
                           "time": _now_hm()})

    # ------------------------------------------------------------------
    # Alert lifecycle with voice integration
    # ------------------------------------------------------------------
    def _handle_alerts(self, worker: dict, prox: dict, fusion_result):
        wid = worker["id"]
        sev = worker["severity"]
        score = worker["risk_score"]
        existing = self.active_alerts.get(wid)

        # Check if worker just exited a hazard zone (for clear announcement)
        was_in_zone = self._in_zone_prev.get(wid, False)
        now_in_zone = prox["in_zone"]
        self._in_zone_prev[wid] = now_in_zone

        # ALERT TRACE: Check alert decision
        if sev in ("WARNING", "HIGH", "CRITICAL"):
            print(f"[ALERT TRACE] worker={wid} severity={sev} score={score} in_zone={prox.get('in_zone')} root_cause={worker.get('root_cause')} existing_alert={existing is not None}")
            if existing is None:
                inc_id = self._create_incident(worker, prox, fusion_result)
                self.active_alerts[wid] = {"incident_id": inc_id, "severity": sev,
                                           "root_cause": worker["root_cause"]}
                self.on_event({"type": "alert", "alert": self._alert_payload(worker, inc_id, "OPEN", fusion_result),
                               "time": _now_hm()})
                print(f"[ALERT CREATED] worker={wid} severity={sev} message={worker.get('root_cause')}")
                # Trigger voice alert
                if fusion_result.voice_alert_triggered:
                    print(f"[VOICE TRACE 1] Alert received by voice decision layer: worker={wid}, severity={sev}, voice_triggered={fusion_result.voice_alert_triggered}, message={fusion_result.voice_message[:80]}")
                    self.voice_system.create_alert(
                        worker_id=wid,
                        worker_name=worker.get("name", wid),
                        severity=sev,
                        root_cause=worker["root_cause"],
                        zone=worker.get("zone") or "Unknown",
                        message=fusion_result.voice_message,
                    )
                else:
                    print(f"[VOICE TRACE 1] Voice NOT triggered: worker={wid}, severity={sev}, voice_triggered={fusion_result.voice_alert_triggered}, overrides={fusion_result.risk_assessment.overrides}")
            elif SEVERITY_RANK[sev] > SEVERITY_RANK[existing["severity"]]:
                # Escalation
                db.execute("UPDATE incidents SET risk_score=?, severity=?, root_cause=?, status='OPEN' WHERE id=?",
                           (score, sev, worker["root_cause"], existing["incident_id"]))
                existing["severity"] = sev
                existing["root_cause"] = worker["root_cause"]
                payload = self._alert_payload(worker, existing["incident_id"], "OPEN", fusion_result)
                payload["escalated"] = True
                self.on_event({"type": "alert", "alert": payload, "time": _now_hm()})
                # Trigger escalation voice alert
                if fusion_result.voice_alert_triggered:
                    self.voice_system.create_alert(
                        worker_id=wid,
                        worker_name=worker.get("name", wid),
                        severity=sev,
                        root_cause=worker["root_cause"],
                        zone=worker.get("zone") or "Unknown",
                        message=fusion_result.voice_message,
                    )
            else:
                db.execute("UPDATE incidents SET risk_score=? WHERE id=?", (score, existing["incident_id"]))
        else:
            # Risk dropped - auto-resolve
            if existing:
                was = existing["severity"]
                nm = 1 if SEVERITY_RANK[was] <= SEVERITY_RANK["HIGH"] else 0
                db.execute("UPDATE incidents SET status='AUTO_RESOLVED', near_miss=?, risk_score=? WHERE id=?",
                           (nm, score, existing["incident_id"]))
                del self.active_alerts[wid]
                self.on_event({"type": "resolved", "incident_id": existing["incident_id"],
                               "worker_id": wid, "status": "AUTO_RESOLVED",
                               "near_miss": bool(nm), "time": _now_hm()})
                # Announce zone clear if worker was in zone
                if was_in_zone and not now_in_zone:
                    self.voice_system.create_clear_announcement(wid, worker.get("name", wid), worker.get("zone") or "the area")

    def _create_incident(self, worker: dict, prox: dict, fusion_result) -> int:
        etype = self._event_type(worker)
        desc = f"Worker {worker['id']} in {worker.get('zone') or 'assembly area'}."
        if prox["in_zone"] and worker.get("zone"):
            desc = f"Worker {worker['id']} entered {worker['zone']}."

        # Get tracking ID
        track = self.worker_tracker.get_track_by_worker_id(worker["id"])
        tracking_id = track.tracking_id if track else None

        return db.insert_incident({
            "timestamp": _now(), "worker_id": worker["id"], "camera_id": self.scenario["camera"],
            "zone_id": prox["zone_id"], "event_type": etype, "risk_score": worker["risk_score"],
            "severity": worker["severity"], "root_cause": worker["root_cause"],
            "ppe_status": worker["ppe"], "distance": prox["distance"],
            "facing_angle": prox["facing_angle"], "closing_speed": prox["closing_speed"],
            "posture_status": worker["posture"], "status": "OPEN",
            "recommendation": worker["recommendation"], "breakdown": worker["breakdown"],
            "description": desc, "near_miss": 0,
            "ml_probability": fusion_result.risk_assessment.ml_probability,
            "voice_alert": fusion_result.voice_alert_triggered,
            "voice_message": fusion_result.voice_message,
            "model_version": fusion_result.risk_assessment.model_version,
            "feature_version": fusion_result.risk_assessment.feature_version,
            "tracking_id": tracking_id,
        })

    @staticmethod
    def _event_type(worker: dict) -> str:
        cats = {f["category"] for f in worker.get("breakdown", [])}
        if "ppe" in cats and ("proximity" in cats or "zone" in cats):
            return "HAZARD_PROXIMITY"
        if "ppe" in cats:
            return "PPE_VIOLATION"
        if "posture" in cats:
            return "UNSAFE_POSTURE"
        if "proximity" in cats or "zone" in cats:
            return "HAZARD_PROXIMITY"
        return "SAFE_EVENT"

    def _alert_payload(self, worker: dict, incident_id: int, status: str, fusion_result) -> dict:
        return {
            "incident_id": incident_id, "time": _now_hm(), "timestamp": _now(),
            "worker_id": worker["id"], "worker_name": worker.get("name"),
            "zone": worker.get("zone") or "Assembly Area", "zone_id": worker.get("zone_id"),
            "risk_score": worker["risk_score"], "severity": worker["severity"],
            "root_cause": worker["root_cause"], "recommendation": worker["recommendation"],
            "ppe": worker["ppe"], "distance": worker.get("distance"),
            "facing_angle": worker.get("facing_angle"), "closing_speed": worker.get("closing_speed"),
            "posture": worker.get("posture"), "status": status,
            "breakdown": worker.get("breakdown", []),
            "ml_probability": fusion_result.risk_assessment.ml_probability,
            "overrides": fusion_result.risk_assessment.overrides,
            "voice_alert": fusion_result.voice_alert_triggered,
            "voice_message": fusion_result.voice_message,
            "model_version": fusion_result.risk_assessment.model_version,
            "feature_version": fusion_result.risk_assessment.feature_version,
        }

    # ------------------------------------------------------------------
    # Snapshot for the frontend monitoring panel
    # ------------------------------------------------------------------
    def build_snapshot(self, workers_out=None, stage=None) -> dict:
        if workers_out is None:
            workers_out = []
            for wid, w in self.world.items():
                prox = self.prox.compute_proximity(
                    {"id": wid, "x": w["x"], "y": w["y"], "facing_vector": w["facing_vector"]},
                    self.zone_list, dt=1.0)
                a = assess_risk({
                    "ppe": w["ppe"], "distance": prox["distance"], "in_zone": prox["in_zone"],
                    "zone_severity": prox["zone_severity"], "facing_hazard": prox["facing_hazard"],
                    "facing_away": prox["facing_away"], "closing_speed": 0.0, "posture": w["posture"],
                })
                m = dict(w)
                m.update(prox)
                m.update({k: a[k] for k in ("risk_score", "severity", "risk_level",
                                            "breakdown", "root_cause", "recommendation")})
                workers_out.append(m)
            stage = self.scenario["stages"][0]
        stages = self.scenario["stages"]
        sidx = stages.index(stage) if stage in stages else 0

        # Get tracking info
        tracks = self.worker_tracker.get_all_tracks()

        return {
            "type": "snapshot",
            "tick": self.tick_count,
            "mode": "DEMO",
            "camera": {"id": self.scenario["camera"], "name": "Main Construction Zone"},
            "fps": 24,
            "time": _now_hm(),
            "scenario": {
                "id": self.scenario["id"], "name": self.scenario["name"],
                "description": self.scenario["description"],
                "stage": stage["id"], "stage_label": stage["label"],
                "stage_index": sidx + 1, "total_stages": len(stages),
                "loop": self.loop, "running": self.running,
            },
            "ai_mode": self._ai_mode(),
            "providers": {k: {"name": v["name"], "available": v["available"], "mode": v["mode"]}
                          for k, v in self.providers.items()},
            "workers": workers_out,
            "zones": self.zone_list,
            "tracks": [
                {
                    "tracking_id": t.tracking_id,
                    "worker_id": t.worker_id,
                    "state": t.state,
                    "bbox": t.bbox,
                    "confidence": t.confidence,
                }
                for t in tracks
            ],
            "active_alerts": len(self.active_alerts),
            "voice_status": self.voice_system.get_status(),
        }

    def _ai_mode(self) -> str:
        if self.risk_model.is_model_loaded():
            return "HYBRID"
        ppe_real = self.providers.get("ppe", {}).get("available")
        pose_real = self.providers.get("pose", {}).get("available")
        if ppe_real and pose_real:
            return "YOLO + POSE"
        if ppe_real or pose_real:
            return "YOLO (partial)"
        return "DEMO"