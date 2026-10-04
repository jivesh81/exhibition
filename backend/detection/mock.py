"""
SafeSight AI — MockDetectionProvider
====================================
Scripted/demo detections. ALWAYS available — guarantees the whole platform
stays fully functional when real AI models cannot be installed or run.

In demo mode the DemoEngine owns the world state (positions, PPE, posture);
this provider simply formats that state into the unified detection shape.
"""

from .base import DetectionProvider


class MockDetectionProvider(DetectionProvider):
    name = "MockDetectionProvider"
    real_vision = False

    def available(self) -> bool:
        return True  # always available — it is the guaranteed fallback

    def detect(self, frame=None, state=None):
        """
        Convert world state into unified worker detections.

        state = {
            "workers": [
                {"id": "W-002", "name": ..., "x": 0.71, "y": 0.34,
                 "ppe": {"helmet": False, "vest": True, "gloves": True},
                 "posture": "Unsafe", "facing_vector": [0.4, 0.9], ...}
            ]
        }
        """
        if not state or "workers" not in state:
            return None
        detections = []
        for w in state["workers"]:
            detections.append({
                "id": w.get("id"),
                "name": w.get("name"),
                "role": w.get("role"),
                "x": w.get("x"),
                "y": w.get("y"),
                "ppe": dict(w.get("ppe") or {"helmet": True, "vest": True, "gloves": True}),
                "posture": w.get("posture", "Normal"),
                "facing_vector": w.get("facing_vector"),
                "source": "mock",
            })
        return detections
