"""
SafeSight AI — FastAPI Application (Modular)
=============================================
Main application entry point with clean architecture.
"""
import os
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import get_all_routers
from app.globals import (
    PROVIDERS, RISK_MODEL, FUSION_ENGINE, FEATURE_EXTRACTOR,
    WORKER_TRACKER, VOICE_SYSTEM, VOICE_SERVICE, WS_MANAGER,
    ALERT_ENGINE, EVENT_ENGINE, DEMO, SCENARIOS,
)
from voice import VoiceAlert

import database as db


# Setup structured logging
setup_logging(level="INFO", json_format=False)


# Event loop reference for thread-safe broadcasting
_main_loop = None


# Unified WebSocket broadcast function
def _broadcast_threadsafe(message: dict):
    """Broadcast from demo thread to WebSocket manager."""
    global _main_loop
    try:
        if WS_MANAGER.clients and _main_loop is not None and _main_loop.is_running():
            print(f"[WS VOICE BROADCAST] sending to {len(WS_MANAGER.clients)} clients: type={message.get('type')}, worker={message.get('alert', {}).get('worker_id')}, severity={message.get('alert', {}).get('severity')}")
            asyncio.run_coroutine_threadsafe(WS_MANAGER.broadcast(message), _main_loop)
        else:
            print(f"[WS VOICE BROADCAST] SKIPPED - no clients or loop not ready: clients={len(WS_MANAGER.clients) if WS_MANAGER.clients else 0}, loop_running={_main_loop.is_running() if _main_loop else False}")
    except Exception as e:
        print(f"[WS VOICE BROADCAST] ERROR: {e}")


# Voice alert callback
def _on_voice_alert(alert: VoiceAlert):
    audio_url = None
    if alert.audio_file:
        audio_url = f"/api/voice/audio/{alert.audio_file}"

    print(f"[VOICE TRACE 5] on_alert_spoken callback firing: alert_id={alert.alert_id}, worker={alert.worker_id}, audio_url={audio_url}")

    _broadcast_threadsafe({
        "type": "voice_alert",
        "alert": {
            "worker_id": alert.worker_id,
            "worker_name": alert.worker_name,
            "severity": alert.severity,
            "message": alert.message,
            "root_cause": alert.root_cause,
            "zone": alert.zone,
            "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat(),
            "audio_url": audio_url,
            "alert_id": alert.alert_id,
        }
    })
    print(f"[VOICE TRACE 6] voice_alert broadcast sent to WebSocket: worker={alert.worker_id}, severity={alert.severity}, audio_url={audio_url}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    # Startup
    _main_loop = asyncio.get_running_loop()
    db.init_db()
    DEMO.load_world()

    # Wire demo engine to new WebSocket manager
    DEMO.on_event = lambda event: _broadcast_threadsafe(event)
    DEMO.on_snapshot = lambda snap: _broadcast_threadsafe(snap)

    # Initialize alert engine with dependencies
    ALERT_ENGINE.voice_service = VOICE_SYSTEM
    ALERT_ENGINE.websocket_manager = WS_MANAGER
    ALERT_ENGINE.database = db
    ALERT_ENGINE.start()

    # Start voice system worker thread
    VOICE_SYSTEM.start()

    # Initialize event engine
    # EVENT_ENGINE is already initialized

    print(f"[SafeSight] ML Model loaded: {RISK_MODEL.is_model_loaded()}")
    print(f"[SafeSight] Voice System: {VOICE_SYSTEM.get_status()['active_provider']}")
    print(f"[SafeSight] Worker Tracker: Ready")
    print(f"[SafeSight] Alert Engine: Started")
    print(f"[SafeSight] Event Engine: Started")

    yield

    # Shutdown
    ALERT_ENGINE.stop()
    VOICE_SYSTEM.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Workplace Safety Monitoring and Risk Assessment Platform — Group 173",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
for router in get_all_routers():
    app.include_router(router)


# Static frontend serving
_FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(_FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, reload=settings.RELOAD)