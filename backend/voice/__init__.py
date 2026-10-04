"""
SafeSight AI — Voice Alert System
=================================
Text-to-speech system for autonomous worker-specific safety alerts.
Supports offline TTS (Piper, pyttsx3) with priority queue and cooldown.
"""

import threading
import queue
import time
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum
from pathlib import Path

import database as db


class AlertPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    WARNING = 2
    INFO = 3

    def __lt__(self, other):
        return self.value < other.value


@dataclass
class VoiceAlert:
    """A voice alert to be spoken."""
    alert_id: str
    worker_id: str
    worker_name: str
    severity: str  # CRITICAL, HIGH, WARNING, INFO
    priority: AlertPriority
    message: str
    root_cause: str
    zone: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    metadata: Dict = field(default_factory=dict)


class AlertCooldown:
    """
    Manages cooldown periods to prevent alert spam.
    Per-worker, per-severity cooldown with escalation override.
    """

    def __init__(
        self,
        base_cooldown: float = 8.0,  # seconds
        critical_cooldown: float = 3.0,
        escalation_override: bool = True,
    ):
        self.base_cooldown = base_cooldown
        self.critical_cooldown = critical_cooldown
        self.escalation_override = escalation_override

        # worker_id -> {severity: last_alert_time}
        self.last_alert: Dict[str, Dict[str, float]] = {}
        # worker_id -> last_severity
        self.last_severity: Dict[str, str] = {}
        self._lock = threading.RLock()

    SEVERITY_RANK = {"SAFE": 0, "INFO": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}

    def should_alert(self, worker_id: str, severity: str) -> bool:
        """Check if an alert should be sent for this worker/severity."""
        with self._lock:
            now = time.time()

            # Initialize worker if new
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
                self.last_severity[worker_id] = "SAFE"

            last_sev = self.last_severity[worker_id]
            current_rank = self.SEVERITY_RANK.get(severity, 0)
            last_rank = self.SEVERITY_RANK.get(last_sev, 0)

            # Always allow if severity increased (escalation)
            if self.escalation_override and current_rank > last_rank:
                return True

            # Check cooldown
            last_time = self.last_alert[worker_id].get(severity, 0)
            cooldown = self.critical_cooldown if severity == "CRITICAL" else self.base_cooldown

            if now - last_time >= cooldown:
                return True

            return False

    def record_alert(self, worker_id: str, severity: str):
        """Record that an alert was sent."""
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
            self.last_alert[worker_id][severity] = now
            self.last_severity[worker_id] = severity

    def record_clear(self, worker_id: str):
        """Record that worker is now clear (for recovery announcement)."""
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
            # Use a special key for clear announcements
            self.last_alert[worker_id]["CLEAR"] = now
            self.last_severity[worker_id] = "SAFE"

    def should_announce_clear(self, worker_id: str) -> bool:
        """Check if we should announce 'area clear'."""
        with self._lock:
            if worker_id not in self.last_alert:
                return False
            last_clear = self.last_alert[worker_id].get("CLEAR", 0)
            last_alert = max(self.last_alert[worker_id].values()) if self.last_alert[worker_id] else 0
            # Allow clear announcement if last alert was > 5s ago and no recent clear
            return (time.time() - last_alert > 5.0) and (time.time() - last_clear > 10.0)

    def get_status(self, worker_id: str) -> Dict:
        """Get cooldown status for a worker."""
        with self._lock:
            if worker_id not in self.last_alert:
                return {"cooldown_active": False, "last_severity": "SAFE"}
            now = time.time()
            status = {"cooldown_active": False, "last_severity": self.last_severity.get(worker_id, "SAFE")}
            for sev, t in self.last_alert[worker_id].items():
                cooldown = self.critical_cooldown if sev == "CRITICAL" else self.base_cooldown
                if now - t < cooldown:
                    status["cooldown_active"] = True
                    status[f"{sev.lower()}_remaining"] = round(cooldown - (now - t), 1)
            return status


class TTSProvider:
    """Base class for TTS providers."""

    def __init__(self, name: str):
        self.name = name
        self.available = False
        self.error = None

    def speak(self, text: str, blocking: bool = False) -> bool:
        """Speak text. Returns True if successful."""
        raise NotImplementedError

    def is_available(self) -> bool:
        return self.available


class Pyttsx3Provider(TTSProvider):
    """Offline TTS using pyttsx3 (system voices)."""

    def __init__(self):
        super().__init__("pyttsx3")
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            # Configure voice
            voices = self.engine.getProperty('voices')
            # Prefer English voices
            for v in voices:
                if 'english' in v.name.lower() or 'en' in v.id.lower():
                    self.engine.setProperty('voice', v.id)
                    break
            self.engine.setProperty('rate', 170)  # words per minute
            self.engine.setProperty('volume', 0.9)
            self.available = True
        except Exception as e:
            self.error = str(e)
            self.available = False

    def speak(self, text: str, blocking: bool = False) -> bool:
        if not self.available or self.engine is None:
            return False
        try:
            self.engine.say(text)
            if blocking:
                self.engine.runAndWait()
            else:
                self.engine.runAndWait()  # pyttsx3 is synchronous anyway
            return True
        except Exception as e:
            self.error = str(e)
            return False


