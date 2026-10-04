"""
SafeSight AI — Worker Tracking
==============================
Multi-worker tracking using a simplified ByteTrack-inspired algorithm.
Tracks workers across frames using IoU matching and Kalman filtering concepts.

For production, consider integrating:
- ByteTrack (YOLOX)
- BoT-SORT
- DeepSORT

This implementation provides a lightweight, dependency-free tracker
compatible with the existing detection pipeline.
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import time
import uuid


@dataclass
class TrackedWorker:
    """A tracked worker with stable ID across frames."""
    tracking_id: int
    worker_id: str  # Original worker ID from detection (e.g., "W-002")
    bbox: List[float]  # [x1, y1, x2, y2] in normalized coords
    confidence: float
    age: int = 0  # frames since first detection
    hits: int = 0  # total matched detections
    time_since_update: int = 0  # frames since last match
    state: str = "Tentative"  # Tentative, Confirmed, Deleted
    last_seen: float = field(default_factory=time.time)

    # Kalman filter state (simplified: position + velocity)
    kf_state: Optional[np.ndarray] = None  # [x, y, vx, vy]
    kf_covariance: Optional[np.ndarray] = None

    # Associated detection data
    ppe: Dict[str, bool] = field(default_factory=dict)
    posture: str = "Normal"
    facing_vector: Optional[List[float]] = None
    zone: Optional[str] = None
    distance: Optional[float] = None
    risk_score: float = 0.0
    severity: str = "SAFE"


class KalmanFilter1D:
    """Simple 1D Kalman filter for position tracking."""

    def __init__(self, dt: float = 1.0/30.0, process_noise: float = 0.1, measurement_noise: float = 0.5):
        self.dt = dt
        # State: [position, velocity]
        self.x = np.zeros(2)
        self.P = np.eye(2) * 10.0  # initial covariance
        self.F = np.array([[1, dt], [0, 1]])  # state transition
        self.H = np.array([[1, 0]])  # measurement matrix
        self.Q = np.eye(2) * process_noise  # process noise
        self.R = np.array([[measurement_noise]])  # measurement noise

    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x[0]

    def update(self, z: float):
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T / S[0, 0]
        self.x = self.x + K * y
        self.P = (np.eye(2) - K @ self.H) @ self.P
        return self.x[0]

    def get_state(self) -> Tuple[float, float]:
        return float(self.x[0]), float(self.x[1])


class KalmanFilter2D:
    """2D Kalman filter for x,y tracking."""

    def __init__(self, dt: float = 1.0/30.0):
        self.kf_x = KalmanFilter1D(dt)
        self.kf_y = KalmanFilter1D(dt)

    def predict(self) -> Tuple[float, float]:
        return self.kf_x.predict(), self.kf_y.predict()

    def update(self, x: float, y: float):
        self.kf_x.update(x)
        self.kf_y.update(y)

    def get_state(self) -> Tuple[float, float]:
        return self.kf_x.get_state()[0], self.kf_y.get_state()[0]


def iou(box1: List[float], box2: List[float]) -> float:
    """Calculate IoU between two boxes in normalized coordinates [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter

    return inter / union if union > 0 else 0.0


def center_distance(box1: List[float], box2: List[float]) -> float:
    """Euclidean distance between box centers."""
    c1 = [(box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2]
    c2 = [(box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2]
    return np.hypot(c1[0] - c2[0], c1[1] - c2[1])


class WorkerTracker:
    """
    Multi-worker tracker using IoU-based association with Kalman filtering.
    Inspired by ByteTrack but simplified for workplace safety use case.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_age: int = 30,
        min_hits: int = 3,
        max_distance: float = 0.15,  # max normalized center distance for match
    ):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits
        self.max_distance = max_distance

        self.tracks: Dict[int, TrackedWorker] = {}
        self.next_id = 1
        self.frame_count = 0

    def _bbox_from_worker(self, worker: Dict[str, Any]) -> Optional[List[float]]:
        """Extract bounding box from worker detection."""
        if "box" in worker:
            return worker["box"]
        # If no box, create from x,y (normalized center)
        x = worker.get("x", 0.5)
        y = worker.get("y", 0.5)
        # Assume approximate person size
        w, h = 0.08, 0.18
        return [x - w/2, y - h/2, x + w/2, y + h/2]

    def _create_track(self, worker: Dict[str, Any], detection_idx: int) -> TrackedWorker:
        """Create a new track from a detection."""
        bbox = self._bbox_from_worker(worker)
        if bbox is None:
            bbox = [0.5, 0.5, 0.58, 0.68]

        track_id = self.next_id
        self.next_id += 1

        # Initialize Kalman filter with detection position
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        kf = KalmanFilter2D()
        kf.kf_x.x[0] = cx
        kf.kf_y.x[0] = cy

        track = TrackedWorker(
            tracking_id=track_id,
            worker_id=worker.get("id", f"UNK-{track_id}"),
            bbox=bbox,
            confidence=worker.get("confidence", 0.5),
            kf_state=np.array([cx, cy, 0.0, 0.0]),
        )
        track.kf_x = kf.kf_x
        track.kf_y = kf.kf_y

        # Copy detection attributes
        track.ppe = dict(worker.get("ppe", {}))
        track.posture = worker.get("posture", "Normal")
        track.facing_vector = worker.get("facing_vector")
        track.zone = worker.get("zone")
        track.distance = worker.get("distance")
        track.risk_score = worker.get("risk_score", 0.0)
        track.severity = worker.get("severity", "SAFE")

        return track

    def _predict_tracks(self):
        """Predict next position for all tracks."""
        for track in self.tracks.values():
            if track.kf_state is not None:
                # Simple prediction without full Kalman for now
                cx, cy = (track.bbox[0] + track.bbox[2]) / 2, (track.bbox[1] + track.bbox[3]) / 2
                # Could use velocity from previous frames
                pass

    def _associate_detections_to_tracks(
        self,
        detections: List[Dict[str, Any]],
        tracks: List[TrackedWorker],
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Associate detections to tracks using IoU + distance.
        Returns: matches, unmatched_detections, unmatched_tracks
        """
        if not detections or not tracks:
            return [], list(range(len(detections))), list(range(len(tracks)))

        # Build cost matrix (1 - IoU)
        cost_matrix = np.zeros((len(tracks), len(detections)))
        for t_idx, track in enumerate(tracks):
            for d_idx, det in enumerate(detections):
                det_bbox = self._bbox_from_worker(det)
                if det_bbox:
                    iou_val = iou(track.bbox, det_bbox)
                    dist = center_distance(track.bbox, det_bbox)
                    # Combined cost: IoU + distance penalty
                    cost_matrix[t_idx, d_idx] = 1.0 - iou_val + dist * 2.0
                else:
                    cost_matrix[t_idx, d_idx] = 1.0

        # Greedy matching (simplified Hungarian)
        matches = []
        used_detections = set()
        used_tracks = set()

        # Sort by cost
        flat_indices = np.argsort(cost_matrix.flatten())
        for idx in flat_indices:
            t_idx = idx // len(detections)
            d_idx = idx % len(detections)

            if t_idx in used_tracks or d_idx in used_detections:
                continue

            cost = cost_matrix[t_idx, d_idx]
            det_bbox = self._bbox_from_worker(detections[d_idx])
            if det_bbox:
                iou_val = iou(tracks[t_idx].bbox, det_bbox)
                dist = center_distance(tracks[t_idx].bbox, det_bbox)

                if iou_val >= self.iou_threshold or dist <= self.max_distance:
                    matches.append((t_idx, d_idx))
                    used_tracks.add(t_idx)
                    used_detections.add(d_idx)

        unmatched_detections = [i for i in range(len(detections)) if i not in used_detections]
        unmatched_tracks = [i for i in range(len(tracks)) if i not in used_tracks]

        return matches, unmatched_detections, unmatched_tracks

    def update(self, detections: List[Dict[str, Any]]) -> List[TrackedWorker]:
        """
        Update tracker with new frame detections.
        Returns list of confirmed tracks.
        """
        self.frame_count += 1
        active_tracks = list(self.tracks.values())

        # Associate
        matches, unmatched_dets, unmatched_trks = self._associate_detections_to_tracks(
            detections, active_tracks
        )

        # Update matched tracks
        for t_idx, d_idx in matches:
            track = active_tracks[t_idx]
            det = detections[d_idx]

            # Update track with detection
            new_bbox = self._bbox_from_worker(det)
            if new_bbox:
                track.bbox = new_bbox
            track.confidence = det.get("confidence", track.confidence)
            track.hits += 1
            track.time_since_update = 0
            track.last_seen = time.time()

            # Update attributes
            if "ppe" in det:
                track.ppe = dict(det["ppe"])
            if "posture" in det:
                track.posture = det["posture"]
            if "facing_vector" in det:
                track.facing_vector = det["facing_vector"]
            if "zone" in det:
                track.zone = det["zone"]
            if "distance" in det:
                track.distance = det["distance"]
            if "risk_score" in det:
                track.risk_score = det["risk_score"]
            if "severity" in det:
                track.severity = det["severity"]

            # Promote to confirmed
            if track.hits >= self.min_hits:
                track.state = "Confirmed"

        # Create new tracks for unmatched detections
        for d_idx in unmatched_dets:
            new_track = self._create_track(detections[d_idx], d_idx)
            self.tracks[new_track.tracking_id] = new_track

        # Age unmatched tracks
        for t_idx in unmatched_trks:
            track = active_tracks[t_idx]
            track.time_since_update += 1
            track.age += 1

            # Predict position (simple: keep last position)
            # In full implementation, would use Kalman prediction

        # Remove dead tracks
        dead_ids = []
        for tid, track in self.tracks.items():
            if track.time_since_update > self.max_age:
                track.state = "Deleted"
                dead_ids.append(tid)

        for tid in dead_ids:
            del self.tracks[tid]

        # Return confirmed tracks
        confirmed = [t for t in self.tracks.values() if t.state == "Confirmed"]
        return confirmed

    def get_track_by_worker_id(self, worker_id: str) -> Optional[TrackedWorker]:
        """Find track by original worker ID."""
        for track in self.tracks.values():
            if track.worker_id == worker_id:
                return track
        return None

    def get_all_tracks(self) -> List[TrackedWorker]:
        """Get all active tracks (including tentative)."""
        return list(self.tracks.values())

    def get_confirmed_tracks(self) -> List[TrackedWorker]:
        """Get only confirmed tracks."""
        return [t for t in self.tracks.values() if t.state == "Confirmed"]

    def reset(self):
        """Reset tracker."""
        self.tracks.clear()
        self.next_id = 1
        self.frame_count = 0


# Singleton tracker
_default_tracker = None


def get_worker_tracker() -> WorkerTracker:
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = WorkerTracker()
    return _default_tracker