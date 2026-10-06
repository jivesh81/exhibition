"""
SafeSight AI — Core Configuration
=================================
Centralized configuration management using Pydantic Settings.
"""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SafeSight AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    GROUP: str = "173"

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False

    # Database
    DATABASE_PATH: str = str(Path(__file__).parent.parent.parent / "safesight.db")
    DATABASE_URL: str = f"sqlite:///{DATABASE_PATH}"

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # Voice/TTS
    VOICE_AUDIO_DIR: str = str(Path(__file__).parent.parent.parent / "voice_audio")
    MAX_AUDIO_FILES: int = 100
    TTS_PROVIDER_PRIORITY: list[str] = ["pyttsx3", "piper", "edge-tts"]
    VOICE_ENABLED: bool = True

    # Demo
    DEMO_TICK_SECONDS: float = 1.2
    DEFAULT_SCENARIO: str = "crane_approach"

    # Tracking
    TRACK_IOU_THRESHOLD: float = 0.3
    TRACK_MAX_AGE: int = 30
    TRACK_MIN_HITS: int = 3
    TRACK_MAX_DISTANCE: float = 0.15

    # Risk Engine
    RULE_WEIGHT: float = 0.5
    ML_WEIGHT: float = 0.3
    TEMPORAL_WEIGHT: float = 0.2

    # Alert Cooldown
    ALERT_BASE_COOLDOWN: float = 8.0
    ALERT_CRITICAL_COOLDOWN: float = 3.0
    ALERT_ESCALATION_OVERRIDE: bool = True

    # Model Paths
    MODEL_PATH: str = str(Path(__file__).parent.parent.parent / "artifacts" / "hybrid_risk_model.pkl")
    SCALER_PATH: str = str(Path(__file__).parent.parent.parent / "artifacts" / "feature_scaler.pkl")
    METADATA_PATH: str = str(Path(__file__).parent.parent.parent / "artifacts" / "model_metadata.json")

    # Detection
    PPE_MODEL_PATH: Optional[str] = None
    POSE_MODEL_PATH: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()