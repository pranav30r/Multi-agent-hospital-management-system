import logging
import json
import uuid
import re
from typing import Dict, Any, Optional, Union, AsyncIterator
from datetime import datetime
from pydantic import BaseModel, Field

from app.core.redis import redis_manager
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)

# Valid tenant ID pattern (alphanumeric, dashes, underscores only, prevents channel injection)
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


class HospitalEvent(BaseModel):
    """Structured hospital system event for distributed transport across workers."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    event_type: str = Field(..., description="E.g. AGENT_DECISION_PROPOSED, APPROVAL_REQUIRED, EMERGENCY_DECLARED")
    tenant_id: str = Field(..., description="Authoritative tenant identifier")
    timestamp: str = Field(default_factory=utc_now_iso)
    source: str = Field(default="SYSTEM", description="Originating agent or service component")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Structured non-sensitive event details")


def get_tenant_channel(tenant_id: str) -> str:
    """
    Constructs a sanitized Redis Pub/Sub channel key for a given tenant.
    Prevents wildcard subscriptions or cross-tenant channel spoofing.
    """
    if not tenant_id or not TENANT_ID_PATTERN.match(tenant_id):
        raise ValueError(f"Invalid tenant_id for event routing: '{tenant_id}'")
    return f"hospital:events:{tenant_id}"


class RedisEventBus:
    """
    Distributed real-time event bus leveraging Redis Pub/Sub.
    Enforces strict tenant isolation and non-blocking graceful degradation.
    """

    def __init__(self, manager=None):
        self.manager = manager or redis_manager
        self._local_subscriber = None

    def register_local_subscriber(self, callback):
        """Registers a fallback in-process callback (e.g. WebSocket manager) when Redis is unavailable."""
        self._local_subscriber = callback

    async def publish(
        self,
        event: Union[HospitalEvent, Dict[str, Any]],
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Publishes a structured event to the appropriate tenant Redis channel.
        Falls back to local in-process subscriber if Redis is unavailable.
        Returns True if sent to Redis, False if degraded/unavailable.
        Does NOT raise exceptions, preserving transactional integrity of the caller.
        """
        try:
            # 1. Normalize event
            if isinstance(event, dict):
                eff_tenant = tenant_id or event.get("tenant_id") or "HOSP-DEFAULT"
                event_data = {
                    "event_id": event.get("event_id") or f"evt-{uuid.uuid4().hex[:12]}",
                    "event_type": event.get("event_type", "GENERIC_EVENT"),
                    "tenant_id": eff_tenant,
                    "timestamp": event.get("timestamp") or utc_now_iso(),
                    "source": event.get("source", "SYSTEM"),
                    "payload": event.get("payload", {})
                }
                event_obj = HospitalEvent(**event_data)
            elif isinstance(event, HospitalEvent):
                event_obj = event
                if tenant_id:
                    event_obj.tenant_id = tenant_id
            else:
                logger.warning(f"Unsupported event object type: {type(event)}")
                return False

            channel = get_tenant_channel(event_obj.tenant_id)

            # 2. Obtain Redis Client
            client = await self.manager.get_client()
            if not client:
                logger.debug(f"Redis client not available. Falling back to local dispatch for {event_obj.event_type} on {channel}")
                if self._local_subscriber:
                    try:
                        await self._local_subscriber(event_obj.tenant_id, event_obj.model_dump())
                    except Exception as loc_err:
                        logger.warning(f"Local event dispatch failed: {loc_err}")
                return False

            # 3. Publish payload as JSON
            payload_json = event_obj.model_dump_json()
            subscribers_count = await client.publish(channel, payload_json)
            logger.debug(
                f"Published event {event_obj.event_type} ({event_obj.event_id}) to {channel}. "
                f"Active Redis subscribers: {subscribers_count}"
            )
            return True

        except Exception as exc:
            logger.warning(f"Failed to publish event to Redis Pub/Sub ({exc}). Continuing gracefully.")
            if self._local_subscriber and 'event_obj' in locals():
                try:
                    await self._local_subscriber(event_obj.tenant_id, event_obj.model_dump())
                except Exception as loc_err:
                    logger.warning(f"Local event dispatch failed: {loc_err}")
            return False

    async def get_pubsub_for_tenant(self, tenant_id: str):
        """
        Returns a Redis PubSub instance subscribed to the tenant's channel.
        Returns None if Redis is unreachable.
        """
        client = await self.manager.get_client()
        if not client:
            return None

        channel = get_tenant_channel(tenant_id)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed PubSub listener to Redis channel '{channel}'")
        return pubsub


# Singleton Event Bus instance
event_bus = RedisEventBus()
