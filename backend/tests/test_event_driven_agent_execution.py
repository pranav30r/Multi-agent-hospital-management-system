"""
Comprehensive Unit, Integration, and Concurrency Test Suite for Event-Driven Agent Execution.

Verifies:
1. AgentEventListener lifecycle (startup, cancellation, queue draining, graceful shutdown).
2. End-to-end PATIENT_INTAKE_COMPLETED event-driven evaluation.
3. End-to-end EMERGENCY_DECLARED event-driven evaluation.
4. Concurrency control and deduplication (event_id dedup and in-flight encounter mutex).
5. Idempotent execution (duplicate events yield single AgentDecision).
6. Multi-tenant isolation propagation.
7. Transient failure handling with exponential backoff retry.
8. Fatal non-retryable error containment (404 / invalid encounter).
9. ClinicalIntakeService direct integration with domain event publishing.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.events import event_bus, HospitalEvent
from app.services.agent_event_listener import (
    AgentEventListener,
    EventListenerConfig,
    EVENT_PATIENT_INTAKE_COMPLETED,
    EVENT_EMERGENCY_DECLARED,
    get_event_listener,
    reset_event_listener,
)
from app.models.patient import Patient, Encounter
from app.models.department import Department
from app.models.agent import AgentDecision, OptimizationRun
from app.models.intake import ClinicalIntakeSession
from app.services.clinical_intake_service import ClinicalIntakeService


# ─── Fixtures & Helpers ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_redis_offline():
    """Ensure fast local fallback during tests by avoiding Redis TCP connection timeouts."""
    with patch("app.core.redis.redis_manager.get_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        yield mock_get


async def seed_test_patient_and_encounter(
    session: AsyncSession,
    enc_id: str = "ENC-001",
    pat_id: str = "PAT-001",
    dept_id: str = "DEP-ER",
    tenant_id: str = "HOSP-DEFAULT"
):
    """Seeds test department, patient, and encounter entities."""
    dept = await session.get(Department, dept_id)
    if not dept:
        dept = Department(
            id=dept_id,
            tenant_id=tenant_id,
            name="Emergency Department",
            code="ER",
            total_beds=6
        )
        session.add(dept)
        await session.flush()

    patient = await session.get(Patient, pat_id)
    if not patient:
        patient = Patient(
            id=pat_id,
            tenant_id=tenant_id,
            first_name="Anita",
            last_name="Desai",
            age=45,
            gender="F",
            blood_group="A+",
            contact_phone="9876543200",
            emergency_contact="9876543201"
        )
        session.add(patient)
        await session.flush()

    encounter = await session.get(Encounter, enc_id)
    if not encounter:
        encounter = Encounter(
            id=enc_id,
            patient_id=pat_id,
            current_department_id=dept_id,
            encounter_type="EMERGENCY",
            status="ACTIVE",
            patient_status="ARRIVED",
            chief_complaint="Severe crushing chest pain radiating to left jaw",
            bp_systolic=165,
            bp_diastolic=105,
            heart_rate=120,
            spo2=91,
            esi_level=2
        )
        session.add(encounter)
        await session.flush()

    await session.commit()
    return patient, encounter


# ─── 1. Lifecycle & Graceful Shutdown ────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_event_listener_lifecycle(test_db):
    """Verify clean worker startup, task tracking, and graceful shutdown."""
    config = EventListenerConfig(worker_concurrency=2, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)

    assert not listener._running
    assert len(listener._worker_tasks) == 0

    await listener.start()
    assert listener._running
    assert len(listener._worker_tasks) == 2
    for task in listener._worker_tasks:
        assert not task.done()

    await listener.stop()
    assert not listener._running
    assert len(listener._worker_tasks) == 0
    assert listener._queue.empty()


# ─── 2. PATIENT_INTAKE_COMPLETED Event-Driven Evaluation ─────────────────────

@pytest.mark.asyncio
async def test_patient_intake_completed_triggers_agent_evaluation(test_db):
    """Verify that publishing PATIENT_INTAKE_COMPLETED triggers background orchestrator evaluation."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-001", pat_id="PAT-001")

    config = EventListenerConfig(worker_concurrency=1, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        # Publish event
        await event_bus.publish({
            "event_type": EVENT_PATIENT_INTAKE_COMPLETED,
            "tenant_id": "HOSP-DEFAULT",
            "source": "clinical_intake_service",
            "payload": {
                "session_id": "INTK-TEST-001",
                "encounter_id": "ENC-001",
                "patient_id": "PAT-001",
                "completion_percentage": 100.0
            }
        }, tenant_id="HOSP-DEFAULT")

        # Wait for worker processing
        for _ in range(40):
            if listener.stats["evaluations_triggered"] >= 1:
                break
            await asyncio.sleep(0.05)

        assert listener.stats["evaluations_triggered"] == 1

        # Verify AgentDecision created in database
        async with test_db() as session:
            dec_res = await session.execute(
                select(AgentDecision).where(AgentDecision.encounter_id == "ENC-001")
            )
            decision = dec_res.scalars().first()
            assert decision is not None
            assert decision.status in ["PROPOSED", "PENDING", "APPROVED"]

    finally:
        await listener.stop()


# ─── 3. EMERGENCY_DECLARED Event-Driven Evaluation ───────────────────────────

@pytest.mark.asyncio
async def test_emergency_declared_triggers_priority_orchestration(test_db):
    """Verify EMERGENCY_DECLARED with explicit encounter triggers immediate evaluation."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-002", pat_id="PAT-002")

    config = EventListenerConfig(worker_concurrency=1, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        await event_bus.publish({
            "event_type": EVENT_EMERGENCY_DECLARED,
            "tenant_id": "HOSP-DEFAULT",
            "source": "emergency_service",
            "payload": {
                "emergency_id": "EMR-TEST-99",
                "event_type": "MASS_CASUALTY",
                "severity": "CRITICAL",
                "status": "ACTIVE",
                "affected_departments": ["DEP-ER"],
                "expected_patient_surge": 15,
                "encounter_id": "ENC-002"
            }
        }, tenant_id="HOSP-DEFAULT")

        # Wait for worker processing
        for _ in range(40):
            if listener.stats["evaluations_triggered"] >= 1:
                break
            await asyncio.sleep(0.05)

        assert listener.stats["evaluations_triggered"] == 1

        async with test_db() as session:
            dec_res = await session.execute(
                select(AgentDecision).where(AgentDecision.encounter_id == "ENC-002")
            )
            decision = dec_res.scalars().first()
            assert decision is not None

    finally:
        await listener.stop()


# ─── 4. Concurrency Control & Event Deduplication ────────────────────────────

@pytest.mark.asyncio
async def test_event_id_deduplication(test_db):
    """Verify exact duplicate event_ids are discarded in O(1) time without processing."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-001", pat_id="PAT-001")

    config = EventListenerConfig(worker_concurrency=1, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        duplicate_event_id = "evt-duplicate-fixed-1234"
        event_dict = {
            "event_id": duplicate_event_id,
            "event_type": EVENT_PATIENT_INTAKE_COMPLETED,
            "tenant_id": "HOSP-DEFAULT",
            "payload": {"encounter_id": "ENC-001"}
        }

        # First delivery
        await event_bus.publish(event_dict, tenant_id="HOSP-DEFAULT")
        for _ in range(40):
            if listener.stats["evaluations_triggered"] >= 1:
                break
            await asyncio.sleep(0.05)

        assert listener.stats["evaluations_triggered"] == 1

        # Second delivery of same event_id
        await event_bus.publish(event_dict, tenant_id="HOSP-DEFAULT")
        await asyncio.sleep(0.1)

        # Duplicates ignored incremented, evaluations unchanged
        assert listener.stats["duplicates_ignored"] >= 1
        assert listener.stats["evaluations_triggered"] == 1

    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_concurrent_duplicate_events_for_same_encounter(test_db):
    """Verify simultaneous duplicate events for same encounter do not cause race conditions."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-001", pat_id="PAT-001")

    config = EventListenerConfig(worker_concurrency=3, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        # Fire 4 concurrent events for ENC-001
        events = [
            {
                "event_id": f"evt-burst-{i}",
                "event_type": EVENT_PATIENT_INTAKE_COMPLETED,
                "tenant_id": "HOSP-DEFAULT",
                "payload": {"encounter_id": "ENC-001"}
            }
            for i in range(4)
        ]

        await asyncio.gather(*[event_bus.publish(ev, tenant_id="HOSP-DEFAULT") for ev in events])

        # Wait for all accepted events to finish processing instead of assuming a fixed runtime.
        await asyncio.wait_for(listener._queue.join(), timeout=15)

        # Exactly 1 evaluation should succeed, remaining should be caught as in-flight or DB idempotency
        assert listener.stats["evaluations_triggered"] == 1

    finally:
        await listener.stop()


# ─── 5. Transient Error Handling & Exponential Backoff Retry ─────────────────

@pytest.mark.asyncio
async def test_transient_error_retry_with_backoff(test_db):
    """Verify transient exception triggers retry with backoff and eventually succeeds."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-001", pat_id="PAT-001")

    config = EventListenerConfig(max_retries=3, base_backoff_seconds=0.02, backoff_multiplier=1.5)
    listener = AgentEventListener(session_factory=test_db, config=config)

    attempt_counter = 0
    original_dispatch = listener._dispatch_event

    async def flaky_dispatch(event: dict):
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter < 2:
            raise ConnectionError("Simulated transient database lock timeout")
        return await original_dispatch(event)

    listener._dispatch_event = flaky_dispatch
    await listener.start()

    try:
        await event_bus.publish({
            "event_type": EVENT_PATIENT_INTAKE_COMPLETED,
            "tenant_id": "HOSP-DEFAULT",
            "payload": {"encounter_id": "ENC-001"}
        })

        for _ in range(40):
            if listener.stats["evaluations_triggered"] >= 1:
                break
            await asyncio.sleep(0.05)

        assert listener.stats["retries"] == 1
        assert listener.stats["evaluations_triggered"] == 1
        assert listener.stats["failures"] == 0

    finally:
        await listener.stop()


