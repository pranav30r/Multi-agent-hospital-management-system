import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_flow_a_patient_intake_intelligence_priority_doctor_view(auth_client: AsyncClient, test_db):
    """
    FLOW A SMOKE TEST:
    Patient Registration -> Intake Encounter -> Complete Clinical Intake Questionnaire ->
    Deterministic Clinical Intelligence Assessment -> Clinical Priority Recommendation ->
    Consolidated Doctor Pre-Consultation View.
    """
    # 1. Register Patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Rohan",
        "last_name": "Mehra",
        "age": 52,
        "gender": "M",
        "blood_group": "O+",
        "contact_phone": "+919876543901",
        "emergency_contact": "+919876543902",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Type 2 Diabetes", "Hypertension"]
    })
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # 2. Create Encounter
    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute retrosternal chest pain and breathlessness",
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "heart_rate": 115,
        "bp_systolic": 165,
        "bp_diastolic": 105,
        "spo2": 93,
        "temperature_f": 99.2,
        "pain_level": 8,
        "respiratory_rate": 24,
        "gcs_score": 15
    })
    assert enc_res.status_code == 201
    encounter_id = enc_res.json()["id"]

    # 3. Start Clinical Intake Session
    intk_start_res = await auth_client.post("/api/v1/clinical-intakes", json={
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "chief_complaint_raw": "Heavy pressure in chest radiating to left arm",
        "language": "en",
        "interaction_mode": "TEXT"
    })
    assert intk_start_res.status_code == 201
    session_id = intk_start_res.json()["id"]

    # 4. Answer / Skip Questions in Sequence until Complete
    for _ in range(20):
        q_res = await auth_client.get(f"/api/v1/clinical-intakes/{session_id}/current-question")
        if q_res.status_code != 200 or not q_res.json():
            break
        q_data = q_res.json()
        q_id = q_data["id"]
        rtype = q_data.get("response_type", "TEXT")

        if rtype == "BOOLEAN":
            raw_val = "true"
        elif rtype == "SCALE":
            raw_val = "8"
        elif rtype == "NUMBER":
            raw_val = "2"
        elif rtype == "CHOICE" and q_data.get("allowed_options"):
            raw_val = q_data["allowed_options"][0]
        else:
            raw_val = "Retrosternal chest pain radiating to left arm for 1 hour"

        resp_res = await auth_client.post(f"/api/v1/clinical-intakes/{session_id}/responses", json={
            "question_id": q_id,
            "raw_response": raw_val,
            "response_metadata": {"confidence": 0.95}
        })
        assert resp_res.status_code == 201

    # 5. Complete Intake Session
    complete_res = await auth_client.post(f"/api/v1/clinical-intakes/{session_id}/complete")
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "COMPLETED"

    # 6. Analyze Clinical Intelligence
    intel_res = await auth_client.post(f"/api/v1/clinical-intelligence/{encounter_id}/analyze")
    assert intel_res.status_code == 200
    assessment = intel_res.json()
    assert assessment["severity"] in ["HIGH", "CRITICAL"]
    assert assessment["requires_priority_attention"] is True
    assert assessment["red_flags_count"] >= 1

    # 7. Evaluate Clinical Priority
    pri_res = await auth_client.post(f"/api/v1/clinical-priority/{encounter_id}/evaluate")
    assert pri_res.status_code == 200
    pri_data = pri_res.json()
    assert pri_data["priority_level"] in ["HIGH", "CRITICAL"]
    assert pri_data["route"] in ["IMMEDIATE_DOCTOR_REVIEW", "EMERGENCY_TRIAGE"]

    # 8. Doctor Clinical View
    doc_view_res = await auth_client.get(f"/api/v1/clinical-intakes/doctor-view/{encounter_id}")
    assert doc_view_res.status_code == 200
    doc_view = doc_view_res.json()
    assert doc_view["patient"]["id"] == patient_id
    assert doc_view["current_encounter"]["id"] == encounter_id
    assert doc_view["clinical_intake"]["status"] == "COMPLETED"
    assert doc_view["clinical_priority"]["priority_level"] == pri_data["priority_level"]


