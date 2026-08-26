import asyncio
import pytest
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Bed, BedAssignment, Equipment, EquipmentBooking,
    ApprovalItem, AgentDecision, AuditLog, Patient, Encounter
)

@pytest.mark.asyncio
async def test_01_bed_double_booking_postgres(pg_db):
    """
    TEST 1 — BED DOUBLE BOOKING AGAINST POSTGRESQL
    Two independent database connections attempt concurrent reservation of the same bed.
    Verifies that SELECT ... FOR UPDATE enforces true pessimistic row-level locking.
    """
    target_bed_id = "BED-ICU-01"

    # Seed two patient records for concurrent assignments
    async with pg_db() as init_session:
        p1 = Patient(id="PAT-CONC-01", first_name="Aarav", last_name="Sharma", age=45, gender="M")
        p2 = Patient(id="PAT-CONC-02", first_name="Diya", last_name="Verma", age=38, gender="F")
        enc1 = Encounter(id="ENC-CONC-01", patient_id="PAT-CONC-01", chief_complaint="Severe Chest Pain", esi_level=1)
        enc2 = Encounter(id="ENC-CONC-02", patient_id="PAT-CONC-02", chief_complaint="Respiratory Distress", esi_level=2)
        init_session.add_all([p1, p2, enc1, enc2])
        await init_session.commit()

    async def attempt_reserve_bed(session_factory, patient_id, encounter_id, worker_name):
        async with session_factory() as session:
            try:
                async with session.begin():
                    # 1. Row Lock Target Bed
                    stmt = select(Bed).where(Bed.id == target_bed_id).with_for_update()
                    res = await session.execute(stmt)
                    bed = res.scalar_one_or_none()

                    if not bed:
                        return {"status": "FAILED", "reason": "BED_NOT_FOUND", "worker": worker_name}

                    # 2. Check Availability
                    if bed.status != "AVAILABLE":
                        return {"status": "REJECTED", "reason": f"BED_{bed.status}", "worker": worker_name}

                    # Simulate brief processing under lock
                    await asyncio.sleep(0.05)

                    # 3. Reserve Resource
                    bed.status = "RESERVED"
                    bed.current_patient_id = patient_id
                    bed.current_encounter_id = encounter_id

                    assignment = BedAssignment(
                        bed_id=target_bed_id,
                        patient_id=patient_id,
                        encounter_id=encounter_id,
                        assigned_by=worker_name,
                        status="RESERVED"
                    )
                    session.add(assignment)

                return {"status": "SUCCESS", "worker": worker_name, "patient": patient_id}
            except Exception as e:
                return {"status": "ERROR", "error": str(e), "worker": worker_name}

    # Execute two genuinely concurrent transaction tasks on separate connections
    results = await asyncio.gather(
        attempt_reserve_bed(pg_db, "PAT-CONC-01", "ENC-CONC-01", "Worker-A"),
        attempt_reserve_bed(pg_db, "PAT-CONC-02", "ENC-CONC-02", "Worker-B")
    )

    successes = [r for r in results if r["status"] == "SUCCESS"]
    rejections = [r for r in results if r["status"] == "REJECTED"]

    # Concurrency Invariant: Exactly ONE succeeds, exactly ONE is rejected
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(rejections) == 1, f"Expected 1 rejection, got {len(rejections)}: {results}"
    assert rejections[0]["reason"] == "BED_RESERVED"

    # Direct PostgreSQL Database Verification
    async with pg_db() as verify_session:
        # Check bed state
        bed_res = await verify_session.execute(select(Bed).where(Bed.id == target_bed_id))
        final_bed = bed_res.scalar_one()
        assert final_bed.status == "RESERVED"
        assert final_bed.current_patient_id == successes[0]["patient"]

        # Check assignment count
        count_res = await verify_session.execute(
            select(func.count(BedAssignment.id)).where(BedAssignment.bed_id == target_bed_id)
        )
        total_assignments = count_res.scalar()
        assert total_assignments == 1, "Double booking detected in PostgreSQL!"