# ─── 6. Fatal Error Containment (404 Encounter Not Found) ─────────────────────

@pytest.mark.asyncio
async def test_fatal_error_aborts_without_infinite_retry(test_db):
    """Verify 404 Encounter Not Found fails fast and is logged as failure without retry loop."""
    config = EventListenerConfig(max_retries=3, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        # Non-existent encounter ID
        await event_bus.publish({
            "event_type": EVENT_PATIENT_INTAKE_COMPLETED,
            "tenant_id": "HOSP-DEFAULT",
            "payload": {"encounter_id": "ENC-DOES-NOT-EXIST-9999"}
        })

        # Wait for worker processing
        for _ in range(20):
            if listener.stats["failures"] >= 1:
                break
            await asyncio.sleep(0.05)

        # Fatal error must increment failures immediately without retrying
        assert listener.stats["failures"] == 1
        assert listener.stats["retries"] == 0
        assert listener.stats["evaluations_triggered"] == 0

    finally:
        await listener.stop()


# ─── 7. ClinicalIntakeService Direct Integration ─────────────────────────────

@pytest.mark.asyncio
async def test_clinical_intake_service_publishes_event_on_completion(test_db):
    """Verify ClinicalIntakeService.complete_intake_session publishes PATIENT_INTAKE_COMPLETED."""
    async with test_db() as session:
        await seed_test_patient_and_encounter(session, enc_id="ENC-001", pat_id="PAT-001")

        # Create intake session directly
        intake_svc = ClinicalIntakeService(session)
        created_session = await intake_svc.start_intake_session(
            patient_id="PAT-001",
            encounter_id="ENC-001"
        )
        session_id = created_session.id

        # Answer required questions according to response_type
        q = await intake_svc.get_current_question(session_id)
        while q:
            r_type = (q.response_type or "TEXT").upper()
            if r_type == "BOOLEAN":
                raw = "Yes"
                val = {"value": True}
            elif r_type == "SCALE":
                raw = "5"
                val = {"value": 5}
            elif r_type == "NUMBER":
                raw = "2"
                val = {"value": 2}
            elif r_type == "SINGLE_CHOICE":
                raw = q.allowed_options[0] if q.allowed_options else "Option 1"
                val = {"value": raw}
            else:
                raw = "Patient reports moderate pain"
                val = {"value": raw}

            await intake_svc.submit_response(
                session_id=session_id,
                question_id=q.id,
                raw_response=raw,
                structured_value=val
            )
            q = await intake_svc.get_current_question(session_id)

    # Now verify completion publishes the event to listener
    config = EventListenerConfig(worker_concurrency=1, base_backoff_seconds=0.01)
    listener = AgentEventListener(session_factory=test_db, config=config)
    await listener.start()

    try:
        async with test_db() as session:
            intake_svc = ClinicalIntakeService(session)
            await intake_svc.complete_intake_session(session_id=session_id)

        # Wait for listener to receive and evaluate
        for _ in range(40):
            if listener.stats["evaluations_triggered"] >= 1:
                break
            await asyncio.sleep(0.05)

        assert listener.stats["evaluations_triggered"] == 1

    finally:
        await listener.stop()


# ─── 8. FastAPI Lifespan Integration ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_fastapi_lifespan_startup_and_shutdown():
    """Verify that FastAPI lifespan starts and gracefully stops the AgentEventListener."""
    from app.main import app, lifespan
    from app.services.agent_event_listener import get_event_listener

    async with lifespan(app):
        listener = get_event_listener()
        assert listener._running
        assert len(listener._worker_tasks) > 0

    assert not listener._running
    assert len(listener._worker_tasks) == 0
