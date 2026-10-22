"""
Reliable Event-Driven Multi-Agent Listener and Lifespan Integration.

Subscribes to hospital domain events (PATIENT_INTAKE_COMPLETED, EMERGENCY_DECLARED),
enqueues background evaluation requests non-blockingly, guarantees idempotency and
concurrency control, and executes multi-agent orchestration within isolated database sessions.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Set, List, Callable
from pydantic import BaseModel, Field
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.patient import Encounter
from app.services.agent_orchestrator import MultiAgentOrchestratorService
from app.services.events import event_bus, get_tenant_channel

logger = logging.getLogger(__name__)

EVENT_PATIENT_INTAKE_COMPLETED = "PATIENT_INTAKE_COMPLETED"
EVENT_EMERGENCY_DECLARED = "EMERGENCY_DECLARED"
HANDLED_EVENT_TYPES = {EVENT_PATIENT_INTAKE_COMPLETED, EVENT_EMERGENCY_DECLARED}


class EventListenerConfig(BaseModel):
    """Configuration settings for the background event listener worker."""
    max_retries: int = Field(default=3, ge=1, le=10)
    base_backoff_seconds: float = Field(default=0.1, ge=0.01)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    queue_max_size: int = Field(default=500, ge=10)
    worker_concurrency: int = Field(default=2, ge=1, le=10)
    dedup_window_size: int = Field(default=1000, ge=100)
    enable_redis_pubsub: bool = False  # Local fallback is always enabled; Redis optional


class AgentEventListener:
    """
    Background event listener coordinating autonomous multi-agent evaluations
    triggered by domain events with strict idempotency and isolated DB sessions.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        config: Optional[EventListenerConfig] = None
    ):
        self.session_factory = session_factory or AsyncSessionLocal
        self.config = config or EventListenerConfig()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.queue_max_size)
        self._running: bool = False
        self._worker_tasks: List[asyncio.Task] = []
        
        # Concurrency & Idempotency Controls
        self._in_flight_encounters: Set[str] = set()
        self._in_flight_lock = asyncio.Lock()
        self._processed_event_ids: Set[str] = set()
        self._processed_events_order: List[str] = []
        self._processed_lock = asyncio.Lock()

        # Telemetry metrics
        self.stats: Dict[str, int] = {
            "events_received": 0,
            "evaluations_triggered": 0,
            "duplicates_ignored": 0,
            "retries": 0,
            "failures": 0,
        }

    # ─── Lifecycle Management ─────────────────────────────────────────────────

    async def start(self) -> None:
        """Starts background worker tasks and registers local event subscriber."""
        if self._running:
            return

        self._running = True
        logger.info(f"Starting AgentEventListener with {self.config.worker_concurrency} worker(s)...")

        # 1. Register with event bus fallback subscriber
        event_bus.register_local_subscriber(self.handle_event_callback)

        # 2. Spawn consumer workers
        for i in range(self.config.worker_concurrency):
            task = asyncio.create_task(
                self._worker_loop(i + 1),
                name=f"agent_event_worker_{i + 1}"
            )
            self._worker_tasks.append(task)

        logger.info("AgentEventListener started successfully.")

    async def stop(self) -> None:
        """Gracefully stops background workers and clears resources."""
        if not self._running:
            return

        logger.info("Stopping AgentEventListener background workers...")
        self._running = False

        # Cancel workers
        for task in self._worker_tasks:
            if not task.done():
                task.cancel()

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()

        # Drain remaining queue items
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        logger.info("AgentEventListener stopped cleanly.")

    # ─── Event Ingestion (Non-Blocking) ───────────────────────────────────────

    async def handle_event_callback(self, tenant_id: str, event_data: dict) -> None:
        """
        In-process event intake callback.
        Enqueues relevant events into the worker queue in O(1) time without blocking the publisher.
        """
        event_type = event_data.get("event_type")
        if event_type not in HANDLED_EVENT_TYPES:
            return

        self.stats["events_received"] += 1
        event_id = event_data.get("event_id")

        # Fast deduplication check on event_id
        if event_id:
            async with self._processed_lock:
                if event_id in self._processed_event_ids:
                    logger.debug(f"Discarding duplicate event {event_id} ({event_type})")
                    self.stats["duplicates_ignored"] += 1
                    return

        # Enqueue non-blockingly
        try:
            self._queue.put_nowait(event_data)
        except asyncio.QueueFull:
            logger.warning(f"AgentEventListener queue full ({self._queue.qsize()} items). Dropping event {event_id}")
            self.stats["failures"] += 1

    # ─── Worker Processing Loop ───────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        """Continuous background worker pulling events from queue and dispatching evaluations."""
        logger.debug(f"AgentEventWorker-{worker_id} started.")
        while self._running:
            try:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                await self._process_event_with_retry(event)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in AgentEventWorker-{worker_id}: {e}", exc_info=True)
                await asyncio.sleep(0.1)

        logger.debug(f"AgentEventWorker-{worker_id} terminated.")

    async def _process_event_with_retry(self, event: dict) -> None:
        """Executes event handling with exponential backoff retry on transient errors."""
        event_id = event.get("event_id")
        event_type = event.get("event_type")

        for attempt in range(1, self.config.max_retries + 1):
            try:
                await self._dispatch_event(event)
                
                # Record successful event_id in dedup window
                if event_id:
                    async with self._processed_lock:
                        self._processed_event_ids.add(event_id)
                        self._processed_events_order.append(event_id)
                        if len(self._processed_events_order) > self.config.dedup_window_size:
                            old_id = self._processed_events_order.pop(0)
                            self._processed_event_ids.discard(old_id)
                return

            except (HTTPException, ValueError) as fatal_err:
                # Permanent clinical/data validation errors (e.g. 404 Encounter not found)
                logger.warning(
                    f"Fatal non-retryable error handling event {event_id} ({event_type}): {fatal_err}. Discarding."
                )
                self.stats["failures"] += 1
                return

            except Exception as transient_err:
                if attempt < self.config.max_retries and self._running:
                    self.stats["retries"] += 1
                    backoff = self.config.base_backoff_seconds * (self.config.backoff_multiplier ** (attempt - 1))
                    logger.warning(
                        f"Transient error handling event {event_id} (attempt {attempt}/{self.config.max_retries}): "
                        f"{transient_err}. Retrying in {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"Max retries exhausted ({self.config.max_retries}) for event {event_id} ({event_type}): {transient_err}"
                    )
                    self.stats["failures"] += 1

    # ─── Event Dispatching ────────────────────────────────────────────────────

    async def _dispatch_event(self, event: dict) -> None:
        """Dispatches an event to the appropriate multi-agent evaluation workflow."""
        event_type = event.get("event_type")
        tenant_id = event.get("tenant_id") or "HOSP-DEFAULT"
        payload = event.get("payload", {})

        if event_type == EVENT_PATIENT_INTAKE_COMPLETED:
            await self._handle_intake_completed(payload, tenant_id)
        elif event_type == EVENT_EMERGENCY_DECLARED:
            await self._handle_emergency_declared(payload, tenant_id)

    async def _handle_intake_completed(self, payload: dict, tenant_id: str) -> None:
        """Handles PATIENT_INTAKE_COMPLETED by orchestrating the associated encounter."""
        encounter_id = payload.get("encounter_id")
        if not encounter_id:
            logger.debug("PATIENT_INTAKE_COMPLETED payload has no encounter_id; skipping agent evaluation.")
            return

        # Concurrency guard: avoid evaluating the same encounter in parallel
        async with self._in_flight_lock:
            if encounter_id in self._in_flight_encounters:
                logger.debug(f"Encounter {encounter_id} is already in-flight for evaluation. Skipping duplicate.")
                self.stats["duplicates_ignored"] += 1
                return
            self._in_flight_encounters.add(encounter_id)

        try:
            async with self.session_factory() as session:
                orchestrator = MultiAgentOrchestratorService(session)
                await orchestrator.orchestrate_encounter(
                    encounter_id=encounter_id,
                    tenant_id=tenant_id,
                    trigger_reason="PATIENT_INTAKE_COMPLETED",
                    force_recalculate=False,
                    actor_id="EVENT_LISTENER"
                )
                self.stats["evaluations_triggered"] += 1
                logger.info(f"Event-driven multi-agent orchestration completed for encounter {encounter_id}")
        finally:
            async with self._in_flight_lock:
                self._in_flight_encounters.discard(encounter_id)

    async def _handle_emergency_declared(self, payload: dict, tenant_id: str) -> None:
        """
        Handles EMERGENCY_DECLARED by triggering priority evaluations for target encounter(s)
        or active encounters in affected departments.
        """
        explicit_encounter_id = payload.get("encounter_id")
        affected_departments = payload.get("affected_departments") or []

        if explicit_encounter_id:
            # Single encounter declared emergency
            target_encounters = [explicit_encounter_id]
        else:
            # Query active encounters in affected departments
            async with self.session_factory() as session:
                stmt = select(Encounter.id).where(Encounter.status == "ACTIVE")
                if affected_departments:
                    stmt = stmt.where(Encounter.current_department_id.in_(affected_departments))
                # Cap to prevent unbounded cascading load on massive departments
                stmt = stmt.limit(10)
                res = await session.execute(stmt)
                target_encounters = res.scalars().all()

        if not target_encounters:
            logger.info("EMERGENCY_DECLARED processed: zero active encounters required immediate evaluation.")
            return

        for enc_id in target_encounters:
            async with self._in_flight_lock:
                if enc_id in self._in_flight_encounters:
                    self.stats["duplicates_ignored"] += 1
                    continue
                self._in_flight_encounters.add(enc_id)

            try:
                async with self.session_factory() as session:
                    orchestrator = MultiAgentOrchestratorService(session)
                    await orchestrator.orchestrate_encounter(
                        encounter_id=enc_id,
                        tenant_id=tenant_id,
                        trigger_reason="EMERGENCY_DECLARED",
                        force_recalculate=False,
                        actor_id="EVENT_LISTENER"
                    )
                    self.stats["evaluations_triggered"] += 1
                    logger.info(f"Emergency-driven multi-agent orchestration completed for encounter {enc_id}")
            finally:
                async with self._in_flight_lock:
                    self._in_flight_encounters.discard(enc_id)


# ─── Global Singleton & Factory ───────────────────────────────────────────────

_listener_instance: Optional[AgentEventListener] = None


def get_event_listener(
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    config: Optional[EventListenerConfig] = None
) -> AgentEventListener:
    """Returns the application-wide singleton AgentEventListener instance."""
    global _listener_instance
    if _listener_instance is None:
        _listener_instance = AgentEventListener(session_factory=session_factory, config=config)
    return _listener_instance


def reset_event_listener() -> None:
    """Resets the singleton instance (primarily for isolated test fixtures)."""
    global _listener_instance
    _listener_instance = None
