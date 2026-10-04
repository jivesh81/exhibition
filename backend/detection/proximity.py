"""
SafeSight AI — ProximityProvider (hazard-zone geometry & proximity analysis)
===========================================================================
OpenCV/homography-concept based worker-to-hazard proximity monitoring.

Monocular distance-estimation concept:
    The camera sees the ground plane in perspective. We approximate the
    homography with a simple depth model — a normalized y coordinate (0=far,
    1=near) maps linearly to a depth in meters, and lateral offsets are
    scaled by the row depth. This is exactly how a full homography maps
    image pixels to ground meters, but with an explainable linear model
    suitable for an edge prototype (a real homography needs calibration).

All geometry is pure Python math (works even if OpenCV is not installed);
OpenCV is only used for REAL person detection on camera frames (HOG detector,
built into opencv-python — no model downloads required).
"""

import math
import time

from .base import DetectionProvider

try:  # optional dependency — must never crash the app
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _CV2 = True
except Exception:
    cv2 = None
    _CV2 = False

# Ground-plane depth model (meters across the camera view)
FAR_DEPTH_M = 28.0     # depth at normalized y = 0 (top of frame)
NEAR_DEPTH_M = 4.0     # depth at normalized y = 1 (bottom of frame)
VIEW_WIDTH_M = 30.0    # lateral meters across the frame at mid-depth


class ProximityProvider(DetectionProvider):
    name = "ProximityProvider"
    real_vision = _CV2  # OpenCV present -> real person detection available

    def __init__(self):
        self._hog = None
        self._prev = {}      # worker_id -> {"distance": m, "t": timestamp}
        if _CV2:
            try:
                self._hog = cv2.HOGDescriptor()
                self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            except Exception:
                self._hog = None

    def available(self) -> bool:
        return True  # geometry core always works; real detection is a bonus

    # ------------------------------------------------------------------
    # Depth model (homography concept)
    # ------------------------------------------------------------------
    @staticmethod
    def _row_depth(y: float) -> float:
        """Depth in meters for a normalized y position (0=far, 1=near)."""
        return FAR_DEPTH_M + (NEAR_DEPTH_M - FAR_DEPTH_M) * max(0.0, min(1.0, y))

    @staticmethod
    def _lateral_scale(y: float) -> float:
        """Lateral meters-per-unit-x at this depth (perspective compression)."""
        return VIEW_WIDTH_M * (0.5 + (1.0 - max(0.0, min(1.0, y))) * 0.5)

    # ------------------------------------------------------------------
    # Zone geometry
    # ------------------------------------------------------------------
    @staticmethod
    def point_in_polygon(x: float, y: float, polygon) -> bool:
        """Ray-casting point-in-polygon test. polygon = [[x,y], ...] normalized."""
        if not polygon or len(polygon) < 3:
            return False
        inside = False
        n = len(polygon)
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i][0], polygon[i][1]
            xj, yj = polygon[j][0], polygon[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    @staticmethod
    def polygon_centroid(polygon):
        """Average vertex — used as the hazard source point."""
        if not polygon:
            return None
        return (sum(p[0] for p in polygon) / len(polygon),
                sum(p[1] for p in polygon) / len(polygon))

    # ------------------------------------------------------------------
    # Proximity computation (used by BOTH demo pipeline and real frames)
    # ------------------------------------------------------------------
    def compute_proximity(self, worker: dict, zones: list, dt: float = 1.0) -> dict:
        """
        For one worker: distance to nearest hazard source (meters, perspective
        corrected), closing speed (m/s), zone containment, facing angle.

        worker: {"x", "y", "facing_vector": [fx, fy] (optional)}
        zones : [{"id", "name", "severity", "polygon": [[x,y],...]}]
        """
        x, y = float(worker.get("x") or 0), float(worker.get("y") or 0)

        best_zone, best_dist, best_centroid = None, None, None
        for zone in zones:
            if not zone.get("active", 1):
                continue
            polygon = zone.get("polygon") or []
            centroid = self.polygon_centroid(polygon)
            if centroid is None:
                continue
            cx, cy = centroid
            # perspective-corrected ground meters
            lateral = (x - cx) * self._lateral_scale((y + cy) / 2)
            depth_diff = self._row_depth(y) - self._row_depth(cy)
            dist = math.hypot(lateral, depth_diff)
            if best_dist is None or dist < best_dist:
                best_zone, best_dist, best_centroid = zone, dist, centroid

        in_zone = False
        if best_zone is not None:
            in_zone = self.point_in_polygon(x, y, best_zone.get("polygon") or [])

        # closing speed: positive = approaching the hazard source
        closing_speed = 0.0
        key = worker.get("id")
        prev = self._prev.get(key)
        now = time.time()
        if best_dist is not None and prev is not None:
            elapsed = max(dt, now - prev["t"])
            closing_speed = round(max(0.0, (prev["distance"] - best_dist) / elapsed), 2)
        if best_dist is not None:
            self._prev[key] = {"distance": best_dist, "t": now}

        # facing angle: angle between worker facing vector and hazard direction
        facing_angle, facing_hazard, facing_away = 0.0, False, False
        fv = worker.get("facing_vector")
        if fv and best_centroid is not None:
            hx, hy = best_centroid[0] - x, best_centroid[1] - y
            mag_f, mag_h = math.hypot(fv[0], fv[1]), math.hypot(hx, hy)
            if mag_f > 1e-6 and mag_h > 1e-6:
                cos_a = (fv[0] * hx + fv[1] * hy) / (mag_f * mag_h)
                facing_angle = round(math.degrees(math.acos(max(-1.0, min(1.0, cos_a)))))
                facing_hazard = facing_angle <= 45
                facing_away = facing_angle >= 135

        return {
            "distance": round(best_dist, 1) if best_dist is not None else None,
            "closing_speed": closing_speed,
            "in_zone": in_zone,
            "zone": best_zone.get("name") if best_zone else None,
            "zone_id": best_zone.get("id") if best_zone else None,
            "zone_severity": best_zone.get("severity") if best_zone else None,
            "facing_angle": facing_angle,
            "facing_hazard": facing_hazard,
            "facing_away": facing_away,
        }

    # ------------------------------------------------------------------
    # REAL person detection on camera frames (OpenCV HOG — no downloads)
    # ------------------------------------------------------------------
    def detect_persons(self, frame) -> list:
        """OpenCV HOG person detection on a BGR frame -> unified detections."""
        if not _CV2 or self._hog is None or frame is None:
            return None
        try:
            frame_small = cv2.resize(frame, (640, 360))
            rects, weights = self._hog.detectMultiScale(
                frame_small, winStride=(8, 8), padding=(4, 4), scale=1.05)
            scale_x = frame.shape[1] / 640
            scale_y = frame.shape[0] / 360
            detections = []
            for (rx, ry, rw, rh), w in zip(rects, weights):
                detections.append({
                    "id": None,
                    "box": [rx * scale_x, ry * scale_y, (rx + rw) * scale_x, (ry + rh) * scale_y],
                    "confidence": float(min(1.0, w)),
                    "ppe": None, "posture": None, "source": "opencv-hog",
                })
            return detections
        except Exception:
            return None

    def detect(self, frame=None, state=None):
        """Interface implementation — real frames via HOG, else None."""
        return self.detect_persons(frame) if frame is not None else None
