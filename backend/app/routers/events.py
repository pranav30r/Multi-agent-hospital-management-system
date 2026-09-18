import logging
import asyncio
import json
from typing import Dict, Set, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from starlette.websockets import WebSocketState

from app.config import settings
from app.auth.security import decode_access_token
from app.services.events import event_bus, get_tenant_channel, HospitalEvent
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket Event Stream"])


class TenantWebSocketManager:
    """
    Manages active WebSocket connections grouped by tenant_id.
    Subscribes to tenant-specific Redis Pub/Sub channels to fan out events
    across multiple distributed FastAPI worker instances.
    """

    def __init__(self):
        # Map of tenant_id -> Set of active WebSockets
        self._connections: Dict[str, Set[WebSocket]] = {}
        # Map of tenant_id -> background asyncio.Task listening on Redis Pub/Sub
        self._listener_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, tenant_id: str):
        """Accepts a WebSocket connection and registers it under the given tenant."""
        await websocket.accept()
        async with self._lock:
            if tenant_id not in self._connections:
                self._connections[tenant_id] = set()
            self._connections[tenant_id].add(websocket)
            logger.info(
                f"WebSocket client connected for tenant '{tenant_id}'. "
                f"Local connections for tenant: {len(self._connections[tenant_id])}"
            )
            # Ensure background Redis listener task is running for this tenant
            self._ensure_tenant_listener_locked(tenant_id)

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        """Unregisters a WebSocket connection and cleans up listener task if tenant has no active clients."""
        if tenant_id in self._connections:
            self._connections[tenant_id].discard(websocket)
            logger.info(
                f"WebSocket client disconnected for tenant '{tenant_id}'. "
                f"Remaining local connections: {len(self._connections[tenant_id])}"
            )
            if not self._connections[tenant_id]:
                del self._connections[tenant_id]
                self._cancel_tenant_listener(tenant_id)

    def _ensure_tenant_listener_locked(self, tenant_id: str):
        """Starts a Redis Pub/Sub background listener task for the tenant if not already running."""
        existing_task = self._listener_tasks.get(tenant_id)
        if existing_task is None or existing_task.done():
            task = asyncio.create_task(
                self._redis_tenant_listener_loop(tenant_id),
                name=f"redis_pubsub_listener_{tenant_id}"
            )
            self._listener_tasks[tenant_id] = task
            logger.info(f"Spawned Redis Pub/Sub background listener for tenant '{tenant_id}'")

    def _cancel_tenant_listener(self, tenant_id: str):
        """Cancels and cleans up the Redis listener task for an idle tenant."""
        task = self._listener_tasks.pop(tenant_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"Stopped idle Redis Pub/Sub listener for tenant '{tenant_id}'")

    async def _redis_tenant_listener_loop(self, tenant_id: str):
        """
        Background loop subscribing to Redis channel `hospital:events:{tenant_id}`
        and broadcasting received events to all local WebSockets for this tenant.
        """
        pubsub = None
        retry_delay = 1.0
        try:
            while True:
                try:
                    pubsub = await event_bus.get_pubsub_for_tenant(tenant_id)
                    if not pubsub:
                        # Redis might be offline/unreachable
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 10.0)
                        continue

                    retry_delay = 1.0  # Reset delay on successful connection
                    logger.info(f"Listening on Redis Pub/Sub channel for tenant '{tenant_id}'")

                    while True:
                        # Non-blocking get_message with timeout to allow cancellation
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message and message.get("type") == "message":
                            raw_data = message.get("data")
                            try:
                                if isinstance(raw_data, str):
                                    event_dict = json.loads(raw_data)
                                elif isinstance(raw_data, bytes):
                                    event_dict = json.loads(raw_data.decode("utf-8"))
                                else:
                                    event_dict = raw_data
                                await self._broadcast_to_tenant_local(tenant_id, event_dict)
                            except Exception as parse_err:
                                logger.warning(f"Error parsing Redis event payload: {parse_err}")
                        await asyncio.sleep(0.01)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning(f"Redis Pub/Sub listener error for tenant '{tenant_id}': {exc}. Reconnecting...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 10.0)

        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception as e:
                    logger.debug(f"Error closing pubsub for tenant '{tenant_id}': {e}")
            logger.info(f"Redis Pub/Sub listener terminated for tenant '{tenant_id}'")

    async def _broadcast_to_tenant_local(self, tenant_id: str, message: dict):
        """Fans out an event payload to all local WebSockets connected under tenant_id."""
        connections = list(self._connections.get(tenant_id, []))
        if not connections:
            return

        dead_connections = []
        for ws in connections:
            if ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_connections.append(ws)
            else:
                dead_connections.append(ws)

        for dc in dead_connections:
            self.disconnect(dc, tenant_id)

    async def broadcast(self, message: dict, tenant_id: Optional[str] = None):
        """
        Broadcasts an event:
        1. If tenant_id is supplied, publishes to Redis event bus (which fans out to all workers).
        2. Also immediately delivers to local websockets if Redis is unavailable.
        """
        eff_tenant = tenant_id or message.get("tenant_id") or "HOSP-DEFAULT"
        published = await event_bus.publish(message, tenant_id=eff_tenant)
        if not published:
            # Fallback to direct local broadcast if Redis is offline
            await self._broadcast_to_tenant_local(eff_tenant, message)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Sends a direct message to a single WebSocket client."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal WebSocket message: {e}")

    async def close_all(self):
        """Gracefully closes all local WebSocket connections and terminates all subscriber tasks."""
        logger.info("Closing all WebSocket connections and Redis listeners...")
        # Cancel all listener tasks
        for tenant_id, task in list(self._listener_tasks.items()):
            if not task.done():
                task.cancel()
        self._listener_tasks.clear()

        # Close all active sockets
        for tenant_id, sockets in list(self._connections.items()):
            for ws in list(sockets):
                try:
                    await ws.close(code=status.WS_1001_GOING_AWAY)
                except Exception:
                    pass
        self._connections.clear()


