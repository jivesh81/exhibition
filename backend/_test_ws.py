"""Focused WebSocket delivery test against the fixed server."""
import json
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
ws_messages = []


def listen_ws():
    try:
        from websockets.sync.client import connect
        with connect("ws://127.0.0.1:8000/ws/alerts") as ws:
            ws_messages.append({"type": "connected"})
            end = time.time() + 30
            while time.time() < end:
                try:
                    ws_messages.append(json.loads(ws.recv(timeout=1)))
                except Exception as e:
                    if "closed" in str(e).lower():
                        ws_messages.append({"type": "ws-error", "error": str(e)})
                        break
    except Exception as e:
        ws_messages.append({"type": "ws-error", "error": str(e)})


def post(path):
    req = urllib.request.Request(BASE + path, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


t = threading.Thread(target=listen_ws, daemon=True)
t.start()
time.sleep(1)
post("/api/demo/reset")
post("/api/demo/start")
time.sleep(26)
post("/api/demo/reset")

alerts = [m for m in ws_messages if isinstance(m, dict) and m.get("type") == "alert"]
snaps = [m for m in ws_messages if isinstance(m, dict) and m.get("type") == "snapshot"]
resolved = [m for m in ws_messages if isinstance(m, dict) and m.get("type") == "resolved"]
connected = any(isinstance(m, dict) and m.get("type") == "connected" for m in ws_messages)
print(f"connected: {connected}")
print(f"snapshots: {len(snaps)}")
print(f"alert messages: {len(alerts)}")
for a in alerts[:8]:
    aa = a["alert"]
    print(f"  {aa['time']} {aa['severity']} {aa['worker_id']} risk={aa['risk_score']} {aa['root_cause']}")
print(f"resolved: {len(resolved)}")
if snaps:
    s = snaps[-1]
    w2 = [w for w in s["workers"] if w["id"] == "W-002"][0]
    print(f"last snapshot: stage={s['scenario']['stage']} W-002 risk={w2['risk_score']} dist={w2['distance']}")
print("WS TEST DONE")
