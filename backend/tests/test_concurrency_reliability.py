import asyncio
import os
import pytest
from sqlalchemy import select, text
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.bed import Bed, BedAssignment
from app.models.patient import Patient, Encounter
from tests.test_tenant_isolation import seed_tenant_b, create_access_token


@pytest.mark.asyncio
async def test_concurrent_bed_booking_exact_single_winner(client, make_auth_headers):
    """
    Requirement 1:
    Two concurrent requests simultaneously attempting to reserve the same bed.
    Executed via asyncio.gather. Exactly ONE succeeds (HTTP 200), the other fails (HTTP 400).
    """
    headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")

    # 1. Create Patient 1 & Encounter 1
    p1_res = await client.post("/api/v1/patients", json={
        "first_name": "Racer",
        "last_name": "One",
        "age": 42,
        "gender": "M",
        "blood_group": "A+",
        "contact_phone": "+919876543301",
        "emergency_contact": "+919876543302"
    }, headers=headers)
    assert p1_res.status_code in [200, 201]
    pat1_id = p1_res.json()["id"]

    e1_res = await client.post("/api/v1/patients/encounters", json={
        "patient_id": pat1_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Acute chest pain candidate 1"
    }, headers=headers)
    assert e1_res.status_code in [200, 201]
    enc1_id = e1_res.json()["id"]

    # 2. Create Patient 2 & Encounter 2
    p2_res = await client.post("/api/v1/patients", json={
        "first_name": "Racer",
        "last_name": "Two",
        "age": 39,
        "gender": "F",
        "blood_group": "B+",
        "contact_phone": "+919876543303",
        "emergency_contact": "+919876543304"
    }, headers=headers)
    assert p2_res.status_code in [200, 201]
    pat2_id = p2_res.json()["id"]

    e2_res = await client.post("/api/v1/patients/encounters", json={
        "patient_id": pat2_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Acute trauma candidate 2"
    }, headers=headers)
    assert e2_res.status_code in [200, 201]
    enc2_id = e2_res.json()["id"]

    target_bed_id = "BED-ICU-08"

    payload1 = {
        "bed_id": target_bed_id,
        "encounter_id": enc1_id,
        "patient_id": pat1_id,
        "reason": "Concurrent race candidate 1"
    }
    payload2 = {
        "bed_id": target_bed_id,
        "encounter_id": enc2_id,
        "patient_id": pat2_id,
        "reason": "Concurrent race candidate 2"
    }

    # Simultaneous concurrent requests via asyncio.gather
    res1, res2 = await asyncio.gather(
        client.post("/api/v1/beds/book-manual", json=payload1, headers=headers),
        client.post("/api/v1/beds/book-manual", json=payload2, headers=headers)
    )

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Expected at least one 200, got {statuses}"
    assert 400 in statuses, f"Expected at least one 400, got {statuses}"
    assert statuses.count(200) == 1, "Exactly one booking must succeed"
    assert statuses.count(400) == 1, "Conflicting concurrent booking must be rejected"


