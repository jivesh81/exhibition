"""
SafeSight AI — Shared Global Instances
======================================
Single source of truth for all global component instances.
"""
from detection import get_providers
from demo_engine import DemoEngine, SCENARIOS
from ml.model import get_risk_model
from ml.fusion import get_fusion_engine
from ml.features import get_feature_extractor
from tracking import get_worker_tracker
from voice import get_voice_system
from voice import VoiceAlertSystem
from app.alerts.engine import get_alert_engine
from app.events.engine import get_safety_event_engine
from app.services.voice_service import get_voice_service
from app.websocket.manager import get_websocket_manager

# Initialize all providers and components
PROVIDERS = get_providers()
RISK_MODEL = get_risk_model()
FUSION_ENGINE = get_fusion_engine()
FEATURE_EXTRACTOR = get_feature_extractor()
WORKER_TRACKER = get_worker_tracker()
VOICE_SYSTEM = get_voice_system()
VOICE_SERVICE = get_voice_service()
WS_MANAGER = get_websocket_manager()
ALERT_ENGINE = get_alert_engine()
EVENT_ENGINE = get_safety_event_engine()
DEMO = DemoEngine(PROVIDERS)

# Export scenario info
__all__ = [
    "PROVIDERS", "RISK_MODEL", "FUSION_ENGINE", "FEATURE_EXTRACTOR",
    "WORKER_TRACKER", "VOICE_SYSTEM", "VOICE_SERVICE", "WS_MANAGER",
    "ALERT_ENGINE", "EVENT_ENGINE", "DEMO", "SCENARIOS",
]