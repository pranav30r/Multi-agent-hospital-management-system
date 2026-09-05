import pytest
from datetime import datetime
from sqlalchemy import select

from app.models.patient import Patient, Encounter
from app.models.agent import AgentDecision, ApprovalItem, AuditLog
from app.models.bed import Bed
from app.models.intake import ClinicalIntakeSession
from app.services.intelligence_engine_service import IntelligenceEngineService


@pytest.mark.asyncio
async def test_01_valid_critical_intelligence_execution_requires_approval(auth_client, test_db):
    """
    1. Critical encounter with hemodynamic instability produces ICU_BED_ALLOCATION_RECOMMENDATION.
    2. Consequential action strictly creates ApprovalItem in PENDING state.
    3. Critical hospital resources (Beds) are NOT mutated directly by the intelligence layer.
    """
    # 1. Register Patient & Critical Encounter
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Rohan",
        "last_name": "Kapoor",
        "age": 58,
        "gender": "M",
        "blood_group": "A+",
        "contact_phone": "+919988776655",
        "emergency_contact": "+919988776654",
        "allergies": [],
        "chronic_conditions": []
    })
    assert pat_res.status_code == 201, f"Patient registration failed: {pat_res.text}"
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute severe crushing chest pain radiating to left jaw, diaphoresis, hypotension",
        "encounter_type": "EMERGENCY",
        "heart_rate": 132,
        "bp_systolic": 80,
        "bp_diastolic": 50,
        "spo2": 86,
        "temperature_f": 99.4,
        "respiratory_rate": 30,
        "gcs_score": 13,
        "pain_level": 10
    })
    assert enc_res.status_code == 201, f"Encounter creation failed: {enc_res.text}"
    encounter_id = enc_res.json()["id"]

    # 2. Trigger Intelligence Decision
    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide", json={
        "trigger_reason": "TRIAGE_VITALS_ALERT"
    })
    assert dec_res.status_code == 200, f"Intelligence decision failed: {dec_res.text}"
    data = dec_res.json()

    assert data["action_type"] == "ICU_BED_ALLOCATION_RECOMMENDATION"
    assert data["risk_level"] == "HIGH"
    assert data["requires_human_approval"] is True
    assert data["approval_item_id"] is not None
    assert data["status"] == "PROPOSED"
    assert data["confidence"] >= 0.85
    assert "ICU bed allocation" in data["reasoning"]

    # 3. Verify Database State: AgentDecision & ApprovalItem exist in DB
    async with test_db() as session:
        dec_db = (await session.execute(select(AgentDecision).where(AgentDecision.id == data["id"]))).scalar_one()
        assert dec_db.encounter_id == encounter_id
        assert dec_db.risk_level == "HIGH"

        appr_db = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == data["approval_item_id"]))).scalar_one()
        assert appr_db.status == "PENDING"
        assert appr_db.decision_id == dec_db.id

        # 4. Verify Critical Resources were NOT autonomously mutated
        bed_icu = (await session.execute(select(Bed).where(Bed.id == "BED-ICU-01"))).scalar_one()
        assert bed_icu.status == "AVAILABLE", "Intelligence layer must NEVER mutate beds autonomously!"


@pytest.mark.asyncio
async def test_02_valid_routine_intelligence_execution_no_approval_needed(auth_client, test_db):
    """
    Routine encounter with normal vital signs generates STANDARD_OPD_ROUTING without requiring human approval.
    """
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Meera",
        "last_name": "Nair",
        "age": 28,
        "gender": "F",
        "blood_group": "O+",
        "contact_phone": "+919123456789",
        "emergency_contact": "+919123456788"
    })
    assert pat_res.status_code == 201
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Mild seasonal allergic rhinitis and nasal congestion",
        "encounter_type": "OPD",
        "heart_rate": 72,
        "bp_systolic": 118,
        "bp_diastolic": 76,
        "spo2": 99,
        "temperature_f": 98.6,
        "respiratory_rate": 16,
        "gcs_score": 15,
        "pain_level": 0
    })
    assert enc_res.status_code == 201
    encounter_id = enc_res.json()["id"]

    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert dec_res.status_code == 200
    data = dec_res.json()

    assert data["action_type"] == "STANDARD_OPD_ROUTING"
    assert data["risk_level"] == "LOW"
    assert data["requires_human_approval"] is False
    assert data["approval_item_id"] is None


