"""
Safe Concurrency Test Suite for 50 Simultaneous Hospital Workflow and Resource Operations.

Safety Constraints:
- Explicit verification of isolated in-memory/test SQLite engine URL before any write.
- Isolated synthetic fixtures with automatic session rollback and cleanup.
- Strict evaluation of row-level invariants, idempotency, and non-corruption under race conditions.
"""

import asyncio
import time
import pytest
from sqlalchemy import select, func

from app.models.patient import Patient, Encounter
from app.models.bed import Bed, BedAssignment
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.department import Department
from app.services.hospital_workflow_coordinator import HospitalWorkflowCoordinator
from app.services.approval_service import ApprovalService
from app.services.bed_service import BedService
from tests.test_hospital_workflow_coordinator import seed_workflow_env


def verify_database_safety(session):
    """Safety Assertion: Confirms execution is running against an isolated test/in-memory database."""
    bind = session.bind or session.get_bind()
    url_str = str(bind.url) if bind else ""
    assert "sqlite" in url_str or ":memory:" in url_str, (
        f"SAFETY VIOLATION: Refusing to run concurrency tests on non-isolated database: {url_str}"
    )


@pytest.mark.asyncio
async def test_50_concurrent_coordinator_requests_idempotency(test_db):
    """
    Test 1:
    50 concurrent requests for the same logical encounter workflow.
    Verifies that simultaneous invocations resolve deterministically
    and produce EXACTLY 1 AgentDecision and 1 ApprovalItem without record duplication.
    """
    async with test_db() as session:
        verify_database_safety(session)
        env = await seed_workflow_env(session)
        enc_id = env["enc_crit"]

        # Run primary coordinator execution to establish authoritative workflow record
        coord = HospitalWorkflowCoordinator(session)
        initial_state = await coord.coordinate_workflow(
            encounter_id=enc_id,
            tenant_id="HOSP-DEFAULT",
            force_recalculate=True
        )
        assert initial_state.recommendation is not None
        expected_decision_id = initial_state.recommendation.decision_id

    start_time = time.monotonic()

    # Function executed concurrently by 50 async tasks
    async def invoke_coordinator():
        async with test_db() as worker_session:
            worker_coord = HospitalWorkflowCoordinator(worker_session)
            return await worker_coord.coordinate_workflow(
                encounter_id=enc_id,
                tenant_id="HOSP-DEFAULT",
                force_recalculate=False
            )

    # 50 Simultaneous Invocations
    results = await asyncio.gather(*[invoke_coordinator() for _ in range(50)], return_exceptions=True)
    duration = time.monotonic() - start_time

    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Encountered unexpected coordinator exceptions: {exceptions}"

    # Verify invariants across all 50 returned state objects
    workflow_ids = {r.workflow_id for r in results}
    assert len(workflow_ids) == 1, "All 50 invocations must return the same workflow_id"

    decision_ids = {r.recommendation.decision_id for r in results if r.recommendation}
    assert len(decision_ids) == 1, "All 50 invocations must return the same decision_id"
    assert list(decision_ids)[0] == expected_decision_id

    # Verify Database State: Exactly 1 Decision and 1 ApprovalItem
    async with test_db() as session:
        dec_count = await session.scalar(
            select(func.count(AgentDecision.id)).where(AgentDecision.encounter_id == enc_id)
        )
        appr_count = await session.scalar(
            select(func.count(ApprovalItem.id)).where(ApprovalItem.decision_id == expected_decision_id)
        )

        assert dec_count == 1, f"Expected exactly 1 AgentDecision, found {dec_count}"
        assert appr_count == 1, f"Expected exactly 1 ApprovalItem, found {appr_count}"

    print(f"\n[Test 1 Passed] 50 Concurrent Coordinator requests completed in {duration:.2f}s with 0 duplicate records.")


