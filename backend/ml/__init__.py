"""
SafeSight AI — ML Module
========================
Hybrid ML + Rule-based risk assessment with worker tracking and voice alerts.
"""

from .model import HybridRiskModel
from .features import FeatureExtractor, WORKER_FEATURES
from .fusion import RiskFusionEngine

# Import from sibling modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tracking import WorkerTracker, get_worker_tracker
from voice import VoiceAlertSystem, get_voice_system, AlertCooldown

__all__ = [
    "HybridRiskModel",
    "FeatureExtractor",
    "WORKER_FEATURES",
    "RiskFusionEngine",
    "WorkerTracker",
    "get_worker_tracker",
    "VoiceAlertSystem",
    "get_voice_system",
    "AlertCooldown",
]

# Version info
__version__ = "1.0.0"
MODEL_VERSION = "1.0"
FEATURE_VERSION = "1"
TRAINING_DATASET = "public-workplace-safety-v1"