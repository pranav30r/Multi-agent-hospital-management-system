import pytest
from fastapi import HTTPException
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService


@pytest.mark.asyncio
async def test_intake_session_lifecycle(test_db):
    """Test ClinicalIntakeService session creation, retrieval, and validation."""
    async with test_db() as session:
        p_service = PatientService(session)
        intake_service = ClinicalIntakeService(session)

        # 1. Register a test patient
        patient = await p_service.register_patient(
            first_name="Meera",
            last_name="Nair",
            age=34,
            gender="F",
            blood_group="B+",
            contact_phone="+919876543401",
            emergency_contact="+919876543402",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )

        # 2. Reject intake start for non-existent patient
        with pytest.raises(HTTPException) as exc_p:
            await intake_service.start_intake_session(patient_id="PAT-NON-EXISTENT-999")
        assert exc_p.value.status_code == 404
        assert "not found" in exc_p.value.detail

        # 3. Start valid intake session
        intake_session = await intake_service.start_intake_session(
            patient_id=patient.id,
            language="en",
            interaction_mode="TEXT",
            chief_complaint_raw="Persistent headache and fatigue",
            actor_id="REC-001"
        )
        assert intake_session.id.startswith("INTK-")
        assert intake_session.status == "IN_PROGRESS"
        assert intake_session.total_questions >= 7
        assert intake_session.completion_percentage == 0.0

        # 4. Fetch session
        fetched = await intake_service.get_intake_session(intake_session.id)
        assert fetched is not None
        assert fetched.patient_id == patient.id
        assert len(fetched.questions) >= 7

        # 5. List patient intake sessions
        history = await intake_service.list_patient_intakes(patient.id)
        assert len(history) >= 1
        assert history[0].id == intake_session.id


