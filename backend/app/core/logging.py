"""
SafeSight AI — Structured Logging
=================================
Provides structured logging with consistent format for all pipeline stages.
"""
import logging
import sys
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {"name", "msg", "args", "levelname", "levelno", "pathname",
                           "filename", "module", "lineno", "funcName", "created",
                           "msecs", "relativeCreated", "thread", "threadName",
                           "processName", "process", "message", "exc_info",
                           "exc_text", "stack_info", "getMessage"}:
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class PipelineLogger:
    """Logger for pipeline stages with consistent formatting."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.stage = name.upper()

    def _log(self, level: int, message: str, **kwargs):
        extra = {"stage": self.stage, **kwargs}
        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)


# Pre-configured loggers for each pipeline stage
DETECTION_LOGGER = PipelineLogger("DETECTION")
TRACKING_LOGGER = PipelineLogger("TRACKING")
RISK_LOGGER = PipelineLogger("RISK")
EVENT_LOGGER = PipelineLogger("EVENT")
ALERT_LOGGER = PipelineLogger("ALERT")
TTS_LOGGER = PipelineLogger("TTS")
VOICE_LOGGER = PipelineLogger("VOICE")
WEBSOCKET_LOGGER = PipelineLogger("WEBSOCKET")
FRONTEND_LOGGER = PipelineLogger("FRONTEND")
DATABASE_LOGGER = PipelineLogger("DATABASE")
DEMO_LOGGER = PipelineLogger("DEMO")


def log_pipeline_stage(stage: str):
    """Decorator to log function entry/exit with timing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = PipelineLogger(stage)
            start = time.time()
            logger.debug(f"{func.__name__} started")
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(f"{func.__name__} completed", duration_ms=round(elapsed * 1000, 2))
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"{func.__name__} failed", duration_ms=round(elapsed * 1000, 2), error=str(e))
                raise
        return wrapper
    return decorator


def setup_logging(level: str = "INFO", json_format: bool = False):
    """Configure application logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(stage)s] %(message)s",
                datefmt="%H:%M:%S"
            )
        )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)