import pytest
from fastapi import HTTPException
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService


@pytest.mark.asyncio
async def test_patient_encounter_intake_full_integration(test_db):
    """Test end-to-end integration across Patient, Encounter, Clinical Intake, and Doctor View."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        intk_service = ClinicalIntakeService(session)

        # 1. Register Patient
        patient = await p_service.register_patient(
            first_name="Kavita",
            last_name="Iyer",
            age=52,
            gender="F",
            blood_group="O+",
            contact_phone="+919876543501",
            emergency_contact="+919876543502",
            actor_id="REC-001",
            actor_role="RECEPTIONIST",
            allergies=["Penicillin"],
            chronic_conditions=["Type 2 Diabetes"]
        )

        # 2. Create Intake Encounter
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Severe right lower quadrant abdominal pain",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=98,
            bp_systolic=135,
            bp_diastolic=88,
            spo2=98,
            temperature_f=100.4,
            pain_level=8
        )

        # 3. Reject intake creation when encounter belongs to a different patient
        other_patient = await p_service.register_patient(
            first_name="Other",
            last_name="Patient",
            age=30,
            gender="M",
            blood_group="A+",
            contact_phone="+919876543599",
            emergency_contact="+919876543598",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        with pytest.raises(HTTPException) as exc_mismatch:
            await intk_service.start_intake_session(
                patient_id=other_patient.id,
                encounter_id=encounter.id,
                actor_id="REC-001"
            )
        assert exc_mismatch.value.status_code == 400
        assert "does not belong to patient" in exc_mismatch.value.detail

        # 4. Start valid intake session linked to patient and encounter
        intake = await intk_service.start_intake_session(
            patient_id=patient.id,
            encounter_id=encounter.id,
            language="en",
            interaction_mode="TEXT",
            chief_complaint_raw="Severe stomach pain with nausea since morning",
            actor_id="REC-001"
        )
        assert intake.patient_id == patient.id
        assert intake.encounter_id == encounter.id
        assert intake.status == "IN_PROGRESS"

        # 5. Answer all required questions
        # Q1: Chief Complaint
        q1 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q1.id,
            raw_response="Severe stomach pain with nausea since morning"
        )

        # Q2: Symptoms
        q2 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q2.id,
            raw_response="Sharp abdominal pain, low-grade fever, nausea"
        )

        # Q3: Pain Presence (Yes)
        q3 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q3.id,
            raw_response="Yes"
        )

        # Q4 (Conditional Location): Submit location
        q4 = await intk_service.get_current_question(intake.id)
        assert q4.category == "LOCATION"
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q4.id,
            raw_response="Right lower abdomen"
        )

        # Q5 (Conditional Severity Scale): Submit score 8
        q5 = await intk_service.get_current_question(intake.id)
        assert q5.category == "SEVERITY"
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q5.id,
            raw_response="8"
        )

        # Q6: Duration
        q6 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q6.id,
            raw_response="6 hours"
        )

        # Q7-Q9: Optional questions -> skip/submit
        q7 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q7.id,
            raw_response="Metformin 500mg daily"
        )

        q8 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q8.id,
            raw_response="Penicillin"
        )

        q9 = await intk_service.get_current_question(intake.id)
        await intk_service.submit_response(
            session_id=intake.id,
            question_id=q9.id,
            raw_response="Type 2 Diabetes diagnosed 4 years ago"
        )

        # Save question id string before commit
        q1_id = q1.id

        # 6. Complete Intake Session
        completed_intake = await intk_service.complete_intake_session(intake.id, actor_id="PATIENT")
        assert completed_intake.status == "COMPLETED"
        assert completed_intake.completion_percentage == 100.0
        assert completed_intake.structured_summary["pain"]["score"] == 8
        assert completed_intake.structured_summary["pain"]["location"] == "Right lower abdomen"

        # 7. Reject response submission to completed intake
        with pytest.raises(HTTPException) as exc_mod:
            await intk_service.submit_response(
                session_id=intake.id,
                question_id=q1_id,
                raw_response="Trying to alter answer"
            )
        assert exc_mod.value.status_code == 400
        assert "Cannot submit response to an already COMPLETED" in exc_mod.value.detail

        # 8. Fetch Intake by Encounter ID
        enc_intake = await intk_service.get_intake_by_encounter(encounter.id)
        assert enc_intake is not None
        assert enc_intake.id == intake.id

        # 9. Doctor Consolidated Pre-Consultation View
        doctor_view = await intk_service.get_doctor_clinical_view(encounter.id)
        assert doctor_view["doctor_ready"] is True
        assert doctor_view["intake_status"] == "COMPLETED"
        assert doctor_view["patient"]["name"] == "Kavita Iyer"
        assert doctor_view["current_encounter"]["vitals"]["heart_rate"] == 98
        assert doctor_view["current_encounter"]["vitals"]["pain_level"] == 8
        assert doctor_view["clinical_intake"]["structured_summary"]["pain"]["location"] == "Right lower abdomen"

        # 10. Patient Medical Timeline
        timeline = await intk_service.get_patient_timeline(patient.id)
        assert len(timeline) >= 2
        event_types = [e["event_type"] for e in timeline]
        assert "ENCOUNTER_ARRIVED" in event_types
        assert "INTAKE_STARTED" in event_types
        assert "INTAKE_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_doctor_view_and_timeline_api(auth_client, test_db):
    """API integration test for doctor consolidated view and timeline endpoints."""
    # 1. Register patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Suresh",
        "last_name": "Menon",
        "age": 61,
        "gender": "M",
        "blood_group": "AB+",
        "contact_phone": "+919876543520",
        "emergency_contact": "+919876543521"
    })
    patient_id = p_res.json()["id"]

    # 2. Create Encounter
    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Dizziness and elevated blood pressure",
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "heart_rate": 84,
        "bp_systolic": 160,
        "bp_diastolic": 100,
        "spo2": 97
    })
    encounter_id = enc_res.json()["id"]

    # 3. Query Doctor View before intake
    doc_view_res1 = await auth_client.get(f"/api/v1/clinical-intakes/doctor-view/{encounter_id}")
    assert doc_view_res1.status_code == 200
    doc_view1 = doc_view_res1.json()
    assert doc_view1["doctor_ready"] is False
    assert doc_view1["intake_status"] == "NOT_STARTED"

    # 4. Start intake session
    intk_res = await auth_client.post("/api/v1/clinical-intakes", json={
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "language": "en",
        "interaction_mode": "TEXT",
        "chief_complaint_raw": "Severe dizziness and lightheadedness"
    })
    assert intk_res.status_code == 201

    # 5. Query timeline endpoint
    timeline_res = await auth_client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert timeline_res.status_code == 200
    timeline = timeline_res.json()
    assert len(timeline) >= 2
    assert any(ev["event_type"] == "ENCOUNTER_ARRIVED" for ev in timeline)
    assert any(ev["event_type"] == "INTAKE_STARTED" for ev in timeline)