@pytest.mark.asyncio
async def test_intake_question_sequencing_and_conditional_branching(test_db):
    """Test sequential question retrieval, conditional branching, and response validation."""
    async with test_db() as session:
        p_service = PatientService(session)
        intake_service = ClinicalIntakeService(session)

        patient = await p_service.register_patient(
            first_name="Rohan",
            last_name="Gupta",
            age=29,
            gender="M",
            blood_group="O+",
            contact_phone="+919876543410",
            emergency_contact="+919876543411",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )

        intake = await intake_service.start_intake_session(
            patient_id=patient.id,
            actor_id="REC-001"
        )

        # 1. Q1: Chief Complaint (Required, TEXT)
        q1 = await intake_service.get_current_question(intake.id)
        assert q1 is not None
        assert q1.category == "CHIEF_COMPLAINT"
        assert q1.order_index == 1

        # Submit Q1
        resp1 = await intake_service.submit_response(
            session_id=intake.id,
            question_id=q1.id,
            raw_response="Severe ankle pain after running",
            actor_id="PATIENT"
        )
        assert resp1.raw_response == "Severe ankle pain after running"

        # 2. Reject duplicate submission to Q1
        with pytest.raises(HTTPException) as exc_dup:
            await intake_service.submit_response(
                session_id=intake.id,
                question_id=q1.id,
                raw_response="Duplicate answer",
                actor_id="PATIENT"
            )
        assert exc_dup.value.status_code == 400
        assert "already been answered" in exc_dup.value.detail

        # 3. Q2: Symptoms (Required, TEXT)
        q2 = await intake_service.get_current_question(intake.id)
        assert q2.category == "SYMPTOMS"
        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q2.id,
            raw_response="Swelling and redness around left ankle",
            actor_id="PATIENT"
        )

        # 4. Q3: Pain Presence (Required, BOOLEAN)
        q3 = await intake_service.get_current_question(intake.id)
        assert q3.category == "PAIN_PRESENCE"
        assert q3.response_type == "BOOLEAN"

        # Test invalid boolean rejection
        with pytest.raises(HTTPException) as exc_bool:
            await intake_service.submit_response(
                session_id=intake.id,
                question_id=q3.id,
                raw_response="Maybe a little",
                actor_id="PATIENT"
            )
        assert exc_bool.value.status_code == 400
        assert "Boolean response" in exc_bool.value.detail

        # Submit valid Yes
        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q3.id,
            raw_response="Yes",
            actor_id="PATIENT"
        )

        # 5. Q4 (Conditional): Location should now be active
        q4 = await intake_service.get_current_question(intake.id)
        assert q4 is not None
        assert q4.category == "LOCATION"

        # Submit location
        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q4.id,
            raw_response="Left ankle joint",
            actor_id="PATIENT"
        )

        # 6. Q5 (Conditional): Pain Severity Scale (1-10)
        q5 = await intake_service.get_current_question(intake.id)
        assert q5.category == "SEVERITY"
        assert q5.response_type == "SCALE"

        # Test scale out-of-bounds rejection
        with pytest.raises(HTTPException) as exc_scale:
            await intake_service.submit_response(
                session_id=intake.id,
                question_id=q5.id,
                raw_response="15",
                actor_id="PATIENT"
            )
        assert exc_scale.value.status_code == 400
        assert "Scale response must be an integer" in exc_scale.value.detail

        # Submit valid scale
        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q5.id,
            raw_response="7",
            actor_id="PATIENT"
        )

        # 7. Q6: Duration (Required, TEXT)
        q6 = await intake_service.get_current_question(intake.id)
        assert q6.category == "DURATION"
        assert q6.is_required is True

        # Test rejection of skipping required question
        with pytest.raises(HTTPException) as exc_skip:
            await intake_service.skip_question(
                session_id=intake.id,
                question_id=q6.id,
                actor_id="PATIENT"
            )
        assert exc_skip.value.status_code == 400
        assert "Cannot skip required question" in exc_skip.value.detail

        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q6.id,
            raw_response="2 days",
            actor_id="PATIENT"
        )

        # 8. Q7: Medications (Optional) -> Test skipping optional question
        q7 = await intake_service.get_current_question(intake.id)
        assert q7.category == "MEDICATIONS"
        assert q7.is_required is False
        skipped_q7 = await intake_service.skip_question(
            session_id=intake.id,
            question_id=q7.id,
            actor_id="PATIENT"
        )
        assert skipped_q7.is_skipped is True

        # 9. Q8: Allergies (Optional) -> Skip
        q8 = await intake_service.get_current_question(intake.id)
        await intake_service.skip_question(session_id=intake.id, question_id=q8.id)

        # 10. Q9: Past History (Optional) -> Submit
        q9 = await intake_service.get_current_question(intake.id)
        await intake_service.submit_response(
            session_id=intake.id,
            question_id=q9.id,
            raw_response="None",
            actor_id="PATIENT"
        )

        # All questions handled, next question is None
        next_q = await intake_service.get_current_question(intake.id)
        assert next_q is None

        # 11. Complete intake session
        completed = await intake_service.complete_intake_session(intake.id, actor_id="PATIENT")
        assert completed.status == "COMPLETED"
        assert completed.completion_percentage == 100.0
        assert completed.structured_summary is not None
        assert completed.structured_summary["chief_complaint"] == "Severe ankle pain after running"
        assert completed.structured_summary["pain"]["present"] is True
        assert completed.structured_summary["pain"]["location"] == "Left ankle joint"
        assert completed.structured_summary["pain"]["score"] == 7
        assert completed.structured_summary["duration"] == "2 days"

        # 12. Doctor Review
        reviewed = await intake_service.review_intake_session(
            session_id=intake.id,
            reviewer_id="DOC-001",
            notes="Physician verified intake. Proceeding with ankle physical examination and X-ray."
        )
        assert reviewed.status == "REVIEWED"
        assert reviewed.reviewed_by == "DOC-001"

        # 13. Pre-consultation structured output
        doctor_doc = await intake_service.get_structured_intake(intake.id)
        assert doctor_doc["session_id"] == intake.id
        assert doctor_doc["status"] == "REVIEWED"
        assert doctor_doc["patient"]["name"] == "Rohan Gupta"
        assert doctor_doc["structured_summary"]["chief_complaint"] == "Severe ankle pain after running"


@pytest.mark.asyncio
async def test_intake_api_endpoints(auth_client, test_db):
    """Integration test for Clinical Intake REST API endpoints."""
    # 1. Register a patient first
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Deepak",
        "last_name": "Sharma",
        "age": 45,
        "gender": "M",
        "blood_group": "A+",
        "contact_phone": "+919876543450",
        "emergency_contact": "+919876543451"
    })
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # 2. Start intake session via API
    start_res = await auth_client.post("/api/v1/clinical-intakes", json={
        "patient_id": patient_id,
        "language": "en",
        "interaction_mode": "TEXT",
        "chief_complaint_raw": "Mild fever and sore throat"
    })
    assert start_res.status_code == 201
    session_data = start_res.json()
    session_id = session_data["id"]
    assert session_data["status"] == "IN_PROGRESS"

    # 3. Get current question
    q_res = await auth_client.get(f"/api/v1/clinical-intakes/{session_id}/current-question")
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["category"] == "CHIEF_COMPLAINT"

    # 4. Submit response
    r_res = await auth_client.post(f"/api/v1/clinical-intakes/{session_id}/responses", json={
        "question_id": q_data["id"],
        "raw_response": "Mild fever and sore throat for 1 day"
    })
    assert r_res.status_code == 201

    # 5. Fetch structured clinical intake
    struct_res = await auth_client.get(f"/api/v1/clinical-intakes/{session_id}/structured")
    assert struct_res.status_code == 200
    struct_data = struct_res.json()
    assert struct_data["patient"]["name"] == "Deepak Sharma"
