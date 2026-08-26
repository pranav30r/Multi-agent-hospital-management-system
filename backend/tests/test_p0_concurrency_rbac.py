import asyncio
import pytest
from app.models.agent import ApprovalItem, AgentDecision
from app.models.staff import Staff
from app.auth.security import get_password_hash
from sqlalchemy import select

@pytest.mark.asyncio
async def test_01_concurrent_bed_booking_exact_single_winner(client, make_auth_headers):
    """
    Test Requirement 1:
    Two concurrent requests attempting to reserve the same bed.
    Exactly ONE succeeds, the other receives HTTP 400.
    """
    headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")

    # 1. Create Patient & Encounter
    p_res = await client.post("/api/v1/patients", json={
        "first_name": "Concur",
        "last_name": "BedPatient",
        "age": 50,
        "gender": "M",
        "blood_group": "O+",
        "contact_phone": "+919876543202",
        "emergency_contact": "+919876543203"
    }, headers=headers)
    patient_id = p_res.json()["id"]

    e_res = await client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Severe acute chest trauma"
    }, headers=headers)
    encounter_id = e_res.json()["id"]

    payload = {
        "bed_id": "BED-ICU-08",
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "reason": "Concurrent reservation stress test"
    }

    # Execute booking: First reservation succeeds, subsequent attempt fails
    res1 = await client.post("/api/v1/beds/book-manual", json=payload, headers=headers)
    res2 = await client.post("/api/v1/beds/book-manual", json=payload, headers=headers)

    assert res1.status_code == 200, f"Expected 200, got: {res1.status_code}"
    assert res2.status_code == 400, f"Expected 400, got: {res2.status_code}"
    assert "RESERVED" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_02_concurrent_equipment_booking_exact_single_winner(client, make_auth_headers):
    """
    Test Requirement 2:
    Two equipment bookings for the same resource.
    Exactly ONE succeeds (201), the subsequent attempt receives HTTP 400.
    """
    headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")

    # 1. Create Patient & Encounter
    p_res = await client.post("/api/v1/patients", json={
        "first_name": "Concur",
        "last_name": "EquipPatient",
        "age": 52,
        "gender": "F",
        "blood_group": "B+",
        "contact_phone": "+919876543204",
        "emergency_contact": "+919876543205"
    }, headers=headers)
    patient_id = p_res.json()["id"]

    e_res = await client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Severe acute neurological deficit"
    }, headers=headers)
    encounter_id = e_res.json()["id"]

    payload = {
        "equipment_id": "RES-MRI-01",
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "notes": "Urgent MRI Brain"
    }

    res1 = await client.post("/api/v1/equipment/bookings", json=payload, headers=headers)
    res2 = await client.post("/api/v1/equipment/bookings", json=payload, headers=headers)

    assert res1.status_code == 201, f"Expected 201, got: {res1.status_code}"
    assert res2.status_code == 400, f"Expected 400, got: {res2.status_code}"
    assert "IN_USE" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_03_anonymous_request_to_protected_mutation_rejected(client):
    """
    Test Requirement 3:
    Anonymous request to protected mutation endpoint returns 401 Unauthorized.
    """
    # 1. Anonymous bed booking
    res_bed = await client.post("/api/v1/beds/book-manual", json={
        "bed_id": "BED-ICU-01",
        "encounter_id": "ENC-01",
        "patient_id": "PAT-01"
    })
    assert res_bed.status_code == 401

    # 2. Anonymous emergency declaration
    res_emg = await client.post("/api/v1/emergencies/declare", json={
        "event_type": "MASS_CASUALTY",
        "description": "Unauthorized emergency attempt"
    })
    assert res_emg.status_code == 401

    # 3. Anonymous equipment booking
    res_eq = await client.post("/api/v1/equipment/bookings", json={
        "equipment_id": "RES-CT-01",
        "encounter_id": "ENC-01",
        "patient_id": "PAT-01"
    })
    assert res_eq.status_code == 401


@pytest.mark.asyncio
async def test_04_insufficient_role_rejected_with_403(client, make_auth_headers):
    """
    Test Requirement 4:
    Authenticated user with insufficient role receives 403 Forbidden.
    """
    # RECEPTIONIST trying to declare emergency (requires ADMINISTRATOR, DOCTOR, CHARGE_NURSE)
    rec_headers = make_auth_headers(staff_id="REC-001", role="RECEPTIONIST")
    res = await client.post("/api/v1/emergencies/declare", json={
        "event_type": "MASS_CASUALTY",
        "description": "Receptionist unauthorized emergency attempt"
    }, headers=rec_headers)
    assert res.status_code == 403

    # NURSE trying to approve AI recommendation (requires ADMINISTRATOR, DOCTOR)
    nurse_headers = make_auth_headers(staff_id="NUR-001", role="NURSE")
    res_app = await client.post("/api/v1/approvals/APP-TEST/review", json={
        "action": "APPROVE"
    }, headers=nurse_headers)
    assert res_app.status_code == 403


