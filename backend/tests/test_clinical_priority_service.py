import pytest
from fastapi import HTTPException
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.clinical_priority_service import ClinicalPriorityService
from app.services.dashboard_service import DashboardService


@pytest.mark.asyncio
async def test_priority_classification_and_routing_levels(test_db):
    """Test deterministic priority levels (CRITICAL, HIGH, MODERATE, ROUTINE) and routing destinations."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        pri_service = ClinicalPriorityService(session)

        # 1. Register Patient
        patient = await p_service.register_patient(
            first_name="Sunita",
            last_name="Deshmukh",
            age=44,
            gender="F",
            blood_group="B+",
            contact_phone="+919876543801",
            emergency_contact="+919876543802",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )

        # Case A: Routine Case (Normal vitals)
        enc_routine = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Mild common cold and runny nose",
            encounter_type="OUTPATIENT",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=72,
            bp_systolic=118,
            bp_diastolic=78,
            spo2=99,
            temperature_f=98.4,
            pain_level=1,
            respiratory_rate=14,
            gcs_score=15
        )
        rec_routine = await pri_service.evaluate_priority(enc_routine.id, actor_id="DOC-001")
        assert rec_routine.priority_level == "ROUTINE"
        assert rec_routine.route == "STANDARD_OPD_QUEUE"
        assert rec_routine.requires_priority_attention is False

        # Case B: Moderate Case (Moderate pain 6/10, elevated BP)
        enc_mod = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Moderate ankle sprain with swelling",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=95,
            bp_systolic=142,
            bp_diastolic=90,
            spo2=96,
            temperature_f=98.8,
            pain_level=6,
            respiratory_rate=18,
            gcs_score=15
        )
        rec_mod = await pri_service.evaluate_priority(enc_mod.id, actor_id="DOC-001")
        assert rec_mod.priority_level == "MODERATE"
        assert rec_mod.route in ["NURSE_TRIAGE", "DEPARTMENT_REVIEW"]

        # Case C: High Case (High pain 8/10, ESI 2)
        enc_high = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Severe abdominal pain and fever",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=112,
            bp_systolic=150,
            bp_diastolic=95,
            spo2=94,
            temperature_f=102.1,
            pain_level=8,
            respiratory_rate=22,
            gcs_score=15
        )
        rec_high = await pri_service.evaluate_priority(enc_high.id, actor_id="DOC-001")
        assert rec_high.priority_level in ["HIGH", "CRITICAL"]
        assert rec_high.requires_priority_attention is True

        # Case D: Critical Case (Critical Hypoxia 88%, Shock BP 80/50)
        enc_crit = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Severe acute respiratory distress and collapse",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=142,
            bp_systolic=80,
            bp_diastolic=50,
            spo2=86,
            temperature_f=103.8,
            pain_level=9,
            respiratory_rate=32,
            gcs_score=10
        )
        rec_crit = await pri_service.evaluate_priority(enc_crit.id, actor_id="DOC-001")
        assert rec_crit.priority_level == "CRITICAL"
        assert rec_crit.route == "EMERGENCY_TRIAGE"
        assert rec_crit.requires_priority_attention is True
        assert len(rec_crit.red_flags) >= 2


@pytest.mark.asyncio
async def test_priority_acknowledgement_and_override_workflow(test_db):
    """Test human-in-the-loop acknowledgement and manual physician override."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        pri_service = ClinicalPriorityService(session)

        # 1. Register Patient & Encounter
        patient = await p_service.register_patient(
            first_name="Ajay",
            last_name="Pandey",
            age=50,
            gender="M",
            blood_group="AB+",
            contact_phone="+919876543820",
            emergency_contact="+919876543821",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Mild dizziness",
            encounter_type="OUTPATIENT",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=78,
            bp_systolic=122,
            bp_diastolic=80,
            spo2=98,
            pain_level=2
        )

        # 2. Evaluate Priority -> ROUTINE
        rec = await pri_service.evaluate_priority(encounter.id, actor_id="SYS")
        assert rec.status == "GENERATED"
        assert rec.priority_level == "ROUTINE"

        # 3. Acknowledge recommendation
        ack_rec = await pri_service.acknowledge_recommendation(
            encounter_id=encounter.id,
            actor_id="NURSE-001",
            notes="Acknowledged routine priority by triage nurse."
        )
        assert ack_rec.status == "ACKNOWLEDGED"
        assert ack_rec.acknowledged_by == "NURSE-001"

        # 4. Physician Override
        # Test rejection of empty override reason
        with pytest.raises(HTTPException) as exc_empty:
            await pri_service.override_recommendation(
                encounter_id=encounter.id,
                actor_id="DOC-001",
                override_priority="HIGH",
                override_route="IMMEDIATE_DOCTOR_REVIEW",
                override_reason=""
            )
        assert exc_empty.value.status_code == 400

        # Valid override
        overridden = await pri_service.override_recommendation(
            encounter_id=encounter.id,
            actor_id="DOC-001",
            override_priority="HIGH",
            override_route="IMMEDIATE_DOCTOR_REVIEW",
            override_reason="Patient history of TIA with acute recurrence suspicion."
        )
        assert overridden.status == "OVERRIDDEN"
        assert overridden.override_priority_level == "HIGH"
        assert overridden.override_route == "IMMEDIATE_DOCTOR_REVIEW"
        assert overridden.overridden_by == "DOC-001"