# Singleton connection manager
ws_manager = TenantWebSocketManager()


@router.websocket("/ws/events")
async def websocket_event_stream(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Authenticated WebSocket endpoint for real-time hospital event streaming.
    Clients connect with a valid JWT token (?token=...) to subscribe strictly
    to their tenant's event stream.
    """
    # 1. Authenticate and resolve tenant_id
    auth_token = token
    if not auth_token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]

    tenant_id = "HOSP-DEFAULT"
    user_id = "anonymous"

    if auth_token:
        payload = decode_access_token(auth_token)
        if not payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
            return
        tenant_id = payload.get("tenant_id") or "HOSP-DEFAULT"
        user_id = payload.get("sub") or "authenticated_user"
    else:
        # In production, require authentication strictly
        if settings.ENVIRONMENT.lower() in ["production", "prod"]:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication token required")
            return
        logger.warning("Unauthenticated WebSocket connection accepted in development mode for default tenant.")

    # 2. Connect client under authenticated tenant
    await ws_manager.connect(websocket, tenant_id=tenant_id)

    # 3. Send welcome event
    await ws_manager.send_personal(websocket, {
        "event_type": "SYSTEM_CONNECTED",
        "tenant_id": tenant_id,
        "timestamp": utc_now_iso(),
        "source": "SYSTEM",
        "payload": {
            "message": "Connected to Hospital Command Center Event Stream",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "server_time": utc_now_iso()
        }
    })

    # 4. Handle client inbound messages (ping/pong, keepalive)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await ws_manager.send_personal(websocket, {
                    "event_type": "PONG",
                    "tenant_id": tenant_id,
                    "timestamp": utc_now_iso(),
                    "source": "SYSTEM",
                    "payload": {}
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, tenant_id=tenant_id)
    except Exception as e:
        logger.error(f"WebSocket error for tenant '{tenant_id}': {e}")
        ws_manager.disconnect(websocket, tenant_id=tenant_id)
