import asyncio
import json
import pytest
import pytest_asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.services.events import HospitalEvent, RedisEventBus, get_tenant_channel
from app.core.redis import RedisManager
from app.routers.events import TenantWebSocketManager, ws_manager
from app.auth.security import create_access_token


# ─── 1. Schema & Serialization Tests ──────────────────────────────────────────

def test_hospital_event_serialization():
    event = HospitalEvent(
        event_type="AGENT_DECISION_PROPOSED",
        tenant_id="HOSP-TENANT-A",
        source="coordinator_agent",
        payload={"decision_id": "DEC-1234", "action_type": "RECOMMEND_BED"}
    )
    json_str = event.model_dump_json()
    data = json.loads(json_str)

    assert data["event_type"] == "AGENT_DECISION_PROPOSED"
    assert data["tenant_id"] == "HOSP-TENANT-A"
    assert data["source"] == "coordinator_agent"
    assert data["payload"]["decision_id"] == "DEC-1234"
    assert "event_id" in data
    assert "timestamp" in data


def test_tenant_channel_sanitization():
    assert get_tenant_channel("HOSP-TENANT-A") == "hospital:events:HOSP-TENANT-A"
    assert get_tenant_channel("tenant_123") == "hospital:events:tenant_123"

    with pytest.raises(ValueError):
        get_tenant_channel("")

    with pytest.raises(ValueError):
        get_tenant_channel("tenant*wildcard")

    with pytest.raises(ValueError):
        get_tenant_channel("tenant:inject")


# ─── 2. Redis Event Bus Unit & Isolation Tests ───────────────────────────────

@pytest.mark.asyncio
async def test_event_bus_publish_success():
    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 2  # 2 subscribers

    mock_manager = MagicMock()
    mock_manager.get_client = AsyncMock(return_value=mock_redis)

    bus = RedisEventBus(manager=mock_manager)
    success = await bus.publish({
        "event_type": "EMERGENCY_DECLARED",
        "tenant_id": "TENANT-1",
        "payload": {"severity": "CRITICAL"}
    })

    assert success is True
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == "hospital:events:TENANT-1"
    published_dict = json.loads(call_args[0][1])
    assert published_dict["event_type"] == "EMERGENCY_DECLARED"
    assert published_dict["tenant_id"] == "TENANT-1"


@pytest.mark.asyncio
async def test_event_bus_graceful_degradation_on_redis_error():
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = ConnectionError("Redis server unreachable")

    mock_manager = MagicMock()
    mock_manager.get_client = AsyncMock(return_value=mock_redis)

    bus = RedisEventBus(manager=mock_manager)
    # Must not raise an exception; must return False gracefully
    success = await bus.publish({
        "event_type": "BED_ASSIGNED",
        "tenant_id": "TENANT-1",
        "payload": {"bed_id": "BED-01"}
    })

    assert success is False


@pytest.mark.asyncio
async def test_event_bus_graceful_degradation_when_client_is_none():
    mock_manager = MagicMock()
    mock_manager.get_client = AsyncMock(return_value=None)

    bus = RedisEventBus(manager=mock_manager)
    success = await bus.publish({
        "event_type": "BED_ASSIGNED",
        "tenant_id": "TENANT-1"
    })
    assert success is False


# ─── 3. Multi-Tenant Cross-Process PubSub Simulation ─────────────────────────

class SimulatedRedisBroker:
    """Simulates a multi-tenant Redis Pub/Sub instance across multiple workers."""
    def __init__(self):
        self.channels: Dict[str, List[asyncio.Queue]] = {}

    def get_subscriber(self, channel: str) -> "SimulatedPubSub":
        if channel not in self.channels:
            self.channels[channel] = []
        queue = asyncio.Queue()
        self.channels[channel].append(queue)
        return SimulatedPubSub(self, channel, queue)

    async def publish(self, channel: str, message: str) -> int:
        queues = self.channels.get(channel, [])
        for q in queues:
            await q.put(message)
        return len(queues)


class SimulatedPubSub:
    def __init__(self, broker: SimulatedRedisBroker, channel: str, queue: asyncio.Queue):
        self.broker = broker
        self.channel = channel
        self.queue = queue

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        try:
            raw = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            return {"type": "message", "data": raw}
        except asyncio.TimeoutError:
            return None

    async def unsubscribe(self):
        if self.channel in self.broker.channels and self.queue in self.broker.channels[self.channel]:
            self.broker.channels[self.channel].remove(self.queue)

    async def close(self):
        await self.unsubscribe()


