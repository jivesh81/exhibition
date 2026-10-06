"""
SafeSight AI — Voice Alert System
=================================
Text-to-speech system for autonomous worker-specific safety alerts.
Generates audio files and serves them via HTTP for browser playback.
Supports offline TTS (Piper, pyttsx3) with priority queue and cooldown.
"""

import threading
import queue
import time
import json
import os
import subprocess
import tempfile
import uuid
import shutil
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
    audio_file: Optional[str] = None  # Path to generated audio file


class AlertCooldown:
    """
    Manages cooldown periods to prevent alert spam.
    Per-worker, per-severity cooldown with escalation override.
    """

    def __init__(
        self,
        base_cooldown: float = 8.0,
        critical_cooldown: float = 3.0,
        escalation_override: bool = True,
    ):
        self.base_cooldown = base_cooldown
        self.critical_cooldown = critical_cooldown
        self.escalation_override = escalation_override

        self.last_alert: Dict[str, Dict[str, float]] = {}
        self.last_severity: Dict[str, str] = {}
        self._lock = threading.RLock()

    SEVERITY_RANK = {"SAFE": 0, "INFO": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}

    def should_alert(self, worker_id: str, severity: str) -> bool:
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
                self.last_severity[worker_id] = "SAFE"

            last_sev = self.last_severity[worker_id]
            current_rank = self.SEVERITY_RANK.get(severity, 0)
            last_rank = self.SEVERITY_RANK.get(last_sev, 0)

            if self.escalation_override and current_rank > last_rank:
                return True

            last_time = self.last_alert[worker_id].get(severity, 0)
            cooldown = self.critical_cooldown if severity == "CRITICAL" else self.base_cooldown

            if now - last_time >= cooldown:
                return True
            return False

    def record_alert(self, worker_id: str, severity: str):
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
            self.last_alert[worker_id][severity] = now
            self.last_severity[worker_id] = severity

    def record_clear(self, worker_id: str):
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
            self.last_alert[worker_id]["CLEAR"] = now
            self.last_severity[worker_id] = "SAFE"

    def should_announce_clear(self, worker_id: str) -> bool:
        with self._lock:
            if worker_id not in self.last_alert:
                return False
            last_clear = self.last_alert[worker_id].get("CLEAR", 0)
            last_alert = max(self.last_alert[worker_id].values()) if self.last_alert[worker_id] else 0
            return (time.time() - last_alert > 5.0) and (time.time() - last_clear > 10.0)

    def get_status(self, worker_id: str) -> Dict:
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

    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio file. Returns True if successful."""
        raise NotImplementedError

    def is_available(self) -> bool:
        return self.available


class Pyttsx3Provider(TTSProvider):
    """Offline TTS using pyttsx3 (system voices). Generates WAV files."""

    def __init__(self):
        super().__init__("pyttsx3")
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty('voices')
            for v in voices:
                if 'english' in v.name.lower() or 'en' in v.id.lower():
                    self.engine.setProperty('voice', v.id)
                    break
            self.engine.setProperty('rate', 170)
            self.engine.setProperty('volume', 0.9)
            self.available = True
        except Exception as e:
            self.error = str(e)
            self.available = False

    def generate_audio(self, text: str, output_path: str) -> bool:
        if not self.available or self.engine is None:
            return False
        try:
            self.engine.save_to_file(text, output_path)
            self.engine.runAndWait()
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            self.error = str(e)
            return False


class PiperProvider(TTSProvider):
    """Offline TTS using Piper (high quality, fast). Generates WAV files."""

    def __init__(self, model_path: Optional[str] = None):
        super().__init__("piper")
        self.model_path = model_path or self._find_model()
        self._check_available()

    def _find_model(self) -> Optional[str]:
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
            try:
                result = subprocess.run(["piper", "--help"], capture_output=True, timeout=2)
                self.available = result.returncode == 0
                if not self.available:
                    self.error = "piper binary not found"
            except Exception:
                self.error = "piper not installed"
        else:
            self.error = "Piper model not found"

    def generate_audio(self, text: str, output_path: str) -> bool:
        if not self.available:
            return False
        try:
            proc = subprocess.Popen(
                ["piper", "--model", self.model_path, "--output_file", output_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate(input=text.encode(), timeout=15)

            if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                self.error = stderr.decode() if stderr else "Piper generation failed"
                return False
        except Exception as e:
            self.error = str(e)
            return False


class EdgeTTSProvider(TTSProvider):
    """Online TTS using Microsoft Edge TTS (requires internet). Generates MP3 files."""

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

    def generate_audio(self, text: str, output_path: str) -> bool:
        if not self.available:
            return False
        try:
            import edge_tts
            import asyncio

            async def _generate():
                communicate = edge_tts.Communicate(text, self.voice)
                await communicate.save(output_path)

            asyncio.run(_generate())
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            self.error = str(e)
            return False


# Audio storage directory
VOICE_AUDIO_DIR = Path(__file__).parent.parent / "voice_audio"
VOICE_AUDIO_DIR.mkdir(exist_ok=True)

# Maximum audio files to keep (cleanup old ones)
MAX_AUDIO_FILES = 100


def _cleanup_old_audio():
    """Remove old audio files if we exceed the limit."""
    try:
        files = sorted(VOICE_AUDIO_DIR.glob("*.wav")) + sorted(VOICE_AUDIO_DIR.glob("*.mp3"))
        if len(files) > MAX_AUDIO_FILES:
            for f in files[:-MAX_AUDIO_FILES]:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


class VoiceAlertSystem:
    """
    Main voice alert system with priority queue, cooldown, and multiple TTS providers.
    Generates audio files for browser playback instead of playing through server speakers.
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

        self.on_alert_spoken: Optional[Callable[[VoiceAlert], None]] = None
        self.on_alert_failed: Optional[Callable[[VoiceAlert, str], None]] = None
        self.on_queue_update: Optional[Callable[[int], None]] = None

        self.stats = {
            "total_alerts": 0,
            "spoken": 0,
            "failed": 0,
            "suppressed": 0,
            "queue_size": 0,
        }

        self.start()

    def _init_default_providers(self) -> List[TTSProvider]:
        providers = [
            Pyttsx3Provider(),
            PiperProvider(),
            EdgeTTSProvider(),
        ]
        return [p for p in providers if p.is_available()]

    def _select_best_provider(self) -> Optional[TTSProvider]:
        for p in self.tts_providers:
            if p.is_available():
                return p
        return None

    def start(self):
        print(f"[VOICE TRACE START] start() called, existing_thread={self._worker_thread}, alive={self._worker_thread.is_alive() if self._worker_thread else None}")
        if self._worker_thread and self._worker_thread.is_alive():
            print(f"[VOICE TRACE START] Thread already alive, returning early")
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="VoiceAlertWorker")
        self._worker_thread.start()
        print(f"[VOICE TRACE START] Thread started: {self._worker_thread}, alive={self._worker_thread.is_alive()}")

    def stop(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def enqueue_alert(self, alert: VoiceAlert) -> bool:
        if not self.enabled:
            return False
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
        priority_map = {
            "CRITICAL": AlertPriority.CRITICAL,
            "HIGH": AlertPriority.HIGH,
            "WARNING": AlertPriority.WARNING,
            "INFO": AlertPriority.INFO,
            "SAFE": AlertPriority.INFO,
        }
        priority = priority_map.get(severity, AlertPriority.INFO)

        print(f"[VOICE TRACE 2] create_alert called: worker={worker_id}, severity={severity}, message={message[:60]}")

        if not self.cooldown.should_alert(worker_id, severity):
            self.stats["suppressed"] += 1
            print(f"[VOICE TRACE 2] SUPPRESSED by cooldown: worker={worker_id}, severity={severity}")
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
        print(f"[VOICE TRACE 2] Alert enqueued: alert_id={alert.alert_id}, queue_size={self.alert_queue.qsize()}")
        return alert

    def create_clear_announcement(self, worker_id: str, worker_name: str, zone: str) -> Optional[VoiceAlert]:
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
        print(f"[VOICE TRACE 3] Worker loop STARTED, thread={threading.current_thread().name}")
        try:
            while not self._stop_event.is_set():
                if self._paused:
                    time.sleep(0.1)
                    continue

                try:
                    priority_val, timestamp, alert = self.alert_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                self.stats["queue_size"] = self.alert_queue.qsize()
                if self.on_queue_update:
                    self.on_queue_update(self.alert_queue.qsize())

                print(f"[VOICE TRACE 3] Worker loop processing alert: alert_id={alert.alert_id}, worker={alert.worker_id}, severity={alert.severity}, queue_remaining={self.alert_queue.qsize()}")

                # Generate audio file
                audio_file = self._generate_audio_file(alert)
                if audio_file:
                    alert.audio_file = audio_file
                    success = True
                else:
                    success = False

                if success:
                    self.stats["spoken"] += 1
                    try:
                        db.insert_voice_event(
                            alert.worker_id, alert.worker_name, alert.severity,
                            alert.message, alert.root_cause, alert.zone
                        )
                    except Exception:
                        pass
                    if self.on_alert_spoken:
                        print(f"[VOICE TRACE 4] on_alert_spoken callback firing: alert_id={alert.alert_id}, audio_file={alert.audio_file}")
                        self.on_alert_spoken(alert)
                else:
                    self.stats["failed"] += 1
                    alert.retry_count += 1
                    if alert.retry_count < 3:
                        self.alert_queue.put((priority_val, alert.timestamp, alert))
                        print(f"[VOICE TRACE 3] Retry scheduled: alert_id={alert.alert_id}, retry_count={alert.retry_count}")
                    elif self.on_alert_failed:
                        self.on_alert_failed(alert, "Max retries exceeded")

                self.alert_queue.task_done()
        except Exception as e:
            print(f"[VOICE TRACE 3] WORKER LOOP CRASHED: {e}")
            import traceback
            traceback.print_exc()

    def _generate_audio_file(self, alert: VoiceAlert) -> Optional[str]:
        """Generate audio file for the alert. Returns the filename (not full path)."""
        if not self.active_provider:
            return None

        # Determine file extension based on provider
        ext = ".mp3" if isinstance(self.active_provider, EdgeTTSProvider) else ".wav"
        filename = f"{alert.alert_id}{ext}"
        output_path = VOICE_AUDIO_DIR / filename

        try:
            success = self.active_provider.generate_audio(alert.message, str(output_path))
            if success and output_path.exists() and output_path.stat().st_size > 0:
                _cleanup_old_audio()
                return filename
            else:
                if output_path.exists():
                    output_path.unlink()
                return None
        except Exception as e:
            self.active_provider.error = str(e)
            # Try fallback provider
            for provider in self.tts_providers:
                if provider != self.active_provider and provider.is_available():
                    self.active_provider = provider
                    return self._generate_audio_file(alert)
            return None

    def get_status(self) -> Dict:
        return {
            "enabled": self.enabled,
            "active_provider": self.active_provider.name if self.active_provider else "NONE",
            "available_providers": [p.name for p in self.tts_providers if p.is_available()],
            "queue_size": self.alert_queue.qsize(),
            "paused": self._paused,
            "stats": self.stats.copy(),
        }

    def speak_immediate(self, text: str) -> Optional[str]:
        """Generate and return audio file immediately (bypass queue). Returns filename or None."""
        if not self.enabled or not self.active_provider:
            return None
        alert = VoiceAlert(
            alert_id=f"test-{int(time.time()*1000)}",
            worker_id="TEST",
            worker_name="Test",
            severity="INFO",
            priority=AlertPriority.INFO,
            message=text,
            root_cause="TEST",
            zone="Test",
        )
        return self._generate_audio_file(alert)


# Singleton
_default_voice_system = None


def get_voice_system() -> VoiceAlertSystem:
    global _default_voice_system
    if _default_voice_system is None:
        _default_voice_system = VoiceAlertSystem()
    return _default_voice_system