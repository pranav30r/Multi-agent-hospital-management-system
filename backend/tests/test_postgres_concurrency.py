import asyncio
import os
import pytest
import pytest_asyncio
from typing import List
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.database import Base
from app.models.bed import Bed, BedAssignment
from app.models.department import Department
from app.models.tenant import Tenant
from app.models.patient import Patient, Encounter
from app.models.staff import Staff
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.services.bed_service import BedService
from app.services.approval_service import ApprovalService

# Target isolated disposable RAM container on port 5433
PG_HOST = os.getenv("POSTGRES_TEST_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_TEST_PORT", "5433"))
PG_USER = os.getenv("POSTGRES_TEST_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_TEST_PASSWORD", "postgrespassword")
PG_DB = os.getenv("POSTGRES_TEST_DB", "hospital_test")

PG_TEST_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"


@pytest_asyncio.fixture(scope="function")
async def pg_session_factory():
    """Provides isolated PostgreSQL engine and session factory backed by disposable tmpfs database."""
    engine = create_async_engine(
        PG_TEST_URL,
        poolclass=NullPool,
        connect_args={"server_settings": {"application_name": "concurrency_test"}}
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_01_real_postgres_50_concurrent_bed_allocations_single_winner(pg_session_factory):
    """
    Test 1: 50 simultaneous competing requests for a single available bed on real PostgreSQL.
    Each worker uses a distinct, independent database connection and session via NullPool.
    Verifies that SELECT ... FOR UPDATE pessimistic row-locking enforces exactly ONE winner.
    """
    tenant_id = "HOSP-CONCUR-01"
    dep_id = "DEP-CONCUR-01"
    bed_id = "BED-CONCUR-01"

    # 1. Seed initial entities in an isolated transaction in topological order
    async with pg_session_factory() as session:
        t = Tenant(id=tenant_id, name="Concurrency Test Hospital", code="CTH", is_active=True)
        session.add(t)
        await session.flush()

        d = Department(id=dep_id, tenant_id=tenant_id, name="Emergency Trauma", code="ER")
        session.add(d)
        await session.flush()

        s = Staff(
            id="DOC-CONCUR-01",
            tenant_id=tenant_id,
            first_name="Test",
            last_name="Doctor",
            role="DOCTOR",
            department_id=dep_id,
            status="AVAILABLE"
        )
        session.add(s)

        bed = Bed(
            id=bed_id,
            department_id=dep_id,
            bed_type="ICU",
            status="AVAILABLE"
        )
        session.add(bed)
        await session.flush()

        for i in range(1, 51):
            p = Patient(
                id=f"PAT-CONCUR-{i:02d}",
                tenant_id=tenant_id,
                first_name=f"Patient{i}",
                last_name="Race",
                age=40 + (i % 20),
                gender="M",
                blood_group="O+",
                contact_phone=f"+91987654{i:04d}",
                emergency_contact=f"+91987654{i:04d}"
            )
            session.add(p)
        await session.flush()

        for i in range(1, 51):
            enc = Encounter(
                id=f"ENC-CONCUR-{i:02d}",
                patient_id=f"PAT-CONCUR-{i:02d}",
                encounter_type="EMERGENCY",
                current_department_id=dep_id,
                chief_complaint=f"Concurrent bed contention candidate {i}"
            )
            session.add(enc)

        await session.commit()

    # 2. Worker function simulating concurrent request with distinct connection
    async def worker_attempt(idx: int):
        async with pg_session_factory() as session:
            service = BedService(session)
            return await service.reserve_bed(
                bed_id=bed_id,
                patient_id=f"PAT-CONCUR-{idx:02d}",
                encounter_id=f"ENC-CONCUR-{idx:02d}",
                actor_id="DOC-CONCUR-01",
                actor_role="DOCTOR",
                reason=f"Concurrent race worker {idx}",
                tenant_id=tenant_id
            )

    # 3. Fire 50 simultaneous competing requests
    results = await asyncio.gather(
        *(worker_attempt(i) for i in range(1, 51)),
        return_exceptions=True
    )

    # 4. Verify exactly ONE winner and 49 HTTP 400 rejections
    successes = [r for r in results if isinstance(r, Bed)]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1, f"Expected exactly 1 successful allocation, got {len(successes)}"
    assert len(failures) == 49, f"Expected exactly 49 rejected allocations, got {len(failures)}"

    for fail in failures:
        assert fail.status_code == 400
        assert "is in 'RESERVED' state and cannot be booked" in fail.detail

    # 5. Verify final PostgreSQL database state consistency
    async with pg_session_factory() as session:
        final_bed = await session.get(Bed, bed_id)
        assert final_bed.status == "RESERVED"
        winner_patient_id = final_bed.current_patient_id
        assert winner_patient_id is not None
        assert winner_patient_id.startswith("PAT-CONCUR-")

        # Exactly 1 active BedAssignment must exist
        assignments = (await session.execute(
            select(BedAssignment).where(BedAssignment.bed_id == bed_id)
        )).scalars().all()
        assert len(assignments) == 1
        assert assignments[0].patient_id == winner_patient_id
        assert assignments[0].status == "RESERVED"

        # Exactly 1 AuditLog entry for bed reservation must exist
        audits = (await session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == bed_id,
                AuditLog.entity_type == "bed",
                AuditLog.field_changed == "status"
            )
        )).scalars().all()
        assert len(audits) == 1
        assert audits[0].old_value == "AVAILABLE"
        assert audits[0].new_value == "RESERVED"


