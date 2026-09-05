import logging
import asyncio
import json
from datetime import datetime
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket Event Stream"])


class ConnectionManager:
    """Manages active WebSocket connections for real-time event broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast an event to all connected WebSocket clients."""
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for dc in dead_connections:
            if dc in self.active_connections:
                self.active_connections.remove(dc)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal WebSocket message: {e}")


# Singleton connection manager — Person 2's agents will import this
# to push events to the frontend in real-time
ws_manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_event_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time hospital event streaming.
    The Command Center frontend connects here to receive live agent decisions,
    bed status changes, emergency alerts, and approval notifications.
    """
    await ws_manager.connect(websocket)

    from app.utils.datetime_utils import utc_now_iso

    # Send welcome event
    await ws_manager.send_personal(websocket, {
        "event_type": "SYSTEM_CONNECTED",
        "timestamp": utc_now_iso(),
        "source": "SYSTEM",
        "payload": {
            "message": "Connected to Hospital Command Center Event Stream",
            "server_time": utc_now_iso()
        }
    })

    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await websocket.receive_text()
            # Client can send ping/pong or commands
            if data == "ping":
                await ws_manager.send_personal(websocket, {
                    "event_type": "PONG",
                    "timestamp": utc_now_iso(),
                    "source": "SYSTEM",
                    "payload": {}
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