@pytest.mark.asyncio
async def test_02_equipment_double_booking_postgres(pg_db):
    """
    TEST 2 — EQUIPMENT DOUBLE BOOKING AGAINST POSTGRESQL
    Two concurrent transactions attempt to book the same CT Scanner.
    Verifies that only ONE transaction acquires the equipment lock.
    """
    target_eq_id = "RES-CT-01"

    async with pg_db() as init_session:
        p1 = Patient(id="PAT-EQ-01", first_name="Karan", last_name="Malhotra", age=50, gender="M")
        p2 = Patient(id="PAT-EQ-02", first_name="Meera", last_name="Sen", age=42, gender="F")
        enc1 = Encounter(id="ENC-EQ-01", patient_id="PAT-EQ-01", chief_complaint="Head Trauma", esi_level=1)
        enc2 = Encounter(id="ENC-EQ-02", patient_id="PAT-EQ-02", chief_complaint="Abdominal Pain", esi_level=2)
        init_session.add_all([p1, p2, enc1, enc2])
        await init_session.commit()

    async def attempt_book_equipment(session_factory, patient_id, encounter_id, worker_name):
        async with session_factory() as session:
            try:
                async with session.begin():
                    # 1. Row Lock Equipment
                    stmt = select(Equipment).where(Equipment.id == target_eq_id).with_for_update()
                    res = await session.execute(stmt)
                    equipment = res.scalar_one_or_none()

                    if not equipment:
                        return {"status": "FAILED", "reason": "NOT_FOUND"}

                    if equipment.status != "AVAILABLE":
                        return {"status": "REJECTED", "reason": f"EQUIPMENT_{equipment.status}"}

                    await asyncio.sleep(0.05)

                    equipment.status = "IN_USE"
                    equipment.current_patient_id = patient_id
                    equipment.current_encounter_id = encounter_id

                    booking = EquipmentBooking(
                        equipment_id=target_eq_id,
                        encounter_id=encounter_id,
                        patient_id=patient_id,
                        requested_by=worker_name,
                        status="IN_USE"
                    )
                    session.add(booking)

                return {"status": "SUCCESS", "worker": worker_name, "patient": patient_id}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}

    results = await asyncio.gather(
        attempt_book_equipment(pg_db, "PAT-EQ-01", "ENC-EQ-01", "Task-1"),
        attempt_book_equipment(pg_db, "PAT-EQ-02", "ENC-EQ-02", "Task-2")
    )

    successes = [r for r in results if r["status"] == "SUCCESS"]
    rejections = [r for r in results if r["status"] == "REJECTED"]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(rejections) == 1, f"Expected 1 rejection, got {len(rejections)}: {results}"
    assert rejections[0]["reason"] == "EQUIPMENT_IN_USE"

    # PostgreSQL Direct Validation
    async with pg_db() as verify_session:
        eq_res = await verify_session.execute(select(Equipment).where(Equipment.id == target_eq_id))
        final_eq = eq_res.scalar_one()
        assert final_eq.status == "IN_USE"

        bookings_count = await verify_session.execute(
            select(func.count(EquipmentBooking.id)).where(EquipmentBooking.equipment_id == target_eq_id)
        )
        assert bookings_count.scalar() == 1