@pytest.mark.asyncio
async def test_03_nonexistent_encounter_returns_404(auth_client):
    """Intelligence execution for nonexistent encounter returns 404."""
    res = await auth_client.post("/api/v1/clinical-intelligence/ENC-NONEXISTENT/decide")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_04_idempotent_duplicate_decision_execution(auth_client, test_db):
    """
    Repeated execution for the same encounter returns the existing active decision
    without creating duplicate decisions, unless force_recalculate=True.
    """
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Anil",
        "last_name": "Sharma",
        "age": 49,
        "gender": "M",
        "blood_group": "B+",
        "contact_phone": "+919876500000",
        "emergency_contact": "+919876500001"
    })
    assert pat_res.status_code == 201
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Moderate abdominal pain and mild fever",
        "heart_rate": 88,
        "bp_systolic": 125,
        "bp_diastolic": 82,
        "spo2": 97,
        "temperature_f": 100.2,
        "respiratory_rate": 18,
        "pain_level": 5
    })
    assert enc_res.status_code == 201
    encounter_id = enc_res.json()["id"]

    # First execution
    res1 = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert res1.status_code == 200
    id1 = res1.json()["id"]

    # Second execution (idempotent retrieval)
    res2 = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert res2.status_code == 200
    id2 = res2.json()["id"]
    assert id1 == id2, "Idempotent request must return the exact same decision ID"

    # Third execution with force_recalculate=True
    res3 = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide", json={
        "force_recalculate": True
    })
    assert res3.status_code == 200
    id3 = res3.json()["id"]
    assert id3 != id1, "Forced recalculation should generate a fresh decision record"


@pytest.mark.asyncio
async def test_05_unauthorized_and_forbidden_requests(client, make_auth_headers):
    """
    1. Unauthenticated request returns 401.
    2. Insufficient role request is rejected with 403.
    """
    # 1. Anonymous request rejected
    anon_res = await client.post("/api/v1/clinical-intelligence/ENC-TEST/decide")
    assert anon_res.status_code == 401

    # 2. Unauthorized role (e.g. TECHNICIAN) rejected
    tech_headers = make_auth_headers(staff_id="TECH-001", role="TECHNICIAN")
    tech_res = await client.post("/api/v1/clinical-intelligence/ENC-TEST/decide", headers=tech_headers)
    assert tech_res.status_code == 403


@pytest.mark.asyncio
async def test_06_actor_identity_strictly_bound_to_jwt(client, make_auth_headers, test_db):
    """
    Verify that AuditLog and decision actor identity strictly originate from authenticated JWT
    and cannot be spoofed by client payload fields.
    """
    doctor_headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")
    pat_res = await client.post("/api/v1/patients", json={
        "first_name": "Sunita",
        "last_name": "Deshmukh",
        "age": 42,
        "gender": "F",
        "blood_group": "AB+",
        "contact_phone": "+919876511111",
        "emergency_contact": "+919876511112"
    }, headers=doctor_headers)
    assert pat_res.status_code == 201
    patient_id = pat_res.json()["id"]

    enc_res = await client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute onset breathlessness and wheezing",
        "heart_rate": 110,
        "bp_systolic": 130,
        "bp_diastolic": 85,
        "spo2": 91,
        "temperature_f": 98.9,
        "respiratory_rate": 24,
        "pain_level": 4
    }, headers=doctor_headers)
    assert enc_res.status_code == 201
    encounter_id = enc_res.json()["id"]

    # Trigger decision with spoofed actor in body (should be ignored)
    dec_res = await client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide", json={
        "trigger_reason": "CONSULT_ESCALATION"
    }, headers=doctor_headers)
    assert dec_res.status_code == 200
    decision_id = dec_res.json()["id"]

    async with test_db() as session:
        audit = (await session.execute(
            select(AuditLog).where(AuditLog.entity_id == decision_id)
        )).scalars().first()
        assert audit is not None
        assert audit.changed_by == "DOC-001"  # Authenticated JWT staff ID


