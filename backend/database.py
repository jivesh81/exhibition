"""
SafeSight AI — Database layer (SQLite)
======================================
Group 173 Prototype

Tables: workers, zones, cameras, incidents, ppe_events,
        proximity_events, posture_events

Every generated alert is automatically stored here. Seed data (deterministic,
seeded RNG) is inserted on first run so KPI values are realistic AND stable
across page refreshes — they come from the database, not random numbers.
"""

import json
import os
import random
import sqlite3
import threading
from datetime import datetime, timedelta

from risk_engine import assess_risk
from risk_config import RISK_CONFIG

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "safesight.db")

_conn = None
_lock = threading.RLock()


# ----------------------------------------------------------------------
# Connection / low-level helpers
# ----------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def query(sql: str, params=()) -> list:
    with _lock:
        cur = get_conn().execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return rows


def query_one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> int:
    """Write helper — returns lastrowid."""
    with _lock:
        cur = get_conn().execute(sql, params)
        get_conn().commit()
        return cur.lastrowid


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
    id            TEXT PRIMARY KEY,
    name          TEXT,
    role          TEXT,
    status        TEXT DEFAULT 'SAFE',
    current_zone  TEXT,
    x             REAL DEFAULT 0.2,
    y             REAL DEFAULT 0.35,
    ppe_status    TEXT DEFAULT '{}',
    distance      REAL,
    facing_angle  REAL DEFAULT 0,
    closing_speed REAL DEFAULT 0,
    posture       TEXT DEFAULT 'Normal',
    risk_score    REAL DEFAULT 0,
    severity      TEXT DEFAULT 'SAFE',
    last_seen     TEXT,
    exposure_time REAL DEFAULT 0,
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS zones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT,
    label      TEXT,
    severity   TEXT DEFAULT 'danger',
    polygon    TEXT,
    camera_id  TEXT DEFAULT 'CAM-01',
    active     INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS cameras (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    location    TEXT,
    status      TEXT DEFAULT 'ONLINE',
    input_mode  TEXT DEFAULT 'DEMO',
    fps         INTEGER DEFAULT 24,
    resolution  TEXT DEFAULT '1280 x 720'
);
CREATE TABLE IF NOT EXISTS incidents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT,
    worker_id     TEXT,
    camera_id     TEXT,
    zone_id       TEXT,
    event_type    TEXT,
    risk_score    REAL,
    severity      TEXT,
    root_cause    TEXT,
    ppe_status    TEXT,
    distance      REAL,
    facing_angle  REAL,
    closing_speed REAL,
    posture_status TEXT,
    status        TEXT DEFAULT 'OPEN',
    recommendation TEXT,
    breakdown     TEXT,
    description   TEXT,
    near_miss     INTEGER DEFAULT 0,
    ml_probability REAL,
    voice_alert   INTEGER DEFAULT 0,
    voice_message TEXT,
    model_version TEXT,
    feature_version TEXT,
    tracking_id   INTEGER
);
CREATE TABLE IF NOT EXISTS ppe_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT,
    worker_id  TEXT,
    camera_id  TEXT,
    helmet     INTEGER,
    vest       INTEGER,
    gloves     INTEGER,
    compliant  INTEGER
);
CREATE TABLE IF NOT EXISTS proximity_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT,
    worker_id     TEXT,
    camera_id     TEXT,
    zone_id       TEXT,
    distance      REAL,
    closing_speed REAL,
    facing_angle  REAL,
    event_type    TEXT
);
CREATE TABLE IF NOT EXISTS posture_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT,
    worker_id  TEXT,
    camera_id  TEXT,
    posture    TEXT,
    severity   TEXT
);
CREATE TABLE IF NOT EXISTS voice_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT,
    worker_id  TEXT,
    worker_name TEXT,
    severity   TEXT,
    message    TEXT,
    root_cause TEXT,
    zone       TEXT,
    status     TEXT DEFAULT 'SPOKEN'
);
"""


def init_db():
    """Create tables and seed demonstration data on first run."""
    with _lock:
        get_conn().executescript(SCHEMA)
        get_conn().commit()
    if query_one("SELECT COUNT(*) AS n FROM workers")["n"] == 0:
        seed_database()
        print("[SafeSight] Database seeded with demonstration data.")
    else:
        print("[SafeSight] Database ready.")


# ----------------------------------------------------------------------
# Seed data
# ----------------------------------------------------------------------
def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def seed_database():
    rng = random.Random(173)  # deterministic — Group 173
    now = datetime.now()

    # --- Cameras -------------------------------------------------------
    cameras = [
        ("CAM-01", "Main Construction Zone", "North Yard", "ONLINE", "DEMO", 24, "1280 x 720"),
        ("CAM-02", "Loading Bay",            "East Gate", "ONLINE", "DEMO", 15, "1280 x 720"),
    ]
    for c in cameras:
        execute("""INSERT INTO cameras (id,name,location,status,input_mode,fps,resolution)
                   VALUES (?,?,?,?,?,?,?)""", c)

    # --- Hazard zones (normalized polygon coords on camera view) -------
    zones = [
        ("Crane Swing Area",       "ZONE A", "danger",
         [[0.60, 0.15], [0.96, 0.15], [0.96, 0.52], [0.60, 0.52]], "CAM-01"),
        ("Restricted Area",        "ZONE B", "critical",
         [[0.60, 0.60], [0.96, 0.60], [0.96, 0.92], [0.60, 0.92]], "CAM-01"),
        ("Machine Operating Area", "ZONE C", "warning",
         [[0.04, 0.55], [0.40, 0.55], [0.40, 0.88], [0.04, 0.88]], "CAM-01"),
    ]
    zone_ids = {}
    for name, label, severity, polygon, cam in zones:
        zid = execute("""INSERT INTO zones (name,label,severity,polygon,camera_id,active,created_at)
                         VALUES (?,?,?,?,?,1,?)""",
                      (name, label, severity, json.dumps(polygon), cam, _iso(now)))
        zone_ids[label] = zid

    # --- Workers (12) — risk computed with the REAL risk engine --------
    from detection.proximity import ProximityProvider
    prox = ProximityProvider()
    zone_list = query("SELECT * FROM zones WHERE camera_id='CAM-01'")
    for z in zone_list:
        z["polygon"] = json.loads(z["polygon"])

    workers = [
        ("W-001", "Ravi Sharma",   "Crane Operator",   0.30, 0.35, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-002", "Arjun Patel",   "Welder",           0.45, 0.45, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-003", "Meera Iyer",    "Electrician",      0.18, 0.40, {"helmet": True,  "vest": True,  "gloves": False}),
        ("W-004", "David Chen",    "Mason",            0.25, 0.28, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-005", "Sofia Alvarez", "Machine Operator", 0.30, 0.62, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-006", "John Mathew",   "Carpenter",        0.12, 0.30, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-007", "Ahmed Khan",    "Steel Fixer",      0.50, 0.68, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-008", "Priya Nair",    "Safety Inspector", 0.10, 0.20, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-009", "Carlos Silva",  "Welder",           0.38, 0.32, {"helmet": True,  "vest": True,  "gloves": False}),
        ("W-010", "Li Wei",        "Rigger",           0.22, 0.50, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-011", "Omar Farouk",   "Electrician",      0.14, 0.45, {"helmet": True,  "vest": True,  "gloves": True}),
        ("W-012", "Tom Becker",    "Painter",          0.42, 0.25, {"helmet": True,  "vest": True,  "gloves": True}),
    ]
    for wid, name, role, x, y, ppe in workers:
        d = prox.compute_proximity({"id": wid, "x": x, "y": y}, zone_list, dt=1.0)
        assessment = assess_risk({
            "ppe": ppe, "distance": d["distance"], "in_zone": d["in_zone"],
            "zone_severity": d["zone_severity"], "facing_hazard": False,
            "facing_away": False, "closing_speed": 0.0, "posture": "Normal",
        })
        exposure = {"W-002": 14.0, "W-005": 22.0, "W-007": 8.0}.get(wid, rng.choice([0, 0, 2, 4]))
        execute("""INSERT INTO workers (id,name,role,status,current_zone,x,y,ppe_status,
                   distance,facing_angle,closing_speed,posture,risk_score,severity,
                   last_seen,exposure_time,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (wid, name, role, assessment["severity"], d["zone"] or "Assembly Zone",
                 x, y, json.dumps(ppe), d["distance"], d["facing_angle"], 0.0,
                 "Normal", assessment["risk_score"], assessment["severity"],
                 _iso(now), float(exposure), _iso(now)))

    # --- Incident seeds (today: 18 — 2 CRITICAL / 5 HIGH / 7 WARNING / 4 SAFE)
    #     Open alerts = 2 (1 CRITICAL, 1 HIGH). Near-misses across week: 12.
    def _mk_incident(day_offset, hour, minute, wid, zlabel, etype, risk, severity,
                     root, ppe, dist, facing, speed, posture, status, rec,
                     near_miss=0, desc=None):
        ts = _iso(now.replace(hour=hour, minute=minute, second=rng.randint(0, 59))
                  - timedelta(days=day_offset))
        zone_id = zone_ids.get(zlabel)
        breakdown = json.dumps([{"factor": root.title(), "category": "seed", "points": risk}])
        execute("""INSERT INTO incidents (timestamp,worker_id,camera_id,zone_id,event_type,
                   risk_score,severity,root_cause,ppe_status,distance,facing_angle,
                   closing_speed,posture_status,status,recommendation,breakdown,
                   description,near_miss)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, wid, "CAM-01", zone_id, etype, risk, severity, root,
                 json.dumps(ppe), dist, facing, speed, posture, status, rec,
                 breakdown, desc or f"Worker {wid} — {root.lower()} event detected.", near_miss))

    ppe_ok = {"helmet": True, "vest": True, "gloves": True}
    ppe_no_helmet = {"helmet": False, "vest": True, "gloves": True}

    # Today — CRITICAL (1 open, 1 resolved)
    _mk_incident(0, 12, 41, "W-002", "ZONE A", "HAZARD_PROXIMITY", 88, "CRITICAL",
                 "PPE NON-COMPLIANCE + INATTENTIVENESS", ppe_no_helmet, 3.2, 18, 2.1,
                 "Unsafe", "OPEN", "Immediate supervisor intervention recommended.",
                 desc="Worker W-002 entered Crane Swing Area without helmet.")
    _mk_incident(0, 9, 12, "W-007", "ZONE B", "HAZARD_PROXIMITY", 79, "CRITICAL",
                 "UNSAFE PROXIMITY", ppe_ok, 2.4, 31, 1.8, "Normal", "RESOLVED",
                 "Immediate supervisor intervention recommended.",
                 desc="Worker W-007 entered Restricted Area.")

    # Today — HIGH (1 open, 1 acknowledged, 2 auto-resolved near-miss, 1 resolved)
    _mk_incident(0, 12, 8, "W-005", "ZONE C", "HAZARD_PROXIMITY", 68, "HIGH",
                 "UNSAFE PROXIMITY", ppe_ok, 2.8, 25, 1.2, "Normal", "OPEN",
                 "Supervisor intervention recommended.",
                 desc="Worker W-005 too close to operating machine.")
    _mk_incident(0, 11, 24, "W-003", "ZONE C", "PPE_VIOLATION", 61, "HIGH",
                 "PPE NON-COMPLIANCE", {"helmet": True, "vest": True, "gloves": False},
                 4.1, 0, 0.4, "Normal", "ACKNOWLEDGED", "Stop worker entry until PPE compliance is restored.",
                 desc="Worker W-033 missing safety gloves near operating machine.")
    _mk_incident(0, 10, 47, "W-002", "ZONE A", "HAZARD_PROXIMITY", 58, "HIGH",
                 "UNSAFE PROXIMITY + INATTENTIVENESS", ppe_ok, 3.8, 40, 1.6, "Normal",
                 "AUTO_RESOLVED", "Supervisor intervention recommended.",
                 near_miss=1, desc="Worker W-002 approached crane swing area, then exited.")
    _mk_incident(0, 8, 55, "W-009", "ZONE A", "PPE_VIOLATION", 52, "HIGH",
                 "PPE NON-COMPLIANCE", ppe_no_helmet, 4.6, 0, 0.9, "Normal", "AUTO_RESOLVED",
                 "Stop worker entry until helmet compliance is restored.",
                 near_miss=1, desc="Worker W-009 entered crane area, helmet restored on exit.")
    _mk_incident(0, 7, 38, "W-010", None, "UNSAFE_POSTURE", 55, "HIGH",
                 "UNSAFE POSTURE", ppe_ok, 12.0, 0, 0.3, "Severe", "RESOLVED",
                 "Review worker posture and task ergonomics.",
                 desc="Worker W-010 severe posture — possible fall risk.")

    # Today — WARNING (7: 2 acknowledged, 5 resolved)
    warnings = [
        (12, 20, "W-006", "ZONE C", "HAZARD_PROXIMITY", 41, "UNSAFE PROXIMITY", 4.8),
        (11, 52, "W-001", "ZONE A", "HAZARD_PROXIMITY", 38, "UNSAFE PROXIMITY", 5.4),
        (11, 5,  "W-012", None,    "PPE_VIOLATION",   30, "PPE NON-COMPLIANCE", 14.0),
        (10, 33, "W-011", "ZONE C", "HAZARD_PROXIMITY", 35, "UNSAFE PROXIMITY", 5.1),
        (9, 44,  "W-007", "ZONE B", "HAZARD_PROXIMITY", 45, "UNSAFE PROXIMITY", 4.2),
        (8, 18,  "W-004", "ZONE C", "HAZARD_PROXIMITY", 33, "UNSAFE PROXIMITY", 5.6),
        (7, 10,  "W-003", None,    "PPE_VIOLATION",   27, "PPE NON-COMPLIANCE", 15.0),
    ]
    for i, (h, m, wid, zl, et, risk, root, dist) in enumerate(warnings):
        _mk_incident(0, h, m, wid, zl, et, risk, "WARNING", root, ppe_ok, dist,
                     0, 0.5, "Normal", "ACKNOWLEDGED" if i < 2 else "RESOLVED",
                     "Monitor worker — warning threshold exceeded.")

    # Today — SAFE events (4, resolved)
    for h, m, wid in [(12, 30, "W-001"), (11, 40, "W-008"), (10, 15, "W-004"), (8, 5, "W-006")]:
        _mk_incident(0, h, m, wid, None, "SAFE_EVENT", rng.randint(4, 18), "SAFE",
                     "NO RISK DETECTED", ppe_ok, rng.uniform(12, 18), 0, 0.0, "Normal",
                     "RESOLVED", "No action required.",
                     desc=f"Worker {wid} — routine safe activity.")

    # Past 7 days — varied history (≈45 incidents, 10 near-misses)
    roots = [("PPE_VIOLATION", "PPE NON-COMPLIANCE", "Stop worker entry until PPE compliance is restored."),
             ("HAZARD_PROXIMITY", "UNSAFE PROXIMITY", "Supervisor intervention recommended."),
             ("HAZARD_PROXIMITY", "UNSAFE PROXIMITY + INATTENTIVENESS", "Immediate supervisor intervention recommended."),
             ("UNSAFE_POSTURE", "UNSAFE POSTURE", "Review worker posture and task ergonomics."),
             ("HAZARD_PROXIMITY", "PROXIMITY + HIGH CLOSING SPEED", "Warn worker and restrict access to active hazard zone.")]
    worker_ids = [w[0] for w in workers]
    zlabels = ["ZONE A", "ZONE B", "ZONE C", None, None]
    for d in range(1, 8):
        for _ in range(rng.randint(5, 8)):
            et, root, rec = rng.choice(roots)
            sev = rng.choices(["CRITICAL", "HIGH", "WARNING", "SAFE"],
                              weights=[0.08, 0.24, 0.42, 0.26])[0]
            risk = {"CRITICAL": rng.randint(75, 94), "HIGH": rng.randint(50, 74),
                    "WARNING": rng.randint(25, 49), "SAFE": rng.randint(2, 22)}[sev]
            status = rng.choice(["RESOLVED", "RESOLVED", "ACKNOWLEDGED", "AUTO_RESOLVED"])
            nm = 1 if (sev == "HIGH" and status == "AUTO_RESOLVED") else 0
            _mk_incident(d, rng.randint(6, 18), rng.randint(0, 59),
                         rng.choice(worker_ids), rng.choice(zlabels), et, risk, sev, root,
                         rng.choice([ppe_ok, ppe_no_helmet]), round(rng.uniform(2, 15), 1),
                         rng.randint(0, 120), round(rng.uniform(0, 2.4), 1),
                         rng.choice(["Normal", "Normal", "Unsafe", "Severe"]),
                         status, rec, near_miss=nm)

    # ensure 12 near-misses total (Near-Miss Intelligence section)
    current_nm = query_one("SELECT COUNT(*) n FROM incidents WHERE near_miss=1")["n"]
    for _ in range(max(0, 12 - current_nm)):
        et, root, rec = rng.choice(roots)
        _mk_incident(rng.randint(1, 7), rng.randint(6, 18), rng.randint(0, 59),
                     rng.choice(worker_ids), rng.choice(zlabels), et,
                     rng.randint(50, 74), "HIGH", root, ppe_ok,
                     round(rng.uniform(2, 6), 1), rng.randint(0, 60), round(rng.uniform(0, 2), 1),
                     "Normal", "AUTO_RESOLVED", rec, near_miss=1,
                     desc="High-risk approach auto-resolved — worker exited hazard zone.")

    # --- ppe_events (7 days, ~91% compliant → PPE compliance KPI) ------
    for d in range(0, 8):
        for _ in range(rng.randint(40, 55)):
            compliant = 1 if rng.random() < 0.91 else 0
            helmet, vest, gloves = 1, 1, 1
            if not compliant:
                item = rng.choice(["helmet", "vest", "gloves"])
                if item == "helmet":
                    helmet = 0
                elif item == "vest":
                    vest = 0
                else:
                    gloves = 0
            ts = _iso(now.replace(hour=rng.randint(6, 18), minute=rng.randint(0, 59))
                      - timedelta(days=d))
            execute("""INSERT INTO ppe_events (timestamp,worker_id,camera_id,helmet,vest,gloves,compliant)
                       VALUES (?,?,?,?,?,?,?)""",
                    (ts, rng.choice(worker_ids), "CAM-01", helmet, vest, gloves, compliant))

    # --- proximity_events (zone entries + close approaches) ------------
    for d in range(0, 8):
        for _ in range(rng.randint(20, 30)):
            et = rng.choices(["PROXIMITY", "ZONE_ENTRY"], weights=[0.7, 0.3])[0]
            ts = _iso(now.replace(hour=rng.randint(6, 18), minute=rng.randint(0, 59))
                      - timedelta(days=d))
            execute("""INSERT INTO proximity_events (timestamp,worker_id,camera_id,zone_id,
                       distance,closing_speed,facing_angle,event_type)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (ts, rng.choice(worker_ids), "CAM-01",
                     zone_ids[rng.choice(["ZONE A", "ZONE B", "ZONE C"])],
                     round(rng.uniform(1, 10), 1), round(rng.uniform(0, 2.4), 1),
                     rng.randint(0, 120), et))

    # --- posture_events -------------------------------------------------
    for d in range(0, 8):
        for _ in range(rng.randint(8, 14)):
            posture = rng.choices(["Unsafe", "Severe"], weights=[0.75, 0.25])[0]
            sev = "HIGH" if posture == "Severe" else "WARNING"
            ts = _iso(now.replace(hour=rng.randint(6, 18), minute=rng.randint(0, 59))
                      - timedelta(days=d))
            execute("""INSERT INTO posture_events (timestamp,worker_id,camera_id,posture,severity)
                       VALUES (?,?,?,?,?)""",
                    (ts, rng.choice(worker_ids), "CAM-01", posture, sev))