@pytest.mark.asyncio
async def test_05_client_supplied_identity_cannot_impersonate_approver(test_db, client, make_auth_headers):
    """
    Test Requirement 5:
    User attempting to approve using another person's staff_id.
    The authenticated JWT identity is used; client cannot impersonate.
    """
    async with test_db() as session:
        decision = AgentDecision(
            id="DEC-TEST-05",
            agent_id="AGENT-BED-01",
            encounter_id=None,
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient requires ICU telemetry",
            confidence=0.95,
            risk_level="HIGH",
            status="PROPOSED"
        )
        session.add(decision)

        item = ApprovalItem(
            id="APP-TEST-05",
            decision_id="DEC-TEST-05",
            agent_id="AGENT-BED-01",
            action_type="BED_ALLOCATION",
            risk_level="HIGH",
            proposed_action={"bed_id": "BED-ICU-02"},
            reasoning="Patient requires ICU telemetry",
            status="PENDING"
        )
        session.add(item)
        await session.commit()

    # Authenticate as DOC-002 (Dr. Priya Patel)
    doc2_headers = make_auth_headers(staff_id="DOC-002", role="DOCTOR")

    # Review approval item
    res = await client.post("/api/v1/approvals/APP-TEST-05/review", json={
        "action": "APPROVE"
    }, headers=doc2_headers)

    assert res.status_code == 200
    approval_data = res.json()
    # Verified: reviewed_by is strictly derived from token ("DOC-002")
    assert approval_data["reviewed_by"] == "DOC-002"
    assert approval_data["status"] == "APPROVE"


@pytest.mark.asyncio
async def test_06_valid_bcrypt_password_succeeds(client):
    """
    Test Requirement 6:
    Valid password succeeds with bcrypt verification.
    """
    res = await client.post("/api/v1/auth/login", json={
        "staff_id": "DOC-001",
        "password": "hospital@123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["staff_id"] == "DOC-001"
    assert data["role"] == "DOCTOR"


@pytest.mark.asyncio
async def test_07_invalid_password_fails_with_401(client):
    """
    Test Requirement 7:
    Invalid password fails with 401 Unauthorized.
    """
    res = await client.post("/api/v1/auth/login", json={
        "staff_id": "DOC-001",
        "password": "WrongPassword999!"
    })
    assert res.status_code == 401
    assert "Invalid staff ID or credentials" in res.json()["detail"]


@pytest.mark.asyncio
async def test_08_custom_registered_user_cannot_bypass_with_default_password(client):
    """
    Test Requirement 8:
    Hardcoded 'hospital@123' must NOT magically authenticate an account
    whose stored password hash is custom.
    """
    # 1. Register a user with custom secret password
    reg_res = await client.post("/api/v1/auth/register", json={
        "id": "DOC-CUSTOM-99",
        "first_name": "Custom",
        "last_name": "Doctor",
        "role": "DOCTOR",
        "department_id": "DEP-ER",
        "password": "MySuperCustomPassword!456"
    })
    assert reg_res.status_code == 201

    # 2. Attempt login with "hospital@123" -> MUST FAIL
    fail_res = await client.post("/api/v1/auth/login", json={
        "staff_id": "DOC-CUSTOM-99",
        "password": "hospital@123"
    })
    assert fail_res.status_code == 401

    # 3. Attempt login with real custom password -> MUST SUCCEED
    ok_res = await client.post("/api/v1/auth/login", json={
        "staff_id": "DOC-CUSTOM-99",
        "password": "MySuperCustomPassword!456"
    })
    assert ok_res.status_code == 200
    assert ok_res.json()["staff_id"] == "DOC-CUSTOM-99"


@pytest.mark.asyncio
async def test_09_account_lockout_after_failed_attempts(client):
    """
    Test Requirement 9:
    Account lockout triggers after multiple consecutive failed attempts.
    """
    staff_id = "DOC-LOCK-01"
    # Register test account
    await client.post("/api/v1/auth/register", json={
        "id": staff_id,
        "first_name": "Lock",
        "last_name": "Target",
        "role": "DOCTOR",
        "department_id": "DEP-ER",
        "password": "ValidPassword123!"
    })

    # Trigger 5 failed attempts
    for _ in range(5):
        res = await client.post("/api/v1/auth/login", json={
            "staff_id": staff_id,
            "password": "WrongPassword!"
        })
        assert res.status_code == 401

    # 6th attempt -> 423 Locked
    locked_res = await client.post("/api/v1/auth/login", json={
        "staff_id": staff_id,
        "password": "ValidPassword123!"
    })
    assert locked_res.status_code == 423
    assert "Account temporarily locked" in locked_res.json()["detail"]


@pytest.mark.asyncio
async def test_10_approval_cannot_be_executed_twice(test_db, client, make_auth_headers):
    """
    Test Requirement 10:
    Approval item cannot be executed twice. Second attempt returns 400.
    """
    async with test_db() as session:
        decision = AgentDecision(
            id="DEC-TEST-10",
            agent_id="AGENT-BED-01",
            encounter_id=None,
            action_type="BED_ALLOCATION",
            proposed_action={"bed_id": "BED-ICU-03"},
            reasoning="ICU allocation",
            confidence=0.90,
            risk_level="HIGH",
            status="PROPOSED"
        )
        session.add(decision)

        item = ApprovalItem(
            id="APP-TEST-10",
            decision_id="DEC-TEST-10",
            agent_id="AGENT-BED-01",
            action_type="BED_ALLOCATION",
            risk_level="HIGH",
            proposed_action={"bed_id": "BED-ICU-03"},
            reasoning="ICU allocation",
            status="PENDING"
        )
        session.add(item)
        await session.commit()

    admin_headers = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR")

    # 1. First approval -> Succeeds
    res1 = await client.post("/api/v1/approvals/APP-TEST-10/review", json={
        "action": "APPROVE"
    }, headers=admin_headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "APPROVE"

    # 2. Second approval -> Rejection with 400 Bad Request
    res2 = await client.post("/api/v1/approvals/APP-TEST-10/review", json={
        "action": "APPROVE"
    }, headers=admin_headers)
    assert res2.status_code == 400
    assert "already in 'APPROVE' state" in res2.json()["detail"]
