"""
SafeSight AI — Voice Service
============================
Clean interface for voice alert generation, wrapping the existing VoiceAlertSystem.
"""
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from voice import VoiceAlertSystem, VoiceAlert, AlertPriority, get_voice_system
from app.core.config import settings
from app.core.logging import TTS_LOGGER


@dataclass
class VoiceGenerationResult:
    success: bool
    audio_file: Optional[str] = None
    audio_url: Optional[str] = None
    error: Optional[str] = None
    provider: Optional[str] = None
    duration_ms: float = 0


class VoiceService:
    """
    High-level voice service for generating alert audio.
    Decouples TTS generation from the main detection loop.
    """

    def __init__(self, voice_system: Optional[VoiceAlertSystem] = None):
        self.voice_system = voice_system or get_voice_system()
        self.audio_dir = Path(settings.VOICE_AUDIO_DIR)
        self.audio_dir.mkdir(exist_ok=True)

    def generate_alert_audio(
        self,
        worker_id: str,
        worker_name: str,
        severity: str,
        root_cause: str,
        zone: str,
        message: str,
    ) -> VoiceGenerationResult:
        """
        Generate audio for an alert.
        This is called asynchronously from the alert engine.
        """
        start_time = time.time()

        try:
            # Create voice alert through the existing system
            alert = self.voice_system.create_alert(
                worker_id=worker_id,
                worker_name=worker_name,
                severity=severity,
                root_cause=root_cause,
                zone=zone,
                message=message,
            )

            if alert and alert.audio_file:
                audio_url = f"/api/voice/audio/{alert.audio_file}"
                duration = (time.time() - start_time) * 1000
                TTS_LOGGER.info(
                    "Audio generated successfully",
                    alert_id=alert.alert_id,
                    worker_id=worker_id,
                    audio_file=alert.audio_file,
                    duration_ms=round(duration, 2),
                )
                return VoiceGenerationResult(
                    success=True,
                    audio_file=alert.audio_file,
                    audio_url=audio_url,
                    provider=self.voice_system.active_provider.name if self.voice_system.active_provider else None,
                    duration_ms=duration,
                )
            elif alert is None:
                # Suppressed by cooldown
                return VoiceGenerationResult(
                    success=False,
                    error="Suppressed by cooldown",
                )
            else:
                # Generation failed
                return VoiceGenerationResult(
                    success=False,
                    error="Audio generation failed",
                )

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            TTS_LOGGER.error(
                "Voice generation exception",
                worker_id=worker_id,
                error=str(e),
                duration_ms=round(duration, 2),
            )
            return VoiceGenerationResult(
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def generate_test_audio(self, text: str = "SafeSight voice alert system is operational.") -> VoiceGenerationResult:
        """Generate test audio for system verification."""
        start_time = time.time()
        try:
            filename = self.voice_system.speak_immediate(text)
            if filename:
                duration = (time.time() - start_time) * 1000
                return VoiceGenerationResult(
                    success=True,
                    audio_file=filename,
                    audio_url=f"/api/voice/audio/{filename}",
                    provider=self.voice_system.active_provider.name if self.voice_system.active_provider else None,
                    duration_ms=duration,
                )
            return VoiceGenerationResult(success=False, error="No audio generated")
        except Exception as e:
            return VoiceGenerationResult(success=False, error=str(e))

    def validate_audio_file(self, filename: str) -> Dict[str, Any]:
        """Validate that an audio file exists and is playable."""
        file_path = self.audio_dir / filename

        result = {
            "filename": filename,
            "exists": False,
            "size_bytes": 0,
            "valid_format": False,
            "mime_type": None,
            "readable": False,
        }

        if not file_path.exists():
            return result

        result["exists"] = True
        result["size_bytes"] = file_path.stat().st_size

        # Check format
        ext = file_path.suffix.lower()
        if ext == ".wav":
            result["valid_format"] = True
            result["mime_type"] = "audio/wav"
        elif ext == ".mp3":
            result["valid_format"] = True
            result["mime_type"] = "audio/mpeg"
        elif ext == ".ogg":
            result["valid_format"] = True
            result["mime_type"] = "audio/ogg"

        # Check readability
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
            result["readable"] = True
        except Exception:
            pass

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get voice system status."""
        status = self.voice_system.get_status()
        status["audio_dir"] = str(self.audio_dir)
        status["audio_files_count"] = len(list(self.audio_dir.glob("*.wav"))) + len(list(self.audio_dir.glob("*.mp3")))
        return status


# Singleton instance
_default_service = None


def get_voice_service() -> VoiceService:
    global _default_service
    if _default_service is None:
        _default_service = VoiceService()
    return _default_service