@pytest.mark.asyncio
async def test_02_real_postgres_transaction_rollback_consistency(pg_session_factory):
    """
    Test 2: Verify transactional rollback on PostgreSQL when a failure occurs mid-transaction.
    Proves that a raised exception reverts Bed status to AVAILABLE and creates zero orphan records.
    """
    tenant_id = "HOSP-CONCUR-01"
    dep_id = "DEP-CONCUR-01"
    bed_id = "BED-ROLLBACK-01"

    # 1. Seed department and bed
    async with pg_session_factory() as session:
        t = Tenant(id=tenant_id, name="Concurrency Test Hospital", code="CTH", is_active=True)
        session.add(t)
        await session.flush()

        d = Department(id=dep_id, tenant_id=tenant_id, name="Emergency Trauma", code="ER")
        session.add(d)
        await session.flush()

        bed = Bed(
            id=bed_id,
            department_id=dep_id,
            bed_type="ICU",
            status="AVAILABLE"
        )
        session.add(bed)
        await session.commit()

    # 2. Simulate transaction failure inside allocation routine
    with pytest.raises(RuntimeError, match="Simulated mid-transaction crash"):
        async with pg_session_factory() as session:
            b_query = select(Bed).where(Bed.id == bed_id).with_for_update()
            res = await session.execute(b_query)
            target_bed = res.scalars().first()
            target_bed.status = "RESERVED"

            # Create uncommitted assignment
            assignment = BedAssignment(
                bed_id=bed_id,
                encounter_id="ENC-CONCUR-01",
                patient_id="PAT-CONCUR-01",
                assigned_by="DOC-CONCUR-01",
                status="RESERVED"
            )
            session.add(assignment)

            # Simulated failure before commit triggers rollback
            raise RuntimeError("Simulated mid-transaction crash")

    # 3. Verify clean state in a new PostgreSQL transaction
    async with pg_session_factory() as session:
        reverted_bed = await session.get(Bed, bed_id)
        assert reverted_bed.status == "AVAILABLE"
        assert reverted_bed.current_patient_id is None

        assignments = (await session.execute(
            select(BedAssignment).where(BedAssignment.bed_id == bed_id)
        )).scalars().all()
        assert len(assignments) == 0


