import pytest
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.clinical_intelligence_service import ClinicalIntelligenceService


@pytest.mark.asyncio
async def test_clinical_intelligence_pipeline_and_persistence(test_db):
    """Test full clinical intelligence analysis, persistence, and audit log generation."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        intk_service = ClinicalIntakeService(session)
        intel_service = ClinicalIntelligenceService(session)

        # 1. Register Patient
        patient = await p_service.register_patient(
            first_name="Vikram",
            last_name="Malhotra",
            age=58,
            gender="M",
            blood_group="B-",
            contact_phone="+919876543601",
            emergency_contact="+919876543602",
            actor_id="REC-001",
            actor_role="RECEPTIONIST",
            allergies=["Aspirin"],
            chronic_conditions=["CAD", "Hyperlipidemia"]
        )

        # 2. Create Encounter with high-acuity vitals
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Crushing substernal chest pain radiating to jaw",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=118,
            bp_systolic=175,
            bp_diastolic=105,
            spo2=91,
            temperature_f=99.1,
            pain_level=9,
            respiratory_rate=24,
            gcs_score=15
        )

        # 3. Start & Complete Clinical Intake
        intake = await intk_service.start_intake_session(
            patient_id=patient.id,
            encounter_id=encounter.id,
            chief_complaint_raw="Crushing chest pain since 45 minutes",
            actor_id="REC-001"
        )
        # Complete intake
        q1 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q1.id, raw_response="Crushing chest pain")
        q2 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q2.id, raw_response="Shortness of breath, diaphoresis")
        q3 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q3.id, raw_response="Yes")
        q4 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q4.id, raw_response="Center of chest")
        q5 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q5.id, raw_response="9")
        q6 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q6.id, raw_response="45 minutes")
        q7 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q7.id, raw_response="Atorvastatin 40mg")
        q8 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q8.id, raw_response="Aspirin")
        q9 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(session_id=intake.id, question_id=q9.id, raw_response="CAD")

        await intk_service.complete_intake_session(intake.id, actor_id="REC-001")

        # 4. Run Clinical Intelligence Analysis
        assessment = await intel_service.analyze_encounter(encounter.id, actor_id="DOC-001")

        assert assessment is not None
        assert assessment.encounter_id == encounter.id
        assert assessment.patient_id == patient.id
        assert assessment.severity == "HIGH"
        assert assessment.requires_priority_attention is True
        assert len(assessment.red_flags) >= 2
        rf_codes = [rf["code"] for rf in assessment.red_flags]
        assert "RF_CHEST_COMPLAINT" in rf_codes
        assert "RF_SEVERE_PAIN" in rf_codes

        # 5. Fetch Severity Breakdown
        sev = await intel_service.get_severity(encounter.id)
        assert sev["severity"] == "HIGH"
        assert sev["requires_priority_attention"] is True
        assert len(sev["reasons"]) > 0

        # 6. Fetch Doctor Summary
        summary = await intel_service.get_summary(encounter.id)
        assert summary["patient_reported"]["chief_complaint"] is not None
        assert summary["derived"]["severity"] == "HIGH"
        assert summary["observed"]["vitals"]["pain_level"] == 9


@pytest.mark.asyncio
async def test_clinical_intelligence_api_endpoints(auth_client, test_db):
    """Test REST API endpoints for clinical intelligence."""
    # 1. Register Patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Radhika",
        "last_name": "Sen",
        "age": 27,
        "gender": "F",
        "blood_group": "O-",
        "contact_phone": "+919876543610",
        "emergency_contact": "+919876543611"
    })
    patient_id = p_res.json()["id"]

    # 2. Create Encounter
    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Mild seasonal allergies with sneezing",
        "encounter_type": "OUTPATIENT",
        "current_department_id": "DEP-ER",
        "heart_rate": 72,
        "bp_systolic": 116,
        "bp_diastolic": 74,
        "spo2": 99,
        "temperature_f": 98.4,
        "pain_level": 1,
        "respiratory_rate": 14,
        "gcs_score": 15
    })
    encounter_id = enc_res.json()["id"]

    # 3. GET /clinical-intelligence/{encounter_id} (auto-analyzes on demand)
    intel_res = await auth_client.get(f"/api/v1/clinical-intelligence/{encounter_id}")
    assert intel_res.status_code == 200
    intel_data = intel_res.json()
    assert intel_data["encounter_id"] == encounter_id
    assert intel_data["severity"] == "LOW"
    assert intel_data["requires_priority_attention"] is False

    # 4. POST /clinical-intelligence/{encounter_id}/analyze (re-trigger)
    analyze_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/analyze")
    assert analyze_res.status_code == 200
    assert analyze_res.json()["severity"] == "LOW"

    # 5. GET /clinical-intelligence/{encounter_id}/severity
    sev_res = await auth_client.get(f"/api/v1/clinical-intelligence/{encounter_id}/severity")
    assert sev_res.status_code == 200
    assert sev_res.json()["severity"] == "LOW"

    # 6. GET /clinical-intelligence/{encounter_id}/red-flags
    rf_res = await auth_client.get(f"/api/v1/clinical-intelligence/{encounter_id}/red-flags")
    assert rf_res.status_code == 200
    assert isinstance(rf_res.json(), list)

    # 7. GET /clinical-intelligence/{encounter_id}/summary
    sum_res = await auth_client.get(f"/api/v1/clinical-intelligence/{encounter_id}/summary")
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert "patient_reported" in sum_data
    assert "observed" in sum_data
    assert "derived" in sum_data