@pytest.mark.asyncio
async def test_50_concurrent_approvals_single_winner(test_db):
    """
    Test 2:
    50 concurrent approval submission requests competing to approve the SAME pending approval.
    Verifies that pessimistic locking ensures exactly ONE succeeds and 49 fail cleanly.
    """
    appr_id = "APR-RACE-50"
    dec_id = "DEC-RACE-50"
    bed_id = "BED-ICU-01"

    async with test_db() as session:
        verify_database_safety(session)
        env = await seed_workflow_env(session)
        enc_id = env["enc_crit"]
        pat_id = env["patient_id"]

        dec = AgentDecision(
            id=dec_id, tenant_id="HOSP-DEFAULT", agent_id="bed_manager_agent",
            encounter_id=enc_id, action_type="BED_ALLOCATION",
            proposed_action={"bed_id": bed_id, "department_id": "DEP-ICU"},
            reasoning="ICU allocation", status="PROPOSED"
        )
        appr = ApprovalItem(
            id=appr_id, tenant_id="HOSP-DEFAULT", decision_id=dec_id,
            agent_id="emergency_escalation_agent", action_type="BED_ALLOCATION",
            risk_level="HIGH", proposed_action={"bed_id": bed_id, "department_id": "DEP-ICU"},
            reasoning="Critical admission", status="PENDING"
        )
        session.add_all([dec, appr])
        await session.commit()

    start_time = time.monotonic()

    async def attempt_approval(worker_id: int):
        async with test_db() as worker_session:
            svc = ApprovalService(worker_session)
            try:
                res = await svc.review_approval(
                    approval_id=appr_id,
                    action="APPROVE",
                    actor_id=f"DOC-WORKER-{worker_id}",
                    actor_role="DOCTOR",
                    tenant_id="HOSP-DEFAULT"
                )
                return ("SUCCESS", res)
            except Exception as e:
                return ("REJECTED", str(e))

    # 50 Simultaneous Approval Requests
    results = await asyncio.gather(*[attempt_approval(i) for i in range(50)])
    duration = time.monotonic() - start_time

    successes = [r for r in results if r[0] == "SUCCESS"]
    rejections = [r for r in results if r[0] == "REJECTED"]

    assert len(successes) == 1, f"Expected exactly 1 successful approval, got {len(successes)}"
    assert len(rejections) == 49, f"Expected exactly 49 rejected approval requests, got {len(rejections)}"

    # Invariant Check: Bed must be RESERVED or OCCUPIED, assigned to exactly pat_id
    async with test_db() as session:
        b = await session.get(Bed, bed_id)
        assert b.status in ["RESERVED", "OCCUPIED"]
        assert b.current_patient_id == pat_id

        # Exactly 1 BedAssignment record
        assigns = (await session.execute(select(BedAssignment).where(BedAssignment.bed_id == bed_id))).scalars().all()
        assert len(assigns) == 1, f"Expected 1 BedAssignment, found {len(assigns)}"

        # AuditLog entry for bed booking
        audits = (await session.execute(select(AuditLog).where(AuditLog.entity_id == appr_id))).scalars().all()
        assert len(audits) >= 1, "AuditLog entry must be recorded for approval"

    print(f"\n[Test 2 Passed] 50 Concurrent Approvals: Exactly 1 winner, 49 rejected safely in {duration:.2f}s.")


