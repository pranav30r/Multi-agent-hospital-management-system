import pytest
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService
from app.services.clinical_intake_service import ClinicalIntakeService
from app.services.clinical_document_service import ClinicalDocumentService
from app.services.investigation_service import InvestigationService


@pytest.mark.asyncio
async def test_document_investigation_timeline_and_doctor_view(test_db):
    """Test full integration across Patient, Encounter, Documents, Investigations, Timeline, and Doctor View."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        intk_service = ClinicalIntakeService(session)
        doc_service = ClinicalDocumentService(session)
        inv_service = InvestigationService(session)

        # 1. Register Patient
        patient = await p_service.register_patient(
            first_name="Harish",
            last_name="Verma",
            age=55,
            gender="M",
            blood_group="O+",
            contact_phone="+919876543780",
            emergency_contact="+919876543781",
            actor_id="REC-001",
            actor_role="RECEPTIONIST",
            allergies=["Iodine Contrast"],
            chronic_conditions=["CKD Stage 3"]
        )

        # 2. Create Encounter
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Flank pain and hematuria",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001",
            heart_rate=88,
            bp_systolic=148,
            bp_diastolic=92,
            spo2=98,
            pain_level=7
        )

        # 3. Create Clinical Document
        doc = await doc_service.create_document(
            patient_id=patient.id,
            encounter_id=encounter.id,
            document_type="CT_REPORT",
            title="Non-Contrast CT KUB",
            storage_key="s3://hospital-docs/ct_kub_harish.pdf",
            storage_provider="S3",
            actor_id="RAD-001"
        )
        await doc_service.verify_document(doc.id, verifier_id="DOC-001", notes="4mm distal ureteral calculus identified")

        # 4. Order & Complete Investigation
        inv = await inv_service.create_investigation(
            patient_id=patient.id,
            encounter_id=encounter.id,
            document_id=doc.id,
            investigation_type="CT",
            test_name="NCCT KUB (Kidney, Ureter, Bladder)",
            result_summary="4mm non-obstructing calculus in right distal ureter with mild hydroureteronephrosis",
            result_values={"stone_size_mm": 4.0, "location": "Right distal ureter"},
            is_abnormal=True,
            abnormal_flags=["CALCULUS_PRESENT", "HYDROURETERONEPHROSIS"],
            ordered_by="DOC-001"
        )
        await inv_service.verify_investigation(inv.id, verifier_id="DOC-001", notes="Verified by Urologist")

        # 5. Verify Timeline Integration
        timeline = await intk_service.get_patient_timeline(patient.id)
        event_types = [e["event_type"] for e in timeline]

        assert "ENCOUNTER_ARRIVED" in event_types
        assert "DOCUMENT_RECORDED" in event_types
        assert "DOCUMENT_VERIFIED" in event_types
        assert "INVESTIGATION_ORDERED" in event_types
        assert "INVESTIGATION_COMPLETED" in event_types
        assert "INVESTIGATION_VERIFIED" in event_types

        # 6. Verify Doctor Clinical View Integration
        doc_view = await intk_service.get_doctor_clinical_view(encounter.id)
        assert len(doc_view["documents"]) == 1
        assert doc_view["documents"][0]["id"] == doc.id
        assert doc_view["documents"][0]["title"] == "Non-Contrast CT KUB"
        assert doc_view["documents"][0]["is_verified"] is True

        assert len(doc_view["investigations"]) == 1
        assert doc_view["investigations"][0]["id"] == inv.id
        assert doc_view["investigations"][0]["is_abnormal"] is True
        assert "CALCULUS_PRESENT" in doc_view["investigations"][0]["abnormal_flags"]


@pytest.mark.asyncio
async def test_document_investigation_timeline_api(auth_client, test_db):
    """API integration test for documents, investigations, and patient timeline."""
    # 1. Register Patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Tarun",
        "last_name": "Kapoor",
        "age": 39,
        "gender": "M",
        "blood_group": "A-",
        "contact_phone": "+919876543790",
        "emergency_contact": "+919876543791"
    })
    patient_id = p_res.json()["id"]

    # 2. POST /clinical-documents
    doc_res = await auth_client.post("/api/v1/clinical-documents", json={
        "patient_id": patient_id,
        "document_type": "LAB_REPORT",
        "title": "Lipid Profile",
        "storage_key": "docs/lipid_tarun.pdf"
    })
    assert doc_res.status_code == 201

    # 3. POST /investigations
    inv_res = await auth_client.post("/api/v1/investigations", json={
        "patient_id": patient_id,
        "investigation_type": "BLOOD_TEST",
        "test_name": "Fasting Lipid Panel",
        "result_summary": "Elevated LDL cholesterol",
        "is_abnormal": True,
        "abnormal_flags": ["HIGH_LDL"]
    })
    assert inv_res.status_code == 201

    # 4. GET /patients/{patient_id}/timeline
    timeline_res = await auth_client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert timeline_res.status_code == 200
    timeline = timeline_res.json()
    assert any(ev["event_type"] == "DOCUMENT_RECORDED" for ev in timeline)
    assert any(ev["event_type"] == "INVESTIGATION_ORDERED" for ev in timeline)
