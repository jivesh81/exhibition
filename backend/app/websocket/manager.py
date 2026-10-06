"""
SafeSight AI — WebSocket Manager
================================
Manages WebSocket connections for live alerts and snapshots.
"""
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import WEBSOCKET_LOGGER


@dataclass
class WSClient:
    """Connected WebSocket client."""
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Set[str] = field(default_factory=set)
    client_id: str = ""

    def __post_init__(self):
        if not self.client_id:
            self.client_id = f"client_{id(self)}"


class WebSocketManager:
    """
    Manages WebSocket connections with broadcasting and subscription support.
    """

    def __init__(self):
        self.clients: Dict[str, WSClient] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str = None) -> WSClient:
        """Accept new WebSocket connection."""
        await websocket.accept()
        client = WSClient(websocket=websocket, client_id=client_id or f"client_{len(self.clients)}")
        async with self._lock:
            self.clients[client.client_id] = client
        WEBSOCKET_LOGGER.info("Client connected", client_id=client.client_id, total=len(self.clients))
        return client

    async def disconnect(self, client_id: str):
        """Remove client."""
        async with self._lock:
            if client_id in self.clients:
                del self.clients[client_id]
        WEBSOCKET_LOGGER.info("Client disconnected", client_id=client_id, total=len(self.clients))

    async def broadcast(self, message: Dict[str, Any], subscription: str = None):
        """Broadcast message to all clients (or those subscribed to topic)."""
        dead_clients = []
        message_str = json.dumps(message)

        async with self._lock:
            clients = list(self.clients.values())

        for client in clients:
            try:
                if subscription is None or subscription in client.subscriptions:
                    await client.websocket.send_text(message_str)
            except Exception as e:
                WEBSOCKET_LOGGER.warning("Broadcast failed", client_id=client.client_id, error=str(e))
                dead_clients.append(client.client_id)

        # Cleanup dead clients
        for client_id in dead_clients:
            await self.disconnect(client_id)

    async def send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific client."""
        async with self._lock:
            client = self.clients.get(client_id)

        if not client:
            return False

        try:
            await client.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            WEBSOCKET_LOGGER.error("Send failed", client_id=client_id, error=str(e))
            await self.disconnect(client_id)
            return False

    def subscribe(self, client_id: str, topic: str):
        """Subscribe client to topic."""
        if client_id in self.clients:
            self.clients[client_id].subscriptions.add(topic)

    def unsubscribe(self, client_id: str, topic: str):
        """Unsubscribe client from topic."""
        if client_id in self.clients:
            self.clients[client_id].subscriptions.discard(topic)

    def get_connected_clients(self) -> List[Dict[str, Any]]:
        """Get info about connected clients."""
        return [
            {
                "client_id": c.client_id,
                "connected_at": c.connected_at.isoformat(),
                "subscriptions": list(c.subscriptions),
            }
            for c in self.clients.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "connected_clients": len(self.clients),
            "total_subscriptions": sum(len(c.subscriptions) for c in self.clients.values()),
        }


# Global instance
_websocket_manager = None


def get_websocket_manager() -> WebSocketManager:
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager