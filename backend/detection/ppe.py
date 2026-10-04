"""
SafeSight AI — YOLOPPEProvider (real PPE detection, optional)
=============================================================
Runs a lightweight YOLO model for PPE detection when `ultralytics` and model
weights are available on this machine. ANY failure (no torch, no weights,
inference error) returns None -> pipeline falls back to MockDetectionProvider.

How to enable (see README):
    pip install ultralytics
    place weights at  backend/models/ppe_yolo.pt
    set environment   SAFE_SIGHT_PPE_MODEL=ppe_yolo.pt   (optional)
Model classes expected (typical open PPE datasets):
    helmet / hardhat / head  |  vest / safety-vest  |  gloves / gloves-on
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

# dataset class-name substrings that map to PPE items
_HELMET_TAGS = ("helmet", "hardhat", "hard hat", "head")
_VEST_TAGS = ("vest",)
_GLOVE_TAGS = ("glove",)


class YOLOPPEProvider(DetectionProvider):
    name = "YOLOPPEProvider"
    real_vision = True

    def __init__(self):
        self.model = None
        self.error = None
        self._load()

    def _model_path(self) -> str:
        env_model = os.environ.get("SAFE_SIGHT_PPE_MODEL")
        return os.path.join(_MODELS_DIR, env_model) if env_model else os.path.join(_MODELS_DIR, "ppe_yolo.pt")

    def _load(self):
        if not _ULTRALYTICS:
            self.error = "ultralytics not installed"
            return
        path = self._model_path()
        if not os.path.exists(path):
            self.error = f"model weights not found: {path}"
            return
        try:
            self.model = YOLO(path)
        except Exception as exc:  # any model load failure -> graceful fallback
            self.model = None
            self.error = f"model load failed: {exc}"

    def available(self) -> bool:
        return self.model is not None

    def detect(self, frame=None, state=None):
        """Run YOLO PPE inference on a frame -> unified detections, or None."""
        if self.model is None or frame is None:
            return None
        try:
            results = self.model.predict(frame, verbose=False, conf=0.35)
            people, helmets, vests, gloves = [], [], [], []
            for res in results:
                for box in res.boxes:
                    cls_name = (res.names.get(int(box.cls)) or "").lower()
                    conf = float(box.conf)
                    xyxy = [float(v) for v in box.xyxy[0].tolist()]
                    if any(t in cls_name for t in _HELMET_TAGS):
                        (helmets if "no" not in cls_name else people).append((xyxy, conf))
                    elif any(t in cls_name for t in _VEST_TAGS):
                        vests.append((xyxy, conf))
                    elif any(t in cls_name for t in _GLOVE_TAGS):
                        gloves.append((xyxy, conf))
                    elif "person" in cls_name:
                        people.append((xyxy, conf))
            # associate helmet/vest boxes with the nearest person box (IoU-free center match)
            def _center(b):
                return ((b[0][0] + b[0][2]) / 2, (b[0][1] + b[0][3]) / 2)
            detections = []
            for person, conf in people:
                px, py = _center((person, conf))
                def _has(boxes):
                    return any(abs(_center(b)[0] - px) < 60 and b[0][1] < person[3] for b in boxes)
                detections.append({
                    "id": None, "box": person, "confidence": conf,
                    "ppe": {"helmet": _has(helmets), "vest": _has(vests), "gloves": _has(gloves)},
                    "posture": None, "source": "yolo-ppe",
                })
            return detections
        except Exception:
            return None  # inference failure -> caller falls back to mock