@pytest.mark.asyncio
async def test_approval_execution_atomicity_and_consistency(auth_client, test_db):
    """
    Requirement 2:
    Verify approval execution is atomic across the approval, decision, bed, encounter,
    bed assignment, and audit log.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Atomic", "last_name": "Patient", "age": 55, "gender": "M",
        "blood_group": "O+", "contact_phone": "+919811003301", "emergency_contact": "+919811003302"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Severe respiratory distress",
        "encounter_type": "EMERGENCY"
    })).json()

    target_bed = "BED-ICU-02"

    async with test_db() as session:
        b = await session.get(Bed, target_bed)
        b.status = "AVAILABLE"
        b.current_patient_id = None
        b.current_encounter_id = None

        decision = AgentDecision(
            id="DEC-ATOMIC-01",
            agent_id="BedAllocatorAgent",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Telemetry required",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-ATOMIC-01",
            decision_id="DEC-ATOMIC-01",
            tenant_id="HOSP-DEFAULT",
            agent_id="BedAllocatorAgent",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Telemetry required",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Clinician reviews and approves
    rev_res = await auth_client.post("/api/v1/approvals/APR-ATOMIC-01/review", json={
        "action": "APPROVE"
    })
    assert rev_res.status_code == 200

    # Verify all 5 entities atomically committed in database
    async with test_db() as session:
        app_db = await session.get(ApprovalItem, "APR-ATOMIC-01")
        assert app_db.status == "APPROVE"
        assert app_db.reviewed_by == "DOC-001"

        dec_db = await session.get(AgentDecision, "DEC-ATOMIC-01")
        assert dec_db.status == "APPROVE"

        bed_db = await session.get(Bed, target_bed)
        assert bed_db.status == "RESERVED"
        assert bed_db.current_patient_id == pat["id"]
        assert bed_db.current_encounter_id == enc["id"]

        enc_db = await session.get(Encounter, enc["id"])
        assert enc_db.current_bed_id == target_bed
        assert enc_db.patient_status == "BED_RESERVED"

        assigns = (await session.execute(
            select(BedAssignment).where(BedAssignment.encounter_id == enc["id"])
        )).scalars().all()
        assert len(assigns) == 1
        assert assigns[0].bed_id == target_bed
        assert assigns[0].status == "RESERVED"

        audit_entries = (await session.execute(
            select(AuditLog).where(AuditLog.entity_id.in_([target_bed, "APR-ATOMIC-01"]))
        )).scalars().all()
        assert len(audit_entries) >= 2


@pytest.mark.asyncio
async def test_approval_failure_rolls_back_atomically(auth_client, test_db):
    """
    Requirement 3:
    Verify failures roll back all related changes and leave approval and resource state consistent.
    If bed is not available, approval execution fails, transaction is rolled back,
    and approval remains PENDING with no orphan assignments or corrupted states.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Rollback", "last_name": "Test", "age": 60, "gender": "F",
        "blood_group": "B-", "contact_phone": "+919811003303", "emergency_contact": "+919811003304"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute observation required",
        "encounter_type": "EMERGENCY"
    })).json()

    target_bed = "BED-ICU-03"

    async with test_db() as session:
        # Make bed OCCUPIED so allocation will be rejected
        b = await session.get(Bed, target_bed)
        b.status = "OCCUPIED"
        b.current_patient_id = "PAT-ALREADY-THERE"

        decision = AgentDecision(
            id="DEC-FAIL-01",
            agent_id="BedAllocatorAgent",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Telemetry required",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-FAIL-01",
            decision_id="DEC-FAIL-01",
            tenant_id="HOSP-DEFAULT",
            agent_id="BedAllocatorAgent",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Telemetry required",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Attempt to approve unavailable bed
    rev_res = await auth_client.post("/api/v1/approvals/APR-FAIL-01/review", json={
        "action": "APPROVE"
    })
    assert rev_res.status_code == 400
    assert "OCCUPIED" in rev_res.json()["detail"]

    # Verify rollback: approval item remains PENDING, no assignment, no bed modification
    async with test_db() as session:
        app_db = await session.get(ApprovalItem, "APR-FAIL-01")
        assert app_db.status == "PENDING"
        assert app_db.reviewed_by is None

        dec_db = await session.get(AgentDecision, "DEC-FAIL-01")
        assert dec_db.status == "PROPOSED"

        bed_db = await session.get(Bed, target_bed)
        assert bed_db.status == "OCCUPIED"
        assert bed_db.current_patient_id == "PAT-ALREADY-THERE"

        assigns = (await session.execute(
            select(BedAssignment).where(BedAssignment.encounter_id == enc["id"])
        )).scalars().all()
        assert len(assigns) == 0


@pytest.mark.asyncio
async def test_concurrent_approval_idempotency_single_winner(auth_client, test_db):
    """
    Requirement 4 & 5:
    Check idempotency when the same approval is submitted concurrently more than once.
    Exactly ONE request succeeds (200), and the second returns 400 Bad Request.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Idempotent", "last_name": "Approval", "age": 48, "gender": "M",
        "blood_group": "AB+", "contact_phone": "+919811003305", "emergency_contact": "+919811003306"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute cardiac evaluation",
        "encounter_type": "EMERGENCY"
    })).json()

    target_bed = "BED-ICU-04"

    async with test_db() as session:
        b = await session.get(Bed, target_bed)
        b.status = "AVAILABLE"
        b.current_patient_id = None
        b.current_encounter_id = None

        decision = AgentDecision(
            id="DEC-IDEMP-01",
            agent_id="BedAllocatorAgent",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Cardiac monitoring",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-IDEMP-01",
            decision_id="DEC-IDEMP-01",
            tenant_id="HOSP-DEFAULT",
            agent_id="BedAllocatorAgent",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": target_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Cardiac monitoring",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Launch two concurrent approval review requests via asyncio.gather
    res1, res2 = await asyncio.gather(
        auth_client.post("/api/v1/approvals/APR-IDEMP-01/review", json={"action": "APPROVE"}),
        auth_client.post("/api/v1/approvals/APR-IDEMP-01/review", json={"action": "APPROVE"})
    )

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Expected one 200, got {statuses}"
    assert 400 in statuses, f"Expected one 400, got {statuses}"
    assert statuses.count(200) == 1, "Exactly one approval must succeed"
    assert statuses.count(400) == 1, "Duplicate concurrent approval must be rejected"


@pytest.mark.asyncio
async def test_sequential_approval_resubmission_rejected(auth_client, test_db):
    """
    Requirement 4 (Sequential Idempotency):
    Submitting the same approval after completion returns 400.
    """
    async with test_db() as session:
        decision = AgentDecision(
            id="DEC-SEQ-01",
            agent_id="BedAllocatorAgent",
            encounter_id=None,
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ICU-05"},
            reasoning="ICU allocation",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-SEQ-01",
            decision_id="DEC-SEQ-01",
            tenant_id="HOSP-DEFAULT",
            agent_id="BedAllocatorAgent",
            action_type="BED_ALLOCATION",
            risk_level="HIGH",
            proposed_action={"bed_id": "BED-ICU-05"},
            reasoning="ICU allocation",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # 1. First approval -> 200
    res1 = await auth_client.post("/api/v1/approvals/APR-SEQ-01/review", json={"action": "APPROVE"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "APPROVE"

    # 2. Second approval -> 400
    res2 = await auth_client.post("/api/v1/approvals/APR-SEQ-01/review", json={"action": "APPROVE"})
    assert res2.status_code == 400
    assert "already in 'APPROVE' state" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_alembic_migrations_on_disposable_database():
    """
    Requirement 7:
    Verify existing Alembic migrations apply cleanly to a disposable test database
    and do not corrupt or damage schema contracts.
    """
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        backend_dir = Path(__file__).resolve().parent.parent
        alembic_ini = backend_dir / "alembic.ini"
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path}")

        old_env = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}"
        try:
            # Run full migration sequence to head in worker thread
            await asyncio.to_thread(command.upgrade, cfg, "head")
        finally:
            if old_env is not None:
                os.environ["DATABASE_URL"] = old_env
            else:
                os.environ.pop("DATABASE_URL", None)

        # Verify tables created
        from sqlalchemy import create_engine, inspect
        sync_engine = create_engine(f"sqlite:///{tmp_path}")
        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()

        assert "beds" in tables
        assert "encounters" in tables
        assert "approval_items" in tables
        assert "audit_log" in tables
        assert "agent_decisions" in tables
        assert "bed_assignments" in tables
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
