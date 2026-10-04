"""
SafeSight AI — Detection Providers
==================================
Group 173 Prototype

Clean detection-provider architecture:

    DetectionProvider          (abstract base)
    ├── MockDetectionProvider  (scripted demo detections — always available)
    ├── YOLOPPEProvider        (real YOLO PPE — optional, graceful fallback)
    ├── YOLOPoseProvider       (real YOLO pose — optional, graceful fallback)
    └── ProximityProvider      (geometry / zone analysis — pure Python + OpenCV)

The frontend never depends on which provider is active: the backend reports
provider availability and the pipeline result always has the same shape.
"""

from .base import DetectionProvider
from .mock import MockDetectionProvider
from .ppe import YOLOPPEProvider
from .pose import YOLOPoseProvider
from .proximity import ProximityProvider


def get_providers() -> dict:
    """Instantiate all providers and report availability (used by /api/system-status)."""
    ppe = YOLOPPEProvider()
    pose = YOLOPoseProvider()
    mock = MockDetectionProvider()
    prox = ProximityProvider()
    return {
        "ppe": {"provider": ppe, "name": ppe.name, "available": ppe.available(),
                "mode": "YOLO" if ppe.available() else "MOCK"},
        "pose": {"provider": pose, "name": pose.name, "available": pose.available(),
                 "mode": "YOLO-POSE" if pose.available() else "MOCK"},
        "mock": {"provider": mock, "name": mock.name, "available": True, "mode": "MOCK"},
        "proximity": {"provider": prox, "name": prox.name, "available": prox.available(),
                      "mode": "OPENCV" if prox.available() else "GEOMETRY"},
    }
