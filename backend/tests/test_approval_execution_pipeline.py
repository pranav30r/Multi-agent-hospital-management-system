import pytest
from sqlalchemy import select
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.bed import Bed, BedAssignment
from app.models.patient import Patient, Encounter
from tests.test_tenant_isolation import seed_tenant_b, create_access_token


@pytest.mark.asyncio
async def test_approval_execution_reserves_bed_and_updates_encounter(auth_client, test_db):
    """
    Test 1: Full end-to-end execution of approved AI bed allocation.
    Verifies that APPROVE transitions the approval, reserves the bed, and updates the encounter.
    """
    # 1. Create Patient & Encounter
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Rohan", "last_name": "Mehta", "age": 45, "gender": "M",
        "blood_group": "B+", "contact_phone": "+919811002201", "emergency_contact": "+919811002202"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Severe respiratory failure, requires ICU telemetry",
        "encounter_type": "EMERGENCY"
    })).json()

    bed_id = "BED-ICU-04"

    # Ensure bed is available
    async with test_db() as session:
        b = await session.get(Bed, bed_id)
        b.status = "AVAILABLE"
        b.current_patient_id = None
        b.current_encounter_id = None
        await session.commit()

    # 2. Create Agent Decision & Approval Item
    async with test_db() as session:
        decision = AgentDecision(
            id="DEC-EXEC-01",
            agent_id="MultiAgentCoordinator",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Critical respiratory status requires ICU telemetry",
            confidence=0.95,
            risk_level="HIGH",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-EXEC-01",
            decision_id="DEC-EXEC-01",
            tenant_id="HOSP-DEFAULT",
            agent_id="MultiAgentCoordinator",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="Critical respiratory status requires ICU telemetry",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # 3. Doctor reviews and APPROVES
    rev_res = await auth_client.post("/api/v1/approvals/APR-EXEC-01/review", json={
        "action": "APPROVE"
    })
    assert rev_res.status_code == 200, f"Approval failed: {rev_res.text}"
    appr_data = rev_res.json()
    assert appr_data["status"] == "APPROVE"

    # 4. Verify database state for all affected entities
    async with test_db() as session:
        # Approval record
        app_db = await session.get(ApprovalItem, "APR-EXEC-01")
        assert app_db.status == "APPROVE"
        assert app_db.reviewed_by == "DOC-001"

        # Linked decision
        dec_db = await session.get(AgentDecision, "DEC-EXEC-01")
        assert dec_db.status == "APPROVE"

        # Physical Bed state
        bed_db = await session.get(Bed, bed_id)
        assert bed_db.status == "RESERVED"
        assert bed_db.current_patient_id == pat["id"]
        assert bed_db.current_encounter_id == enc["id"]

        # Encounter state
        enc_db = await session.get(Encounter, enc["id"])
        assert enc_db.current_bed_id == bed_id
        assert enc_db.patient_status == "BED_RESERVED"

        # Bed assignment record
        assigns = (await session.execute(
            select(BedAssignment).where(BedAssignment.encounter_id == enc["id"])
        )).scalars().all()
        assert len(assigns) == 1
        assert assigns[0].bed_id == bed_id
        assert assigns[0].assigned_by == "DOC-001"
        assert assigns[0].is_manual_override is False

        # Audit logs for both approval and bed
        audit_bed = (await session.execute(
            select(AuditLog).where(AuditLog.entity_type == "bed", AuditLog.entity_id == bed_id)
        )).scalars().all()
        assert len(audit_bed) >= 1
        assert audit_bed[-1].new_value == "RESERVED"


@pytest.mark.asyncio
async def test_approval_rejection_leaves_resources_unmutated(auth_client, test_db):
    """
    Test 2: Rejection must never mutate physical beds or encounter state.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Sonia", "last_name": "Iyer", "age": 34, "gender": "F",
        "blood_group": "A-", "contact_phone": "+919811002203", "emergency_contact": "+919811002204"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Mild palpitations",
        "encounter_type": "EMERGENCY"
    })).json()

    bed_id = "BED-ICU-05"

    async with test_db() as session:
        b = await session.get(Bed, bed_id)
        b.status = "AVAILABLE"
        b.current_patient_id = None
        b.current_encounter_id = None

        decision = AgentDecision(
            id="DEC-EXEC-02",
            agent_id="MultiAgentCoordinator",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-EXEC-02",
            decision_id="DEC-EXEC-02",
            tenant_id="HOSP-DEFAULT",
            agent_id="MultiAgentCoordinator",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Doctor REJECTS recommendation
    rev_res = await auth_client.post("/api/v1/approvals/APR-EXEC-02/review", json={
        "action": "REJECT",
        "rejection_reason": "Patient is stable; regular telemetry sufficient"
    })
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REJECT"

    # Verify zero physical resource mutation
    async with test_db() as session:
        bed_db = await session.get(Bed, bed_id)
        assert bed_db.status == "AVAILABLE"
        assert bed_db.current_patient_id is None

        enc_db = await session.get(Encounter, enc["id"])
        assert enc_db.current_bed_id is None

        assigns = (await session.execute(
            select(BedAssignment).where(BedAssignment.encounter_id == enc["id"])
        )).scalars().all()
        assert len(assigns) == 0


@pytest.mark.asyncio
async def test_approval_fails_closed_when_target_bed_is_stale_or_occupied(auth_client, test_db):
    """
    Test 3: Stale bed handling and transactional rollback.
    If the target bed becomes OCCUPIED before clinician approval, review fails with 400
    and the approval item remains in PENDING state.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Arun", "last_name": "Verma", "age": 58, "gender": "M",
        "blood_group": "AB+", "contact_phone": "+919811002205", "emergency_contact": "+919811002206"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Acute stroke alert",
        "encounter_type": "EMERGENCY"
    })).json()

    bed_id = "BED-ICU-06"

    # Make bed OCCUPIED by another patient
    async with test_db() as session:
        b = await session.get(Bed, bed_id)
        b.status = "OCCUPIED"
        b.current_patient_id = "PAT-OTHER"
        b.current_encounter_id = "ENC-OTHER"

        decision = AgentDecision(
            id="DEC-EXEC-03",
            agent_id="MultiAgentCoordinator",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-EXEC-03",
            decision_id="DEC-EXEC-03",
            tenant_id="HOSP-DEFAULT",
            agent_id="MultiAgentCoordinator",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": bed_id,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Attempt to APPROVE -> Must fail with 400
    rev_res = await auth_client.post("/api/v1/approvals/APR-EXEC-03/review", json={
        "action": "APPROVE"
    })
    assert rev_res.status_code == 400
    assert "OCCUPIED" in rev_res.json()["detail"]

    # Verify Approval Item was NOT marked executed
    async with test_db() as session:
        app_db = await session.get(ApprovalItem, "APR-EXEC-03")
        assert app_db.status == "PENDING"
        assert app_db.reviewed_by is None


@pytest.mark.asyncio
async def test_approval_modification_executes_overridden_bed(auth_client, test_db):
    """
    Test 4: Clinician MODIFY overrides target bed and executes the modified assignment.
    """
    pat = (await auth_client.post("/api/v1/patients", json={
        "first_name": "Maya", "last_name": "Nair", "age": 41, "gender": "F",
        "blood_group": "O-", "contact_phone": "+919811002207", "emergency_contact": "+919811002208"
    })).json()

    enc = (await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": pat["id"],
        "chief_complaint": "Chest discomfort",
        "encounter_type": "EMERGENCY"
    })).json()

    original_bed = "BED-ICU-07"
    overridden_bed = "BED-WA-01"

    async with test_db() as session:
        b_orig = await session.get(Bed, original_bed)
        b_orig.status = "AVAILABLE"
        b_over = await session.get(Bed, overridden_bed)
        b_over.status = "AVAILABLE"

        decision = AgentDecision(
            id="DEC-EXEC-04",
            agent_id="MultiAgentCoordinator",
            encounter_id=enc["id"],
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": original_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU-07",
            status="PROPOSED",
            tenant_id="HOSP-DEFAULT"
        )
        session.add(decision)

        approval = ApprovalItem(
            id="APR-EXEC-04",
            decision_id="DEC-EXEC-04",
            tenant_id="HOSP-DEFAULT",
            agent_id="MultiAgentCoordinator",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": original_bed,
                "encounter_id": enc["id"],
                "patient_id": pat["id"]
            },
            reasoning="AI recommends ICU-07",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Clinician modifies recommendation to Ward Bed WA-01
    rev_res = await auth_client.post("/api/v1/approvals/APR-EXEC-04/review", json={
        "action": "MODIFY",
        "modification": {"target_bed_id": overridden_bed}
    })
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "MODIFY"

    # Verify overridden bed was reserved, original bed was untouched
    async with test_db() as session:
        b_orig_db = await session.get(Bed, original_bed)
        assert b_orig_db.status == "AVAILABLE"

        b_over_db = await session.get(Bed, overridden_bed)
        assert b_over_db.status == "RESERVED"
        assert b_over_db.current_patient_id == pat["id"]

        enc_db = await session.get(Encounter, enc["id"])
        assert enc_db.current_bed_id == overridden_bed

        assigns = (await session.execute(
            select(BedAssignment).where(BedAssignment.encounter_id == enc["id"])
        )).scalars().all()
        assert len(assigns) == 1
        assert assigns[0].bed_id == overridden_bed
        assert assigns[0].is_manual_override is True