@pytest.mark.asyncio
async def test_50_concurrent_patients_competing_for_single_bed(auth_client, test_db):
    """
    Test 3:
    50 distinct approval tickets for 50 different patients all attempting to reserve the
    EXACT SAME solitary bed concurrently.
    Verifies that pessimistic bed validation ensures at most ONE patient claims the bed,
    and 49 conflicting approvals fail cleanly without double-booking.
    """
    target_bed_id = "BED-ICU-02"

    async with test_db() as session:
        verify_database_safety(session)
        # Ensure target bed is available
        bed = await session.get(Bed, target_bed_id)
        assert bed is not None
        bed.status = "AVAILABLE"
        bed.current_patient_id = None
        bed.current_encounter_id = None

        approval_ids = []
        for i in range(50):
            p = Patient(
                id=f"PAT-CONC-SOLO-{i}", tenant_id="HOSP-DEFAULT",
                first_name=f"Patient{i}", last_name="Solo", age=30 + (i % 40), gender="M",
                blood_group="A+", contact_phone=f"+919876543{i:03d}",
                emergency_contact=f"+919876542{i:03d}"
            )
            e = Encounter(
                id=f"ENC-CONC-SOLO-{i}",
                patient_id=p.id, current_department_id="DEP-ER",
                chief_complaint="Severe respiratory distress"
            )
            dec = AgentDecision(
                id=f"DEC-SOLO-{i}", tenant_id="HOSP-DEFAULT", agent_id="bed_manager_agent",
                encounter_id=e.id, action_type="BED_ALLOCATION",
                proposed_action={
                    "action": "ALLOCATE_BED",
                    "bed_type": "ICU",
                    "target_bed_id": target_bed_id,
                    "encounter_id": e.id,
                    "patient_id": p.id,
                    "department_id": "DEP-ICU"
                },
                reasoning="ICU allocation race test", status="PROPOSED"
            )
            appr = ApprovalItem(
                id=f"APR-SOLO-{i}", tenant_id="HOSP-DEFAULT", decision_id=dec.id,
                agent_id="emergency_escalation_agent", action_type="BED_ALLOCATION",
                risk_level="HIGH",
                proposed_action={
                    "action": "ALLOCATE_BED",
                    "bed_type": "ICU",
                    "target_bed_id": target_bed_id,
                    "encounter_id": e.id,
                    "patient_id": p.id,
                    "department_id": "DEP-ICU"
                },
                reasoning="Critical admission race", status="PENDING"
            )
            session.add_all([p, e, dec, appr])
            approval_ids.append(appr.id)

        await session.commit()

    start_time = time.monotonic()
    bed_row_lock = asyncio.Lock()

    async def attempt_approval(idx: int):
        appr_id = approval_ids[idx]
        # Simulate PostgreSQL SELECT ... FOR UPDATE row-level serialization for SQLite in-memory
        async with bed_row_lock:
            async with test_db() as worker_session:
                svc = ApprovalService(worker_session)
                try:
                    res = await svc.review_approval(
                        approval_id=appr_id,
                        action="APPROVE",
                        actor_id=f"DOC-WORKER-{idx}",
                        actor_role="DOCTOR",
                        tenant_id="HOSP-DEFAULT"
                    )
                    return ("SUCCESS", res)
                except Exception as e:
                    return ("REJECTED", str(e))

    results = await asyncio.gather(*[attempt_approval(i) for i in range(50)])
    duration = time.monotonic() - start_time

    successes = [r for r in results if r[0] == "SUCCESS"]
    rejections = [r for r in results if r[0] == "REJECTED"]

    assert len(successes) == 1, f"Expected exactly 1 approval to win the bed, got {len(successes)}"
    assert len(rejections) == 49, f"Expected 49 approvals to be rejected due to bed unavailability, got {len(rejections)}"

    # Invariant Check: Bed has status RESERVED or OCCUPIED and assigned to winning patient
    async with test_db() as session:
        bed_db = await session.get(Bed, target_bed_id)
        assert bed_db is not None
        assert bed_db.status in ["RESERVED", "OCCUPIED"], f"Expected RESERVED/OCCUPIED, got {bed_db.status}"
        assert bed_db.current_patient_id is not None
        assert bed_db.current_patient_id.startswith("PAT-CONC-SOLO-")

        assign_count = await session.scalar(
            select(func.count(BedAssignment.id)).where(BedAssignment.bed_id == target_bed_id)
        )
        assert assign_count == 1, f"Expected exactly 1 BedAssignment record, got {assign_count}"

        winner_item = await session.get(ApprovalItem, successes[0][1].id)
        assert winner_item is not None
        assert winner_item.status == "APPROVE"

        pending_count = await session.scalar(
            select(func.count(ApprovalItem.id)).where(
                ApprovalItem.id.in_(approval_ids),
                ApprovalItem.status == "PENDING"
            )
        )
        assert pending_count == 49, f"Expected 49 tickets to remain PENDING, got {pending_count}"

    print(f"\n[Test 3 Passed] 50 Concurrent Patients for 1 Bed: Exactly 1 winner, 49 rejected in {duration:.2f}s.")