@pytest.mark.asyncio
async def test_priority_integration_with_timeline_doctor_view_dashboard(test_db):
    """Test full integration of priority decisions with patient timeline, doctor view, and dashboard metrics."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        intk_service = ClinicalIntakeService(session)
        pri_service = ClinicalPriorityService(session)
        dash_service = DashboardService(session)

        # 1. Register Patient & Encounter
        patient = await p_service.register_patient(
            first_name="Deepa",
            last_name="Rao",
            age=36,
            gender="F",
            blood_group="O-",
            contact_phone="+919876543840",
            emergency_contact="+919876543841",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Severe migraine with vomiting",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=98,
            bp_systolic=138,
            bp_diastolic=88,
            spo2=98,
            pain_level=7
        )

        # 2. Evaluate Priority & Acknowledge
        await pri_service.evaluate_priority(encounter.id, actor_id="DOC-001")
        await pri_service.acknowledge_recommendation(encounter.id, actor_id="DOC-001", notes="Verified priority")

        # 3. Verify Doctor Clinical View contains clinical priority
        doc_view = await intk_service.get_doctor_clinical_view(encounter.id)
        assert "clinical_priority" in doc_view
        assert doc_view["clinical_priority"] is not None
        assert doc_view["clinical_priority"]["priority_level"] in ["MODERATE", "HIGH"]
        assert doc_view["clinical_priority"]["status"] == "ACKNOWLEDGED"

        # 4. Verify Patient Timeline contains Priority events
        timeline = await intk_service.get_patient_timeline(patient.id)
        event_types = [e["event_type"] for e in timeline]
        assert "PRIORITY_ASSESSMENT_GENERATED" in event_types
        assert "PRIORITY_ACKNOWLEDGED" in event_types

        # 5. Verify Dashboard Telemetry aggregation
        state = await dash_service.get_hospital_state()
        assert "clinical_priorities" in state
        assert state["clinical_priorities"]["total"] >= 1


@pytest.mark.asyncio
async def test_clinical_priority_api(auth_client, test_db):
    """Test clinical priority REST API endpoints."""
    # 1. Register Patient & Encounter
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Manish",
        "last_name": "Tiwari",
        "age": 41,
        "gender": "M",
        "blood_group": "A+",
        "contact_phone": "+919876543860",
        "emergency_contact": "+919876543861"
    })
    patient_id = p_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute lower back spasm",
        "encounter_type": "OUTPATIENT",
        "current_department_id": "DEP-ER",
        "heart_rate": 82,
        "bp_systolic": 128,
        "bp_diastolic": 82,
        "spo2": 98,
        "pain_level": 5
    })
    encounter_id = enc_res.json()["id"]

    # 2. POST /clinical-priority/{encounter_id}/evaluate
    eval_res = await auth_client.post(f"/api/v1/clinical-priority/{encounter_id}/evaluate")
    assert eval_res.status_code == 200
    rec_data = eval_res.json()
    assert rec_data["encounter_id"] == encounter_id
    assert rec_data["priority_level"] in ["MODERATE", "ROUTINE", "HIGH"]
    assert rec_data["status"] == "GENERATED"

    # 3. GET /clinical-priority/{encounter_id}/recommendation
    get_res = await auth_client.get(f"/api/v1/clinical-priority/{encounter_id}/recommendation")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == rec_data["id"]

    # 4. POST /clinical-priority/{encounter_id}/acknowledge
    ack_res = await auth_client.post(f"/api/v1/clinical-priority/{encounter_id}/acknowledge", json={
        "notes": "Acknowledged by duty officer"
    })
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 5. POST /clinical-priority/{encounter_id}/override
    ovr_res = await auth_client.post(f"/api/v1/clinical-priority/{encounter_id}/override", json={
        "override_priority": "HIGH",
        "override_route": "IMMEDIATE_DOCTOR_REVIEW",
        "override_reason": "Severe muscle spasm preventing ambulation"
    })
    assert ovr_res.status_code == 200
    assert ovr_res.json()["status"] == "OVERRIDDEN"
    assert ovr_res.json()["override_priority_level"] == "HIGH"
