"""
SafeSight AI — DetectionProvider abstract base
==============================================
All detection providers implement this interface, so the monitoring
pipeline (and the frontend) never depends on a concrete implementation.
"""


class DetectionProvider:
    """Base class for every detection provider."""

    name = "DetectionProvider"
    #: True when the provider can produce REAL detections on this machine
    real_vision = False

    def available(self) -> bool:
        """Return False if required models/libraries are missing — the
        pipeline then falls back to MockDetectionProvider automatically."""
        return True

    def detect(self, frame=None, state=None):
        """
        Produce detections.

        frame : raw image (numpy array / bytes) for real-vision providers
        state : dict — world/scenario state for mock providers

        Returns a list of detection dicts with a UNIFIED shape:
            {id, ppe:{helmet,vest,gloves}, posture, ...}
        or None when the provider cannot run (caller falls back).
        """
        raise NotImplementedError
