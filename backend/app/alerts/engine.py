"""
SafeSight AI — Alert Decision Engine
====================================
Manages alert lifecycle: deduplication, cooldown, escalation, priority queue.
Decouples event generation from alert delivery.
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from collections import deque
import threading

from app.core.config import settings
from app.core.logging import ALERT_LOGGER, TTS_LOGGER


class AlertPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    WARNING = 2
    INFO = 3

    def __lt__(self, other):
        return self.value < other.value


class AlertStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    SUPPRESSED = "suppressed"
    FAILED = "failed"


@dataclass
class SafetyEvent:
    """A safety event from the risk engine."""
    event_id: str
    timestamp: float
    worker_id: str
    worker_name: str
    event_type: str
    severity: str  # SAFE, WARNING, HIGH, CRITICAL
    risk_score: float
    confidence: float
    zone_id: Optional[str]
    zone_name: Optional[str]
    position: Dict[str, float]  # x, y
    evidence: Dict[str, Any]  # PPE, proximity, posture, etc.
    root_cause: str
    source: str  # "demo", "realtime", "manual"
    tracking_id: Optional[int] = None


@dataclass
class Alert:
    """An alert to be delivered."""
    alert_id: str
    event_id: str
    worker_id: str
    worker_name: str
    severity: str
    priority: AlertPriority
    message: str
    root_cause: str
    zone: str
    timestamp: float
    audio_file: Optional[str] = None
    audio_url: Optional[str] = None
    status: AlertStatus = AlertStatus.PENDING
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AlertCooldownManager:
    """
    Manages cooldown periods to prevent alert spam.
    Per-worker, per-severity cooldown with escalation override.
    """

    SEVERITY_RANK = {"SAFE": 0, "INFO": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}

    def __init__(
        self,
        base_cooldown: float = None,
        critical_cooldown: float = None,
        escalation_override: bool = None,
    ):
        self.base_cooldown = base_cooldown or settings.ALERT_BASE_COOLDOWN
        self.critical_cooldown = critical_cooldown or settings.ALERT_CRITICAL_COOLDOWN
        self.escalation_override = escalation_override if escalation_override is not None else settings.ALERT_ESCALATION_OVERRIDE

        self.last_alert: Dict[str, Dict[str, float]] = {}
        self.last_severity: Dict[str, str] = {}
        self._lock = threading.RLock()

    def should_alert(self, worker_id: str, severity: str) -> bool:
        with self._lock:
            now = time.time()
            if worker_id not in self.last_alert:
                self.last_alert[worker_id] = {}
                self.last_severity[worker_id] = "SAFE"

            last_sev = self.last_severity[worker_id]
            current_rank = self.SEVERITY_RANK.get(severity, 0)
            last_rank = self.SEVERITY_RANK.get(last_sev, 0)

            # Escalation override: allow if severity increased
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


class AlertDeduplicator:
    """Deduplicates alerts by event_id and worker_id+severity within time window."""

    def __init__(self, window_seconds: float = 30.0):
        self.window_seconds = window_seconds
        self.recent_alerts: Dict[str, float] = {}  # key -> timestamp
        self._lock = threading.RLock()

    def _make_key(self, event_id: str = None, worker_id: str = None, severity: str = None) -> str:
        if event_id:
            return f"event:{event_id}"
        return f"worker:{worker_id}:{severity}"

    def is_duplicate(self, event_id: str = None, worker_id: str = None, severity: str = None) -> bool:
        with self._lock:
            key = self._make_key(event_id, worker_id, severity)
            now = time.time()
            if key in self.recent_alerts:
                if now - self.recent_alerts[key] < self.window_seconds:
                    return True
            return False

    def record(self, event_id: str = None, worker_id: str = None, severity: str = None):
        with self._lock:
            key = self._make_key(event_id, worker_id, severity)
            self.recent_alerts[key] = time.time()
            # Cleanup old entries
            now = time.time()
            self.recent_alerts = {k: v for k, v in self.recent_alerts.items() if now - v < self.window_seconds * 2}


class AlertDecisionEngine:
    """
    Main alert decision engine.
    Processes safety events and decides which become alerts.
    """

    def __init__(
        self,
        cooldown_manager: Optional[AlertCooldownManager] = None,
        deduplicator: Optional[AlertDeduplicator] = None,
        voice_service: Optional[Any] = None,
        websocket_manager: Optional[Any] = None,
        database: Optional[Any] = None,
    ):
        self.cooldown = cooldown_manager or AlertCooldownManager()
        self.deduplicator = deduplicator or AlertDeduplicator()
        self.voice_service = voice_service
        self.websocket_manager = websocket_manager
        self.database = database

        self.alert_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.pending_alerts: Dict[str, Alert] = {}
        self.active_alerts: Dict[str, Alert] = {}  # worker_id -> alert
        self.alert_history: deque = deque(maxlen=1000)

        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()

        # Callbacks
        on_alert_created: Optional[Callable[[Alert], None]] = None
        on_alert_sent: Optional[Callable[[Alert], None]] = None
        on_alert_failed: Optional[Callable[[Alert, str], None]] = None
        on_clear_announcement: Optional[Callable[[str, str, str], None]] = None

        self.stats = {
            "events_received": 0,
            "alerts_created": 0,
            "alerts_sent": 0,
            "alerts_suppressed": 0,
            "alerts_failed": 0,
            "clears_announced": 0,
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        ALERT_LOGGER.info("AlertDecisionEngine started")

    def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
        ALERT_LOGGER.info("AlertDecisionEngine stopped")

    async def _process_queue(self):
        while self._running:
            try:
                priority_val, timestamp, alert = await asyncio.wait_for(
                    self.alert_queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            try:
                await self._deliver_alert(alert)
                self.stats["alerts_sent"] += 1
                self.alert_history.append({
                    "alert_id": alert.alert_id,
                    "worker_id": alert.worker_id,
                    "severity": alert.severity,
                    "status": "sent",
                    "timestamp": time.time(),
                })
            except Exception as e:
                alert.status = AlertStatus.FAILED
                alert.retry_count += 1
                self.stats["alerts_failed"] += 1
                ALERT_LOGGER.error(f"Alert delivery failed", alert_id=alert.alert_id, error=str(e))

                if alert.retry_count < 3:
                    await asyncio.sleep(1)
                    await self.alert_queue.put((priority_val, timestamp, alert))
                elif self.on_alert_failed:
                    self.on_alert_failed(alert, str(e))

            self.alert_queue.task_done()

    async def _deliver_alert(self, alert: Alert):
        """Deliver alert through all channels."""
        alert.status = AlertStatus.QUEUED

        # 1. Generate voice audio if voice service available
        if self.voice_service and not alert.audio_file:
            try:
                audio_file = self.voice_service.speak_immediate(alert.message)
                if audio_file:
                    alert.audio_file = audio_file
                    alert.audio_url = f"/api/voice/audio/{audio_file}"
            except Exception as e:
                TTS_LOGGER.error(f"Voice generation failed", alert_id=alert.alert_id, error=str(e))

        # 2. Send via WebSocket
        if self.websocket_manager:
            try:
                await self.websocket_manager.broadcast({
                    "type": "voice_alert",
                    "alert": {
                        "alert_id": alert.alert_id,
                        "event_id": alert.event_id,
                        "worker_id": alert.worker_id,
                        "worker_name": alert.worker_name,
                        "severity": alert.severity,
                        "message": alert.message,
                        "root_cause": alert.root_cause,
                        "zone": alert.zone,
                        "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat(),
                        "audio_url": alert.audio_url,
                    }
                })
            except Exception as e:
                ALERT_LOGGER.error(f"WebSocket broadcast failed", alert_id=alert.alert_id, error=str(e))

        # 3. Persist to database
        if self.database:
            try:
                self.database.insert_voice_event(
                    alert.worker_id, alert.worker_name, alert.severity,
                    alert.message, alert.root_cause, alert.zone
                )
            except Exception as e:
                ALERT_LOGGER.error(f"Database insert failed", alert_id=alert.alert_id, error=str(e))

        alert.status = AlertStatus.SENT
        if self.on_alert_sent:
            self.on_alert_sent(alert)

    def process_event(self, event: SafetyEvent) -> Optional[Alert]:
        """
        Process a safety event and decide whether to create an alert.
        Returns the created alert or None if suppressed.
        """
        self.stats["events_received"] += 1

        # Check deduplication
        if self.deduplicator.is_duplicate(event_id=event.event_id):
            ALERT_LOGGER.debug("Event deduplicated", event_id=event.event_id)
            self.stats["alerts_suppressed"] += 1
            return None

        # Check cooldown
        if not self.cooldown.should_alert(event.worker_id, event.severity):
            ALERT_LOGGER.debug("Alert suppressed by cooldown", worker_id=event.worker_id, severity=event.severity)
            self.stats["alerts_suppressed"] += 1
            return None

        # Check if this is a clear announcement
        if event.severity == "SAFE" and event.event_type == "ZONE_CLEAR":
            if not self.cooldown.should_announce_clear(event.worker_id):
                return None
            self.cooldown.record_clear(event.worker_id)
            alert = self._create_clear_alert(event)
        else:
            # Regular alert
            self.cooldown.record_alert(event.worker_id, event.severity)
            self.deduplicator.record(event_id=event.event_id)
            alert = self._create_alert(event)

        self.stats["alerts_created"] += 1
        self.pending_alerts[alert.alert_id] = alert

        if self.on_alert_created:
            self.on_alert_created(alert)

        # Queue for delivery
        priority_val = alert.priority.value
        asyncio.create_task(self.alert_queue.put((priority_val, alert.timestamp, alert)))

        return alert

    def _create_alert(self, event: SafetyEvent) -> Alert:
        """Create alert from safety event."""
        priority_map = {
            "CRITICAL": AlertPriority.CRITICAL,
            "HIGH": AlertPriority.HIGH,
            "WARNING": AlertPriority.WARNING,
            "INFO": AlertPriority.INFO,
            "SAFE": AlertPriority.INFO,
        }

        # Generate dynamic message
        message = self._generate_message(event)

        return Alert(
            alert_id=f"{event.worker_id}-{int(time.time() * 1000)}",
            event_id=event.event_id,
            worker_id=event.worker_id,
            worker_name=event.worker_name,
            severity=event.severity,
            priority=priority_map.get(event.severity, AlertPriority.INFO),
            message=message,
            root_cause=event.root_cause,
            zone=event.zone_name or "Unknown",
            timestamp=event.timestamp,
            metadata={
                "event_type": event.event_type,
                "risk_score": event.risk_score,
                "confidence": event.confidence,
                "tracking_id": event.tracking_id,
            }
        )

    def _create_clear_alert(self, event: SafetyEvent) -> Alert:
        """Create clear announcement alert."""
        return Alert(
            alert_id=f"{event.worker_id}-clear-{int(time.time() * 1000)}",
            event_id=event.event_id,
            worker_id=event.worker_id,
            worker_name=event.worker_name,
            severity="SAFE",
            priority=AlertPriority.INFO,
            message=f"{event.worker_name}, area is now clear.",
            root_cause="ZONE_CLEAR",
            zone=event.zone_name or "the area",
            timestamp=event.timestamp,
            metadata={"clear_announcement": True}
        )

    def _generate_message(self, event: SafetyEvent) -> str:
        """Generate natural language message from event."""
        worker_id = event.worker_id
        severity = event.severity
        root_cause = event.root_cause
        zone = event.zone_name or "the area"
        distance = event.evidence.get("distance")

        if severity == "CRITICAL":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                return f"{worker_id}, critical danger. Safety helmet required in this area. Leave immediately."
            if "proximity" in root_cause.lower() or "closing" in root_cause.lower():
                return f"{worker_id}, critical danger detected. You are too close to the hazard. Leave this area immediately."
            if "posture" in root_cause.lower():
                return f"{worker_id}, critical safety violation. Unsafe posture detected in hazard zone. Move to safety immediately."
            return f"{worker_id}, critical danger detected. Please leave this area immediately."

        elif severity == "HIGH":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                missing = []
                ppe = event.evidence.get("ppe", {})
                if not ppe.get("helmet"): missing.append("helmet")
                if not ppe.get("vest"): missing.append("vest")
                if not ppe.get("gloves"): missing.append("gloves")
                items = ", ".join(missing)
                return f"{worker_id}, {items} required in this area. Please comply immediately."
            if "proximity" in root_cause.lower():
                dist_msg = f" at {distance:.1f} meters" if distance else ""
                return f"{worker_id}, high risk. You are approaching a hazardous area{dist_msg}. Please maintain safe distance."
            if "posture" in root_cause.lower():
                return f"{worker_id}, unsafe posture detected. Please correct your posture for safety."
            return f"{worker_id}, high risk detected in {zone}. Exercise caution."

        elif severity == "WARNING":
            if "helmet" in root_cause.lower() or "ppe" in root_cause.lower():
                missing = []
                ppe = event.evidence.get("ppe", {})
                if not ppe.get("helmet"): missing.append("helmet")
                if not ppe.get("vest"): missing.append("vest")
                if not ppe.get("gloves"): missing.append("gloves")
                items = ", ".join(missing)
                return f"{worker_id}, warning. {items} required in this zone."
            if "proximity" in root_cause.lower():
                return f"{worker_id}, warning. You are approaching a hazardous area. Please be cautious."
            return f"{worker_id}, warning. Safety violation detected in {zone}."

        return f"{worker_id}, status updated."

    def get_status(self) -> Dict:
        return {
            "running": self._running,
            "queue_size": self.alert_queue.qsize(),
            "pending_alerts": len(self.pending_alerts),
            "active_workers": len(self.active_alerts),
            "cooldown_manager": "active",
            "stats": self.stats.copy(),
        }


# Singleton instance
_default_engine = None


def get_alert_engine() -> AlertDecisionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AlertDecisionEngine()
    return _default_engine