class PiperProvider(TTSProvider):
    """Offline TTS using Piper (high quality, fast)."""

    def __init__(self, model_path: Optional[str] = None):
        super().__init__("piper")
        self.model_path = model_path or self._find_model()
        self._check_available()

    def _find_model(self) -> Optional[str]:
        # Look for Piper model in common locations
        search_paths = [
            Path.home() / ".local" / "share" / "piper" / "en_US-lessac-medium.onnx",
            Path("/usr/share/piper/voices/en_US-lessac-medium.onnx"),
            Path("models/piper/en_US-lessac-medium.onnx"),
        ]
        for p in search_paths:
            if p.exists():
                return str(p)
        return None

    def _check_available(self):
        if self.model_path and Path(self.model_path).exists():
            # Check if piper binary exists
            try:
                result = subprocess.run(["piper", "--help"], capture_output=True, timeout=2)
                self.available = result.returncode == 0
                if not self.available:
                    self.error = "piper binary not found"
            except Exception:
                self.error = "piper not installed"
        else:
            self.error = "Piper model not found"

    def speak(self, text: str, blocking: bool = False) -> bool:
        if not self.available:
            return False
        try:
            # Piper reads from stdin, writes WAV to stdout
            proc = subprocess.Popen(
                ["piper", "--model", self.model_path, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            audio_data, _ = proc.communicate(input=text.encode(), timeout=10)

            if proc.returncode == 0 and audio_data:
                # Play audio using system player
                if os.name == 'nt':  # Windows
                    # Save to temp file and play
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        # Add WAV header for raw PCM (16-bit, 22050 Hz, mono)
                        import wave
                        with wave.open(f.name, 'wb') as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(22050)
                            wav.writeframes(audio_data)
                        subprocess.run(["powershell", "-c", f"(New-Object Media.SoundPlayer '{f.name}').PlaySync()"], timeout=10)
                        os.unlink(f.name)
                else:  # Linux/Mac
                    import wave
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        with wave.open(f.name, 'wb') as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(22050)
                            wav.writeframes(audio_data)
                        subprocess.run(["aplay", f.name], timeout=10)
                        os.unlink(f.name)
                return True
        except Exception as e:
            self.error = str(e)
        return False


class EdgeTTSProvider(TTSProvider):
    """Online TTS using Microsoft Edge TTS (requires internet)."""

    def __init__(self, voice: str = "en-US-GuyNeural"):
        super().__init__("edge-tts")
        self.voice = voice
        self._check_available()

    def _check_available(self):
        try:
            import edge_tts
            self.available = True
        except ImportError:
            self.error = "edge-tts not installed"
            self.available = False

    def speak(self, text: str, blocking: bool = False) -> bool:
        if not self.available:
            return False
        try:
            import edge_tts
            import asyncio

            async def _speak():
                communicate = edge_tts.Communicate(text, self.voice)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    await communicate.save(f.name)
                    # Play the file
                    if os.name == 'nt':
                        subprocess.run(["powershell", "-c", f"(New-Object Media.SoundPlayer '{f.name}').PlaySync()"], timeout=15)
                    else:
                        subprocess.run(["mpg123", "-q", f.name], timeout=15)
                    os.unlink(f.name)

            if blocking:
                asyncio.run(_speak())
            else:
                # Run in thread
                threading.Thread(target=lambda: asyncio.run(_speak()), daemon=True).start()
            return True
        except Exception as e:
            self.error = str(e)
            return False


class VoiceAlertSystem:
    """
    Main voice alert system with priority queue, cooldown, and multiple TTS providers.
    """

    def __init__(
        self,
        cooldown: Optional[AlertCooldown] = None,
        tts_providers: Optional[List[TTSProvider]] = None,
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.cooldown = cooldown or AlertCooldown()
        self.alert_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.tts_providers = tts_providers or self._init_default_providers()
        self.active_provider = self._select_best_provider()

        self._worker_thread = None
        self._stop_event = threading.Event()
        self._paused = False
        self._lock = threading.RLock()

        # Callbacks
        self.on_alert_spoken: Optional[Callable[[VoiceAlert], None]] = None
        self.on_alert_failed: Optional[Callable[[VoiceAlert, str], None]] = None
        self.on_queue_update: Optional[Callable[[int], None]] = None

        # Stats
        self.stats = {
            "total_alerts": 0,
            "spoken": 0,
            "failed": 0,
            "suppressed": 0,
            "queue_size": 0,
        }

        self.start()

    def _init_default_providers(self) -> List[TTSProvider]:
        """Initialize TTS providers in order of preference (offline first)."""
        providers = [
            Pyttsx3Provider(),  # Offline, always available if installed
            PiperProvider(),    # Offline, high quality
            EdgeTTSProvider(),  # Online, fallback
        ]
        return [p for p in providers if p.is_available()]

    def _select_best_provider(self) -> Optional[TTSProvider]:
        for p in self.tts_providers:
            if p.is_available():
                return p
        return None

    def start(self):
        """Start the worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="VoiceAlertWorker")
        self._worker_thread.start()

    def stop(self):
        """Stop the worker thread."""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2)

    def pause(self):
        """Pause alert processing."""
        self._paused = True

    def resume(self):
        """Resume alert processing."""
        self._paused = False

    def enqueue_alert(self, alert: VoiceAlert) -> bool:
        """Add alert to priority queue."""
        if not self.enabled:
            return False
        # Priority queue uses (priority_value, timestamp, alert) for ordering
        priority_val = alert.priority.value
        self.alert_queue.put((priority_val, alert.timestamp, alert))
        self.stats["total_alerts"] += 1
        self.stats["queue_size"] = self.alert_queue.qsize()
        if self.on_queue_update:
            self.on_queue_update(self.alert_queue.qsize())
        return True

    def create_alert(
        self,
        worker_id: str,
        worker_name: str,
        severity: str,
        root_cause: str,
        zone: str,
        message: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[VoiceAlert]:
        """Create and enqueue an alert if cooldown allows."""
        # Map severity to priority
        priority_map = {
            "CRITICAL": AlertPriority.CRITICAL,
            "HIGH": AlertPriority.HIGH,
            "WARNING": AlertPriority.WARNING,
            "INFO": AlertPriority.INFO,
            "SAFE": AlertPriority.INFO,
        }
        priority = priority_map.get(severity, AlertPriority.INFO)

        # Check cooldown
        if not self.cooldown.should_alert(worker_id, severity):
            self.stats["suppressed"] += 1
            return None

        alert = VoiceAlert(
            alert_id=f"{worker_id}-{int(time.time()*1000)}",
            worker_id=worker_id,
            worker_name=worker_name,
            severity=severity,
            priority=priority,
            message=message,
            root_cause=root_cause,
            zone=zone,
            metadata=metadata or {},
        )

        self.cooldown.record_alert(worker_id, severity)
        self.enqueue_alert(alert)
        return alert

    def create_clear_announcement(self, worker_id: str, worker_name: str, zone: str) -> Optional[VoiceAlert]:
        """Create a 'zone clear' announcement."""
        if not self.cooldown.should_announce_clear(worker_id):
            return None

        alert = VoiceAlert(
            alert_id=f"{worker_id}-clear-{int(time.time()*1000)}",
            worker_id=worker_id,
            worker_name=worker_name,
            severity="SAFE",
            priority=AlertPriority.INFO,
            message=f"{worker_name}, area is now clear.",
            root_cause="ZONE CLEAR",
            zone=zone,
        )
        self.cooldown.record_clear(worker_id)
        self.enqueue_alert(alert)
        return alert

    def _worker_loop(self):
        """Background thread that processes the alert queue."""
        while not self._stop_event.is_set():
            if self._paused:
                time.sleep(0.1)
                continue

            try:
                # Get next alert with timeout
                priority_val, timestamp, alert = self.alert_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self.stats["queue_size"] = self.alert_queue.qsize()
            if self.on_queue_update:
                self.on_queue_update(self.alert_queue.qsize())

            # Speak the alert
            success = self._speak_alert(alert)

            if success:
                self.stats["spoken"] += 1
                # Log to database
                try:
                    db.insert_voice_event(
                        alert.worker_id, alert.worker_name, alert.severity,
                        alert.message, alert.root_cause, alert.zone
                    )
                except Exception:
                    pass
                if self.on_alert_spoken:
                    self.on_alert_spoken(alert)
            else:
                self.stats["failed"] += 1
                alert.retry_count += 1
                if alert.retry_count < 3:
                    # Re-queue with same priority
                    self.alert_queue.put((priority_val, alert.timestamp, alert))
                elif self.on_alert_failed:
                    self.on_alert_failed(alert, "Max retries exceeded")

            self.alert_queue.task_done()

    def _speak_alert(self, alert: VoiceAlert) -> bool:
        """Speak alert using the active TTS provider."""
        if not self.active_provider:
            return False

        try:
            return self.active_provider.speak(alert.message, blocking=True)
        except Exception as e:
            self.active_provider.error = str(e)
            # Try fallback provider
            for provider in self.tts_providers:
                if provider != self.active_provider and provider.is_available():
                    self.active_provider = provider
                    return provider.speak(alert.message, blocking=True)
            return False

    def get_status(self) -> Dict:
        """Get system status."""
        return {
            "enabled": self.enabled,
            "active_provider": self.active_provider.name if self.active_provider else "NONE",
            "available_providers": [p.name for p in self.tts_providers if p.is_available()],
            "queue_size": self.alert_queue.qsize(),
            "paused": self._paused,
            "stats": self.stats.copy(),
        }

    def speak_immediate(self, text: str) -> bool:
        """Speak text immediately (bypass queue)."""
        if not self.enabled or not self.active_provider:
            return False
        return self.active_provider.speak(text, blocking=True)


# Singleton
_default_voice_system = None


def get_voice_system() -> VoiceAlertSystem:
    global _default_voice_system
    if _default_voice_system is None:
        _default_voice_system = VoiceAlertSystem()
    return _default_voice_system