# ----------------------------------------------------------------------
# Incident helpers (used by demo engine + API)
# ----------------------------------------------------------------------
def insert_incident(d: dict) -> int:
    """d: keys matching incidents schema; breakdown/ppe_status may be dicts."""
    breakdown = d.get("breakdown")
    breakdown = json.dumps(breakdown) if isinstance(breakdown, (list, dict)) else (breakdown or "[]")
    ppe_status = d.get("ppe_status")
    ppe_status = json.dumps(ppe_status) if isinstance(ppe_status, dict) else (ppe_status or "{}")
    return execute("""INSERT INTO incidents (timestamp,worker_id,camera_id,zone_id,event_type,
        risk_score,severity,root_cause,ppe_status,distance,facing_angle,closing_speed,
        posture_status,status,recommendation,breakdown,description,near_miss,
        ml_probability,voice_alert,voice_message,model_version,feature_version,tracking_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (d.get("timestamp") or _iso(datetime.now()), d.get("worker_id"),
                    d.get("camera_id") or "CAM-01", d.get("zone_id"), d.get("event_type"),
                    d.get("risk_score"), d.get("severity"), d.get("root_cause"),
                    ppe_status, d.get("distance"), d.get("facing_angle"),
                    d.get("closing_speed"), d.get("posture_status"),
                    d.get("status") or "OPEN", d.get("recommendation"), breakdown,
                    d.get("description"), d.get("near_miss") or 0,
                    d.get("ml_probability"), 1 if d.get("voice_alert") else 0,
                    d.get("voice_message"), d.get("model_version"), d.get("feature_version"),
                    d.get("tracking_id")))


def update_incident_status(incident_id: int, status: str):
    execute("UPDATE incidents SET status=? WHERE id=?", (status, incident_id))


def insert_voice_event(worker_id: str, worker_name: str, severity: str,
                       message: str, root_cause: str, zone: str) -> int:
    """Log a voice alert event."""
    return execute("""INSERT INTO voice_events (timestamp,worker_id,worker_name,severity,message,root_cause,zone,status)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (_iso(datetime.now()), worker_id, worker_name, severity, message, root_cause, zone, "SPOKEN"))


def update_worker_state(wid: str, **fields):
    """Update live worker fields (status, risk_score, x, y, ...)."""
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE workers SET {cols} WHERE id=?", (*fields.values(), wid))


if __name__ == "__main__":
    init_db()
    print("workers:   ", query_one("SELECT COUNT(*) n FROM workers")["n"])
    print("zones:     ", query_one("SELECT COUNT(*) n FROM zones")["n"])
    print("incidents: ", query_one("SELECT COUNT(*) n FROM incidents")["n"])
    print("ppe_events:", query_one("SELECT COUNT(*) n FROM ppe_events")["n"])
    print("near_miss: ", query_one("SELECT COUNT(*) n FROM incidents WHERE near_miss=1")["n"])