@pytest.mark.asyncio
async def test_multi_tenant_channel_isolation_simulation():
    """Verify that Tenant A subscribers NEVER receive events published on Tenant B channels."""
    broker = SimulatedRedisBroker()

    # Worker 1 subscribes to Tenant A
    sub_tenant_a = broker.get_subscriber("hospital:events:TENANT-A")
    # Worker 2 subscribes to Tenant B
    sub_tenant_b = broker.get_subscriber("hospital:events:TENANT-B")

    # Publish an event to Tenant A
    event_a = json.dumps({"event_type": "ALERT", "tenant_id": "TENANT-A", "msg": "Secret A"})
    await broker.publish("hospital:events:TENANT-A", event_a)

    # Publish an event to Tenant B
    event_b = json.dumps({"event_type": "ALERT", "tenant_id": "TENANT-B", "msg": "Secret B"})
    await broker.publish("hospital:events:TENANT-B", event_b)

    # Check Tenant A subscriber
    msg_a = await sub_tenant_a.get_message(timeout=0.1)
    assert msg_a is not None
    assert json.loads(msg_a["data"])["msg"] == "Secret A"

    # Check Tenant B subscriber
    msg_b = await sub_tenant_b.get_message(timeout=0.1)
    assert msg_b is not None
    assert json.loads(msg_b["data"])["msg"] == "Secret B"

    # Verify no cross-channel leakage
    assert await sub_tenant_a.get_message(timeout=0.05) is None
    assert await sub_tenant_b.get_message(timeout=0.05) is None

    await sub_tenant_a.close()
    await sub_tenant_b.close()


# ─── 4. WebSocket Client & Authentication Tests ──────────────────────────────

def test_websocket_event_stream_unauthenticated_dev():
    """In development mode, unauthenticated WebSocket gets assigned HOSP-DEFAULT."""
    client = TestClient(app)
    with client.websocket_connect("/ws/events") as ws:
        welcome = ws.receive_json()
        assert welcome["event_type"] == "SYSTEM_CONNECTED"
        assert welcome["tenant_id"] == "HOSP-DEFAULT"

        # Test ping/pong
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["event_type"] == "PONG"
        assert pong["tenant_id"] == "HOSP-DEFAULT"


def test_websocket_event_stream_authenticated_tenant():
    """Authenticated WebSocket derives tenant_id strictly from JWT token."""
    token = create_access_token(
        data={"sub": "STF-999", "role": "DOCTOR", "tenant_id": "TENANT-HOSPITAL-X"}
    )
    client = TestClient(app)
    with client.websocket_connect(f"/ws/events?token={token}") as ws:
        welcome = ws.receive_json()
        assert welcome["event_type"] == "SYSTEM_CONNECTED"
        assert welcome["tenant_id"] == "TENANT-HOSPITAL-X"
        assert welcome["payload"]["user_id"] == "STF-999"


# ─── 5. Real Redis Server Integration (Conditional) ──────────────────────────

async def is_real_redis_available() -> bool:
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url("redis://localhost:6379/0", socket_connect_timeout=0.5)
        res = await client.ping()
        await client.aclose()
        return bool(res)
    except Exception:
        return False


@pytest.mark.asyncio
async def test_real_redis_pubsub_if_available():
    """Tests real Redis server if one is active locally; skipped if not running."""
    if not await is_real_redis_available():
        pytest.skip("Local Redis server is not reachable at redis://localhost:6379/0")

    manager = RedisManager("redis://localhost:6379/0")
    await manager.initialize()
    bus = RedisEventBus(manager=manager)

    test_tenant = "REAL-TEST-TENANT"
    pubsub = await bus.get_pubsub_for_tenant(test_tenant)
    assert pubsub is not None

    test_event = {
        "event_type": "INTEGRATION_TEST_EVENT",
        "tenant_id": test_tenant,
        "payload": {"status": "SUCCESS"}
    }
    published = await bus.publish(test_event, tenant_id=test_tenant)
    assert published is True

    # Read from pubsub
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
    assert msg is not None
    data = json.loads(msg["data"])
    assert data["event_type"] == "INTEGRATION_TEST_EVENT"
    assert data["tenant_id"] == test_tenant

    await pubsub.unsubscribe()
    await pubsub.close()
    await manager.close()