@pytest.mark.asyncio
async def test_03_approval_double_execution_postgres(pg_db):
    """
    TEST 3 — APPROVAL DOUBLE EXECUTION AGAINST POSTGRESQL
    Two concurrent transactions attempt to execute the same human approval item.
    Verifies that the item cannot be approved twice.
    """
    target_app_id = "APP-PG-CONCUR-01"

    async with pg_db() as init_session:
        decision = AgentDecision(
            id="DEC-PG-01",
            agent_id="AGENT-TRIAGE-01",
            action_type="BED_TRANSFER",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient condition deteriorating",
            status="PROPOSED"
        )
        item = ApprovalItem(
            id=target_app_id,
            decision_id="DEC-PG-01",
            agent_id="AGENT-TRIAGE-01",
            action_type="BED_TRANSFER",
            risk_level="HIGH",
            proposed_payload={"bed_id": "BED-ICU-02"},
            status="PENDING"
        )
        init_session.add_all([decision, item])
        await init_session.commit()

    async def attempt_review_approval(session_factory, reviewer_id, action):
        async with session_factory() as session:
            try:
                async with session.begin():
                    stmt = select(ApprovalItem).where(ApprovalItem.id == target_app_id).with_for_update()
                    res = await session.execute(stmt)
                    approval = res.scalar_one_or_none()

                    if not approval or approval.status != "PENDING":
                        return {"status": "REJECTED", "reason": "ALREADY_REVIEWED", "reviewer": reviewer_id}

                    await asyncio.sleep(0.05)

                    approval.status = "APPROVED" if action == "APPROVE" else "REJECTED"
                    approval.reviewed_by = reviewer_id
                    approval.reviewed_at = datetime.utcnow()

                return {"status": "SUCCESS", "reviewer": reviewer_id}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}

    results = await asyncio.gather(
        attempt_review_approval(pg_db, "DOC-001", "APPROVE"),
        attempt_review_approval(pg_db, "DOC-002", "APPROVE")
    )

    successes = [r for r in results if r["status"] == "SUCCESS"]
    rejections = [r for r in results if r["status"] == "REJECTED"]

    assert len(successes) == 1
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "ALREADY_REVIEWED"

    async with pg_db() as verify_session:
        app_res = await verify_session.execute(select(ApprovalItem).where(ApprovalItem.id == target_app_id))
        final_app = app_res.scalar_one()
        assert final_app.status == "APPROVED"
        assert final_app.reviewed_by == successes[0]["reviewer"]


@pytest.mark.asyncio
async def test_04_transaction_rollback_postgres(pg_db):
    """
    TEST 4 — TRANSACTION ROLLBACK INTEGRITY AGAINST POSTGRESQL
    Forces an unhandled exception before commit and verifies PostgreSQL atomic rollback.
    """
    target_bed_id = "BED-WA-01"

    # Confirm initial state is AVAILABLE
    async with pg_db() as check_session:
        b_init = (await check_session.execute(select(Bed).where(Bed.id == target_bed_id))).scalar_one()
        assert b_init.status == "AVAILABLE"

    # Attempt mutation that raises exception before commit
    with pytest.raises(RuntimeError):
        async with pg_db() as session:
            async with session.begin():
                b = (await session.execute(
                    select(Bed).where(Bed.id == target_bed_id).with_for_update()
                )).scalar_one()
                
                # Mutate state in memory/transaction
                b.status = "OCCUPIED"
                b.current_patient_id = "PAT-ROLLBACK"
                
                session.add(BedAssignment(
                    bed_id=target_bed_id,
                    patient_id="PAT-ROLLBACK",
                    encounter_id="ENC-ROLLBACK",
                    assigned_by="TEST-AGENT",
                    status="OCCUPIED"
                ))
                
                session.add(AuditLog(
                    entity_type="bed",
                    entity_id=target_bed_id,
                    field_changed="status",
                    old_value="AVAILABLE",
                    new_value="OCCUPIED",
                    changed_by="TEST-AGENT"
                ))

                # Force infrastructure failure before commit
                raise RuntimeError("Simulated network/DB crash before commit")

    # PostgreSQL Database Validation after Rollback
    async with pg_db() as verify_session:
        b_final = (await verify_session.execute(select(Bed).where(Bed.id == target_bed_id))).scalar_one()
        assert b_final.status == "AVAILABLE", "Rollback failed: Bed status was not reverted!"
        assert b_final.current_patient_id is None

        # Verify no orphan assignment or audit log was committed
        asgn_count = (await verify_session.execute(
            select(func.count(BedAssignment.id)).where(BedAssignment.bed_id == target_bed_id)
        )).scalar()
        assert asgn_count == 0, "Rollback failed: Orphan bed assignment was persisted!"

        audit_count = (await verify_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.entity_id == target_bed_id)
        )).scalar()
        assert audit_count == 0, "Rollback failed: Orphan audit log was persisted!"