@pytest.mark.asyncio
async def test_cross_tenant_approval_execution_blocked(client, test_db):
    """
    Test 5: Cross-tenant execution is strictly blocked with HTTP 404.
    """
    await seed_tenant_b(test_db)

    # Approval item in Tenant A
    async with test_db() as session:
        approval = ApprovalItem(
            id="APR-EXEC-TENANT-A",
            decision_id="DEC-EXEC-TENANT-A",
            tenant_id="HOSP-DEFAULT",
            agent_id="MultiAgentCoordinator",
            action_type="ICU_BED_ALLOCATION_RECOMMENDATION",
            risk_level="HIGH",
            proposed_action={
                "action": "ALLOCATE_BED",
                "target_bed_id": "BED-ICU-08",
                "encounter_id": "ENC-001",
                "patient_id": "PAT-001"
            },
            reasoning="Tenant A action",
            status="PENDING"
        )
        session.add(approval)
        await session.commit()

    # Tenant B doctor tries to review Tenant A approval
    token_b = create_access_token({
        "sub": "DOC-RIVAL-01",
        "role": "DOCTOR",
        "name": "Dr. Rival",
        "department_id": "DEP-RIVAL",
        "tenant_id": "HOSP-RIVAL"
    })
    headers_b = {"Authorization": f"Bearer {token_b}"}

    rev_res = await client.post(
        "/api/v1/approvals/APR-EXEC-TENANT-A/review",
        headers=headers_b,
        json={"action": "APPROVE"}
    )
    assert rev_res.status_code == 404

    # Ensure Approval remains PENDING
    async with test_db() as session:
        app_db = await session.get(ApprovalItem, "APR-EXEC-TENANT-A")
        assert app_db.status == "PENDING"
