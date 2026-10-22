import pytest
from unittest.mock import AsyncMock
from app.services.events import event_bus, HospitalEvent

@pytest.mark.asyncio
async def test_event_bus_local_fallback_when_redis_offline(monkeypatch):
    """
    Verify that when Redis is offline, event_bus.publish does NOT drop the event,
    but instead delivers it to the registered in-process subscriber (ws_manager).
    """
    received_events = []

    async def mock_local_subscriber(tenant_id: str, event_data: dict):
        received_events.append((tenant_id, event_data))

    # Register local subscriber
    event_bus.register_local_subscriber(mock_local_subscriber)

    # Explicitly mock Redis as unavailable (offline)
    monkeypatch.setattr(event_bus.manager, "get_client", AsyncMock(return_value=None))

    try:
        # Publish an event without Redis running
        test_payload = {"emergency_id": "EMR-TEST-01", "severity": "CRITICAL"}
        await event_bus.publish({
            "event_type": "EMERGENCY_DECLARED",
            "tenant_id": "HOSP-DEFAULT",
            "payload": test_payload
        })

        assert len(received_events) == 1, "Expected event to be delivered to local subscriber"
        t_id, ev = received_events[0]
        assert t_id == "HOSP-DEFAULT"
        assert ev["event_type"] == "EMERGENCY_DECLARED"
        assert ev["payload"]["emergency_id"] == "EMR-TEST-01"
    finally:
        event_bus._local_subscribers.clear()
