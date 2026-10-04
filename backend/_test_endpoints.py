"""Quick analytics-endpoint test (no server needed)."""
import main

try:
    a = main.analytics()
    print("analytics OK")
    print("  over_time:", a["incidents_over_time"])
    print("  by_severity:", a["incidents_by_severity"])
    print("  by_root_cause:", [(r["cause"], r["pct"]) for r in a["incidents_by_root_cause"]])
    print("  ppe_compliance:", a["ppe_compliance"], "| events:", a["ppe_events_total"])
    print("  zone_entries:", a["zone_entries"])
    print("  near_misses:", a["near_misses"], "| today:", a["near_misses_today"])
    print("  avg_risk:", a["avg_risk_score"])
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    s = main.system_status()
    print("system_status OK:", s["ppe_model"], "|", s["pose_model"], "| ai_mode:", s["ai_mode"])
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    d = main.dashboard()
    print("dashboard OK:", d)
except Exception as e:
    import traceback
    traceback.print_exc()