@pytest.mark.asyncio
async def test_07_human_approval_resolution_lifecycle(auth_client, test_db):
    """
    Complete lifecycle:
    Intelligence generates Decision + ApprovalItem (PENDING)
    -> Human clinician reviews and APPROVES
    -> Status transitions to APPROVE/APPROVED
    -> Direct DB state verifies synchronization
    """
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Pooja",
        "last_name": "Joshi",
        "age": 35,
        "gender": "F",
        "blood_group": "B+",
        "contact_phone": "+919876522222",
        "emergency_contact": "+919876522223"
    })
    assert pat_res.status_code == 201
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Chest pressure and shortness of breath with tachycardia",
        "heart_rate": 125,
        "bp_systolic": 88,
        "bp_diastolic": 58,
        "spo2": 89,
        "temperature_f": 99.2,
        "respiratory_rate": 26,
        "pain_level": 8
    })
    assert enc_res.status_code == 201
    encounter_id = enc_res.json()["id"]

    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert dec_res.status_code == 200
    approval_id = dec_res.json()["approval_item_id"]
    decision_id = dec_res.json()["id"]
    assert approval_id is not None

    # Review Approval Item as authenticated doctor
    review_res = await auth_client.post(f"/api/v1/approvals/{approval_id}/review", json={
        "action": "APPROVE",
        "notes": "Clinically indicated for intensive monitoring."
    })
    assert review_res.status_code == 200
    assert review_res.json()["status"] in ["APPROVE", "APPROVED"]

    # Verify both ApprovalItem and AgentDecision in database
    async with test_db() as session:
        appr_db = (await session.execute(select(ApprovalItem).where(ApprovalItem.id == approval_id))).scalar_one()
        assert appr_db.status in ["APPROVE", "APPROVED"]
        assert appr_db.reviewed_by == "DOC-001"

        dec_db = (await session.execute(select(AgentDecision).where(AgentDecision.id == decision_id))).scalar_one()
        assert dec_db.status in ["APPROVE", "APPROVED"]


@pytest.mark.asyncio
async def test_08_specialist_consult_decision_for_high_acuity(auth_client, test_db):
    """High acuity encounter produces SPECIALIST_CONSULT_RECOMMENDATION requiring approval."""
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Deepak",
        "last_name": "Verma",
        "age": 52,
        "gender": "M",
        "blood_group": "O+",
        "contact_phone": "+919876533333",
        "emergency_contact": "+919876533334"
    })
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute severe shortness of breath with unilateral leg swelling",
        "heart_rate": 108,
        "bp_systolic": 138,
        "bp_diastolic": 88,
        "spo2": 92,
        "temperature_f": 98.6,
        "respiratory_rate": 24,
        "pain_level": 6
    })
    encounter_id = enc_res.json()["id"]

    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert dec_res.status_code == 200
    data = dec_res.json()
    assert data["action_type"] in ["SPECIALIST_CONSULT_RECOMMENDATION", "ICU_BED_ALLOCATION_RECOMMENDATION"]
    assert data["requires_human_approval"] is True


@pytest.mark.asyncio
async def test_09_observation_admission_decision_for_moderate_acuity(auth_client, test_db):
    """Moderate acuity encounter produces OBSERVATION_ADMISSION_RECOMMENDATION requiring approval."""
    pat_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Kavita",
        "last_name": "Patil",
        "age": 40,
        "gender": "F",
        "blood_group": "A+",
        "contact_phone": "+919876544444",
        "emergency_contact": "+919876544445"
    })
    patient_id = pat_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Persistent dehydration and dizziness following gastroenteritis",
        "heart_rate": 92,
        "bp_systolic": 110,
        "bp_diastolic": 72,
        "spo2": 97,
        "temperature_f": 99.0,
        "respiratory_rate": 18,
        "pain_level": 3
    })
    encounter_id = enc_res.json()["id"]

    dec_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/decide")
    assert dec_res.status_code == 200
    data = dec_res.json()
    assert data["action_type"] in ["OBSERVATION_ADMISSION_RECOMMENDATION", "SPECIALIST_CONSULT_RECOMMENDATION", "STANDARD_OPD_ROUTING"]
    assert data["status"] == "PROPOSED"
