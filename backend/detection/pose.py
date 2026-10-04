"""
SafeSight AI — YOLOPoseProvider (real pose/posture detection, optional)
=======================================================================
Runs a lightweight YOLO pose model (yolov8n-pose class) when `ultralytics`
and weights are available. Converts keypoints into a posture estimate using
a simple, explainable geometric heuristic:

    torso angle (shoulder-midpoint -> hip-midpoint vs vertical)
      < ~45 deg from vertical OR wide bounding box  -> lying / "Severe"
      45-70 deg                                     -> "Unsafe" (bent)
      otherwise                                     -> "Normal"

ANY failure returns None -> pipeline falls back to MockDetectionProvider.

How to enable (see README):
    pip install ultralytics
    place weights at  backend/models/yolov8n-pose.pt
"""

import os

from .base import DetectionProvider

try:  # optional heavy dependency — must never crash the app
    from ultralytics import YOLO  # type: ignore
    _ULTRALYTICS = True
except Exception:
    YOLO = None
    _ULTRALYTICS = False

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


class YOLOPoseProvider(DetectionProvider):
    name = "YOLOPoseProvider"
    real_vision = True

    # COCO pose keypoint indices
    L_SHOULDER, R_SHOULDER = 5, 6
    L_HIP, R_HIP = 11, 12

    def __init__(self):
        self.model = None
        self.error = None
        path = os.path.join(_MODELS_DIR, "yolov8n-pose.pt")
        if not _ULTRALYTICS:
            self.error = "ultralytics not installed"
            return
        if not os.path.exists(path):
            self.error = f"model weights not found: {path}"
            return
        try:
            self.model = YOLO(path)
        except Exception as exc:
            self.model = None
            self.error = f"model load failed: {exc}"

    def available(self) -> bool:
        return self.model is not None

    def _posture_from_keypoints(self, kpts, box) -> str:
        """Explainable geometric posture heuristic (no fancy math)."""
        try:
            ls, rs = kpts[self.L_SHOULDER], kpts[self.R_SHOULDER]
            lh, rh = kpts[self.L_HIP], kpts[self.R_HIP]
            if ls is None or rs is None or lh is None or rh is None:
                return "Normal"
            shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2)
            hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2)
            dx, dy = abs(shoulder_mid[0] - hip_mid[0]), abs(shoulder_mid[1] - hip_mid[1])
            box_w = box[2] - box[0]
            box_h = box[3] - box[1]
            if dy < 0.35 * box_h or (box_w / max(box_h, 1)) > 1.1:
                return "Severe"      # horizontal / lying down
            if dx > 0.45 * max(dy, 1):
                return "Unsafe"      # strongly bent torso
            return "Normal"
        except Exception:
            return "Normal"

    def detect(self, frame=None, state=None):
        """Run YOLO pose inference on a frame -> unified detections, or None."""
        if self.model is None or frame is None:
            return None
        try:
            results = self.model.predict(frame, verbose=False, conf=0.35)
            detections = []
            for res in results:
                for pi, box in enumerate(res.boxes):
                    xyxy = [float(v) for v in box.xyxy[0].tolist()]
                    kpts = res.keypoints[pi].data[0].tolist() if res.keypoints is not None else []
                    detections.append({
                        "id": None, "box": xyxy, "confidence": float(box.conf),
                        "ppe": None, "posture": self._posture_from_keypoints(kpts, xyxy),
                        "keypoints": kpts, "source": "yolo-pose",
                    })
            return detections
        except Exception:
            return None