@pytest.mark.asyncio
async def test_03_real_postgres_50_concurrent_approval_reviews_single_winner(pg_session_factory):
    """
    Test 3: 50 simultaneous competing reviews on the same pending approval item on PostgreSQL.
    Verifies that row-level locking on ApprovalItem guarantees exactly ONE approval execution.
    """
    tenant_id = "HOSP-CONCUR-01"
    dep_id = "DEP-CONCUR-01"
    bed_id = "BED-CONCUR-APR"
    approval_id = "APR-CONCUR-01"
    decision_id = "DEC-CONCUR-01"

    # 1. Seed pending approval and target bed
    async with pg_session_factory() as session:
        t = Tenant(id=tenant_id, name="Concurrency Test Hospital", code="CTH", is_active=True)
        session.add(t)
        await session.flush()

        d = Department(id=dep_id, tenant_id=tenant_id, name="Emergency Trauma", code="ER")
        session.add(d)
        await session.flush()

        p = Patient(
            id="PAT-CONCUR-01",
            tenant_id=tenant_id,
            first_name="Patient1",
            last_name="Race",
            age=45,
            gender="M",
            blood_group="O+",
            contact_phone="+919876540001",
            emergency_contact="+919876540001"
        )
        session.add(p)
        await session.flush()

        enc = Encounter(
            id="ENC-CONCUR-01",
            patient_id="PAT-CONCUR-01",
            encounter_type="EMERGENCY",
            current_department_id=dep_id,
            chief_complaint="Contention approval"
        )
        session.add(enc)

        bed = Bed(
            id=bed_id,
            department_id=dep_id,
            bed_type="ICU",
            status="AVAILABLE"
        )
        session.add(bed)
        await session.flush()

        decision = AgentDecision(
            id=decision_id,
            agent_id="BedAllocatorAgent",
            encounter_id="ENC-CONCUR-01",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": bed_id,
                "encounter_id": "ENC-CONCUR-01",
                "patient_id": "PAT-CONCUR-01"
            },
            reasoning="Critical ICU contention test",
            status="PROPOSED",
            tenant_id=tenant_id
        )
        session.add(decision)
        await session.flush()

        approval = ApprovalItem(
            id=approval_id,
            decision_id=decision_id,
            tenant_id=tenant_id,
            agent_id="BedAllocatorAgent",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action=decision.proposed_action,
            reasoning="Critical ICU contention test",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # 2. Worker function attempting approval review
    async def review_attempt(idx: int):
        async with pg_session_factory() as session:
            service = ApprovalService(session)
            return await service.review_approval(
                approval_id=approval_id,
                action="APPROVE",
                actor_id=f"DOC-CONCUR-{idx:02d}",
                actor_role="DOCTOR",
                tenant_id=tenant_id
            )

    # 3. Fire 50 simultaneous competing approval reviews
    results = await asyncio.gather(
        *(review_attempt(i) for i in range(1, 51)),
        return_exceptions=True
    )

    # 4. Verify exactly ONE successful review
    successes = [r for r in results if isinstance(r, ApprovalItem)]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1, f"Expected exactly 1 successful approval, got {len(successes)}"
    assert len(failures) == 49, f"Expected exactly 49 rejected reviews, got {len(failures)}"

    for fail in failures:
        assert fail.status_code == 400
        assert "already in 'APPROVE' state" in fail.detail

    # 5. Verify PostgreSQL database state
    async with pg_session_factory() as session:
        final_app = await session.get(ApprovalItem, approval_id)
        assert final_app.status == "APPROVE"

        final_bed = await session.get(Bed, bed_id)
        assert final_bed.status == "RESERVED"


@pytest.mark.asyncio
async def test_04_repeat_concurrency_reproducibility(pg_session_factory):
    """
    Test 4: Repeat 50-worker bed concurrency on an independent bed to ensure reproducibility.
    """
    tenant_id = "HOSP-CONCUR-01"
    dep_id = "DEP-CONCUR-01"
    bed_id = "BED-CONCUR-02"

    async with pg_session_factory() as session:
        t = Tenant(id=tenant_id, name="Concurrency Test Hospital", code="CTH", is_active=True)
        session.add(t)
        await session.flush()

        d = Department(id=dep_id, tenant_id=tenant_id, name="Emergency Trauma", code="ER")
        session.add(d)
        await session.flush()

        s = Staff(
            id="DOC-CONCUR-01",
            tenant_id=tenant_id,
            first_name="Test",
            last_name="Doctor",
            role="DOCTOR",
            department_id=dep_id,
            status="AVAILABLE"
        )
        session.add(s)

        bed = Bed(
            id=bed_id,
            department_id=dep_id,
            bed_type="ICU",
            status="AVAILABLE"
        )
        session.add(bed)
        await session.flush()

        for i in range(1, 51):
            p = Patient(
                id=f"PAT-CONCUR-REP-{i:02d}",
                tenant_id=tenant_id,
                first_name=f"PatientRep{i}",
                last_name="Race",
                age=40 + (i % 20),
                gender="M",
                blood_group="O+",
                contact_phone=f"+91987655{i:04d}",
                emergency_contact=f"+91987655{i:04d}"
            )
            session.add(p)
        await session.flush()

        for i in range(1, 51):
            enc = Encounter(
                id=f"ENC-CONCUR-REP-{i:02d}",
                patient_id=f"PAT-CONCUR-REP-{i:02d}",
                encounter_type="EMERGENCY",
                current_department_id=dep_id,
                chief_complaint=f"Repeat concurrency test candidate {i}"
            )
            session.add(enc)

        await session.commit()

    async def worker_attempt(idx: int):
        async with pg_session_factory() as session:
            service = BedService(session)
            return await service.reserve_bed(
                bed_id=bed_id,
                patient_id=f"PAT-CONCUR-REP-{idx:02d}",
                encounter_id=f"ENC-CONCUR-REP-{idx:02d}",
                actor_id="DOC-CONCUR-01",
                actor_role="DOCTOR",
                reason=f"Repetition race worker {idx}",
                tenant_id=tenant_id
            )

    results = await asyncio.gather(
        *(worker_attempt(i) for i in range(1, 51)),
        return_exceptions=True
    )

    successes = [r for r in results if isinstance(r, Bed)]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1
    assert len(failures) == 49