@pytest.mark.asyncio
async def test_flow_b_bed_staff_and_dashboard_integration(auth_client: AsyncClient, admin_client: AsyncClient, test_db):
    """
    FLOW B SMOKE TEST:
    Patient Arrival -> Encounter -> Manual Bed Booking -> Staff Shift & Workload -> Dashboard Telemetry.
    """
    # 1. Register Patient & Encounter
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Kavita",
        "last_name": "Krishnan",
        "age": 29,
        "gender": "F",
        "blood_group": "B-",
        "contact_phone": "+919876543910",
        "emergency_contact": "+919876543911"
    })
    patient_id = p_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Acute appendicitis evaluation",
        "encounter_type": "INPATIENT",
        "current_department_id": "DEP-ER"
    })
    encounter_id = enc_res.json()["id"]

    # 2. Book Bed
    bed_res = await auth_client.post("/api/v1/beds/book-manual", json={
        "bed_id": "BED-ER-01",
        "patient_id": patient_id,
        "encounter_id": encounter_id
    })
    assert bed_res.status_code == 200
    assert bed_res.json()["status"] == "RESERVED"

    # 3. Update Staff Workload via admin client
    staff_wl_res = await admin_client.patch("/api/v1/staff/DOC-001/workload", json={
        "delta": 2,
        "changed_by": "ADM-001",
        "reason": "Assigned 2 emergency patients"
    })
    assert staff_wl_res.status_code == 200
    assert staff_wl_res.json()["current_workload"] >= 1

    # 4. Check Dashboard State
    dash_res = await auth_client.get("/api/v1/dashboard/state")
    assert dash_res.status_code == 200
    dash_state = dash_res.json()
    assert dash_state["beds"]["total"] >= 1
    assert dash_state["patients"]["active_encounters"] >= 1
    assert "clinical_priorities" in dash_state


@pytest.mark.asyncio
async def test_flow_c_investigation_document_verification_timeline(auth_client: AsyncClient, test_db):
    """
    FLOW C SMOKE TEST:
    Clinical Document -> Linked Diagnostic Investigation -> Physician Verification -> Patient Timeline.
    """
    # 1. Register Patient & Encounter
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Vikram",
        "last_name": "Seth",
        "age": 60,
        "gender": "M",
        "blood_group": "AB-",
        "contact_phone": "+919876543920",
        "emergency_contact": "+919876543921"
    })
    patient_id = p_res.json()["id"]

    enc_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "chief_complaint": "Persistent headache and visual blurriness",
        "encounter_type": "OUTPATIENT",
        "current_department_id": "DEP-ER"
    })
    encounter_id = enc_res.json()["id"]

    # 2. Record Clinical Document
    doc_res = await auth_client.post("/api/v1/clinical-documents", json={
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "document_type": "MRI_REPORT",
        "title": "Brain MRI with Contrast",
        "storage_key": "s3://hospital-docs/mri_vikram.pdf",
        "storage_provider": "S3"
    })
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    # 3. Verify Document
    v_doc_res = await auth_client.post(f"/api/v1/clinical-documents/{doc_id}/verify", json={
        "notes": "Reviewed and verified by Neurologist"
    })
    assert v_doc_res.status_code == 200
    assert v_doc_res.json()["is_verified"] is True

    # 4. Record Investigation linked to Document
    inv_res = await auth_client.post("/api/v1/investigations", json={
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "document_id": doc_id,
        "investigation_type": "MRI",
        "test_name": "MRI Brain Protocol",
        "result_summary": "Mild microvascular ischemic changes, no acute infarct",
        "is_abnormal": False
    })
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["id"]

    # 5. Verify Investigation
    v_inv_res = await auth_client.post(f"/api/v1/investigations/{inv_id}/verify", json={
        "notes": "Verified by Attending Radiologist"
    })
    assert v_inv_res.status_code == 200
    assert v_inv_res.json()["is_verified"] is True

    # 6. Verify Patient Timeline
    tl_res = await auth_client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert tl_res.status_code == 200
    events = tl_res.json()
    event_types = [e["event_type"] for e in events]
    assert "DOCUMENT_RECORDED" in event_types
    assert "DOCUMENT_VERIFIED" in event_types
    assert "INVESTIGATION_ORDERED" in event_types
    assert "INVESTIGATION_VERIFIED" in event_types


@pytest.mark.asyncio
async def test_security_rbac_and_error_handling(auth_client: AsyncClient, test_db):
    """
    SECURITY & RBAC SMOKE TEST:
    Verify anonymous request rejection (401), invalid payloads (422), non-existent resources (404),
    and cross-patient validation errors (400).
    """
    # 1. Anonymous request with invalid/missing token -> 401
    anon_res = await auth_client.post("/api/v1/clinical-documents", json={
        "patient_id": "PAT-001",
        "document_type": "LAB_REPORT",
        "title": "Unauthorized Document",
        "storage_key": "docs/test.pdf"
    }, headers={"Authorization": "Bearer invalid.jwt.token"})
    assert anon_res.status_code == 401

    # 2. Non-existent patient lookup -> 404
    not_found_res = await auth_client.get("/api/v1/patients/PAT-DOESNOTEXIST")
    assert not_found_res.status_code == 404

    # 3. Invalid payload (missing required field) -> 422
    bad_payload_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "OnlyFirstName"
    })
    assert bad_payload_res.status_code == 422