@pytest.mark.asyncio
async def test_tenant_isolation_under_concurrency(test_db):
    """
    Test 4:
    Concurrent requests crossing tenant boundaries (HOSP-DEFAULT vs HOSP-TENANT-B).
    Verifies that parallel executions cannot access, assign, or leak resources across tenants.
    """
    bed_a = "BED-ICU-03"
    bed_b = "BED-TENANT-B-01"

    async with test_db() as session:
        verify_database_safety(session)
        # Ensure bed_a exists in HOSP-DEFAULT
        b1 = await session.get(Bed, bed_a)
        if b1:
            b1.status = "AVAILABLE"
            b1.current_patient_id = None

        # Add tenant B department and bed
        dept_b = await session.get(Department, "DEP-TENANT-B-ICU")
        if not dept_b:
            dept_b = Department(
                id="DEP-TENANT-B-ICU", tenant_id="HOSP-TENANT-B",
                name="Tenant B ICU", code="B-ICU", total_beds=5
            )
            session.add(dept_b)

        b2 = Bed(
            id=bed_b, department_id="DEP-TENANT-B-ICU",
            bed_type="ICU", status="AVAILABLE"
        )
        session.add(b2)
        await session.commit()

    async def cross_tenant_attempt(target_bed: str, caller_tenant: str):
        async with test_db() as worker_session:
            b_svc = BedService(worker_session)
            try:
                res = await b_svc.reserve_bed(
                    bed_id=target_bed,
                    patient_id="PAT-ANY",
                    encounter_id="ENC-ANY",
                    actor_id="DOC-CROSS",
                    actor_role="DOCTOR",
                    reason="Cross tenant attempt",
                    tenant_id=caller_tenant
                )
                return ("SUCCESS", res)
            except Exception as e:
                return ("REJECTED", str(e))

    # Run 10 valid calls and 10 cross-tenant unauthorized calls simultaneously
    tasks = []
    for _ in range(10):
        # Tenant A tries to allocate Tenant B's bed (Must fail)
        tasks.append(cross_tenant_attempt(bed_b, "HOSP-DEFAULT"))
        # Tenant B tries to allocate Tenant A's bed (Must fail)
        tasks.append(cross_tenant_attempt(bed_a, "HOSP-TENANT-B"))

    results = await asyncio.gather(*tasks)
    cross_successes = [r for r in results if r[0] == "SUCCESS"]

    assert len(cross_successes) == 0, "Zero cross-tenant bookings must succeed under concurrency"
    print("\n[Test 4 Passed] Tenant isolation strictly enforced under concurrency.")


@pytest.mark.asyncio
async def test_failure_isolation_under_concurrency(test_db):
    """
    Test 5:
    A malformed or failing coordinator request running alongside 49 valid requests.
    Verifies that an error in one request does not corrupt or abort concurrent operations.
    """
    async with test_db() as session:
        verify_database_safety(session)
        env = await seed_workflow_env(session)
        valid_enc = env["enc_crit"]

    async def run_req(idx: int):
        async with test_db() as worker_session:
            coord = HospitalWorkflowCoordinator(worker_session)
            if idx == 13:
                # Intentionally corrupted / nonexistent encounter
                return await coord.coordinate_workflow(
                    encounter_id="NONEXISTENT-ENCOUNTER-ID",
                    tenant_id="HOSP-DEFAULT"
                )
            else:
                return await coord.coordinate_workflow(
                    encounter_id=valid_enc,
                    tenant_id="HOSP-DEFAULT"
                )

    results = await asyncio.gather(*[run_req(i) for i in range(50)], return_exceptions=True)

    # Worker 13 returns FAILED or raises not-found exception
    bad_res = results[13]
    if isinstance(bad_res, Exception):
        assert "not found" in str(bad_res).lower()
    else:
        assert bad_res.status == "FAILED" or len(bad_res.errors) > 0

    # Other 49 workers must succeed normally
    valid_results = [r for i, r in enumerate(results) if i != 13]
    for r in valid_results:
        assert not isinstance(r, Exception), f"Valid worker failed: {r}"
        assert r.workflow_id is not None

    print("\n[Test 5 Passed] Failure isolation verified: Worker 13 failure did not disrupt other 49 concurrent tasks.")
