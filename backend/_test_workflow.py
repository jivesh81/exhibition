"""End-to-end workflow test: demo scenario -> alerts -> incidents -> WebSocket."""
import json
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read().decode())


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


# --- WebSocket listener (collects live messages in background) ----------
ws_messages = []


def listen_ws():
    try:
        from websockets.sync.client import connect
        with connect("ws://127.0.0.1:8000/ws/alerts") as ws:
            ws_messages.append("CONNECTED")
            end = time.time() + 40
            while time.time() < end:
                try:
                    msg = ws.recv(timeout=1)
                    ws_messages.append(json.loads(msg))
                except Exception:
                    if not ws_messages:
                        pass
    except Exception as e:
        ws_messages.append(f"WS-ERROR: {e}")


t = threading.Thread(target=listen_ws, daemon=True)
t.start()
time.sleep(1)

print("=== 1. RESET DEMO ===")
print(post("/api/demo/reset"))

print("\n=== 2. START LIVE DEMO ===")
print(post("/api/demo/start"))

time.sleep(16)
print("\n=== 3. WORKERS after 16s (W-002 should be approaching) ===")
workers = get("/api/workers")
w2 = [w for w in workers if w["id"] == "W-002"][0]
print(f"W-002: risk={w2['risk_score']} sev={w2['severity']} dist={w2['distance']} zone={w2['current_zone']}")

time.sleep(14)
print("\n=== 4. WORKERS after 30s (should be CRITICAL) ===")
workers = get("/api/workers")
w2 = [w for w in workers if w["id"] == "W-002"][0]
print(f"W-002: risk={w2['risk_score']} sev={w2['severity']} dist={w2['distance']} zone={w2['current_zone']}")
print(f"  root_cause: {w2.get('root_cause')}")
print(f"  breakdown: {[(f['factor'], f['points']) for f in (w2.get('breakdown') or [])]}")

print("\n=== 5. OPEN INCIDENTS ===")
open_incs = get("/api/incidents?status=OPEN")
for i in open_incs[:5]:
    print(f"  #{i['id']} {i['timestamp']} {i['worker_id']} {i['event_type']} risk={i['risk_score']} {i['severity']}")

print("\n=== 6. INCIDENT DETAIL (first open) ===")
if open_incs:
    det = get(f"/api/incidents/{open_incs[0]['id']}")
    print(f"  #{det['id']} root_cause={det['root_cause']}")
    print(f"  recommendation: {det['recommendation']}")
    print(f"  timeline entries: {len(det['timeline'])}")

print("\n=== 7. WAIT FOR EXIT + AUTO-RESOLVE (~20s more) ===")
time.sleep(20)
w2 = [w for w in get("/api/workers") if w["id"] == "W-002"][0]
print(f"W-002 now: risk={w2['risk_score']} sev={w2['severity']} zone={w2['current_zone']}")

print("\n=== 8. DASHBOARD (should reflect demo events) ===")
d = get("/api/dashboard")
print(f"  today_incidents={d['today_incidents']} critical={d['critical']} high={d['high']} warning={d['warning']} open={d['open_alerts']} near={d['near_misses']}")

print("\n=== 9. ANALYTICS (should have updated) ===")
a = get("/api/analytics")
print(f"  today count in over_time: {a['incidents_over_time'][-1]}")
print(f"  near_misses: {a['near_misses']}")

print("\n=== 10. RESET DEMO (cleanup) ===")
print(post("/api/demo/reset"))

print("\n=== WEBSOCKET MESSAGES RECEIVED ===")
alerts = [m for m in ws_messages if isinstance(m, dict) and m.get("type") == "alert"]
snaps = [m for m in ws_messages if isinstance(m, dict) and m.get("type") == "snapshot"]
others = [m for m in ws_messages if isinstance(m, str) or (isinstance(m, dict) and m.get("type") not in ("alert", "snapshot"))]
print(f"  connected: {'CONNECTED' in ws_messages}")
print(f"  alert messages: {len(alerts)}")
for al in alerts[:6]:
    aa = al["alert"]
    print(f"    {aa['time']} {aa['severity']} {aa['worker_id']} risk={aa['risk_score']} {aa['root_cause']}")
print(f"  snapshots: {len(snaps)}")
print(f"  other messages: {len(others)}")
print("\nDONE")
