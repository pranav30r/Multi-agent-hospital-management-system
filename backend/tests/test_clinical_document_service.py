import pytest
from fastapi import HTTPException
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService
from app.services.clinical_document_service import ClinicalDocumentService


@pytest.mark.asyncio
async def test_clinical_document_lifecycle(test_db):
    """Test creating, fetching, listing, verifying, and archiving clinical documents."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        doc_service = ClinicalDocumentService(session)

        # 1. Register Patient & Encounter
        patient = await p_service.register_patient(
            first_name="Ramesh",
            last_name="Babu",
            age=48,
            gender="M",
            blood_group="A+",
            contact_phone="+919876543701",
            emergency_contact="+919876543702",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Chest pain and chronic cough",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="REC-001"
        )

        # 2. Reject document with invalid patient
        with pytest.raises(HTTPException) as exc_p:
            await doc_service.create_document(
                patient_id="PAT-NONEXISTENT",
                document_type="XRAY_REPORT",
                title="Chest X-Ray",
                storage_key="docs/xray_001.pdf"
            )
        assert exc_p.value.status_code == 404

        # 3. Reject document with encounter belonging to different patient
        other_patient = await p_service.register_patient(
            first_name="Other",
            last_name="Person",
            age=30,
            gender="F",
            blood_group="O+",
            contact_phone="+919876543799",
            emergency_contact="+919876543798",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        with pytest.raises(HTTPException) as exc_mismatch:
            await doc_service.create_document(
                patient_id=other_patient.id,
                encounter_id=encounter.id,
                document_type="XRAY_REPORT",
                title="Chest X-Ray",
                storage_key="docs/xray_001.pdf"
            )
        assert exc_mismatch.value.status_code == 400
        assert "does not belong to patient" in exc_mismatch.value.detail

        # 4. Create valid Clinical Document
        doc = await doc_service.create_document(
            patient_id=patient.id,
            encounter_id=encounter.id,
            document_type="XRAY_REPORT",
            title="Chest PA View X-Ray",
            storage_key="s3://hospital-docs/xray_ramesh.pdf",
            storage_provider="S3",
            original_filename="chest_pa_view.pdf",
            content_type="application/pdf",
            file_size_bytes=1048576,
            checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata_json={"modality": "CR", "findings": "Clear lung fields, normal cardiothoracic ratio"},
            actor_id="RAD-001"
        )
        assert doc.id.startswith("DOC-")
        assert doc.status == "RECORDED"
        assert doc.is_verified is False
        assert doc.storage_key == "s3://hospital-docs/xray_ramesh.pdf"

        # 5. Fetch by ID
        fetched = await doc_service.get_document_by_id(doc.id)
        assert fetched is not None
        assert fetched.title == "Chest PA View X-Ray"

        # 6. List by Patient & Encounter
        patient_docs = await doc_service.list_patient_documents(patient.id)
        assert len(patient_docs) == 1
        assert patient_docs[0].id == doc.id

        enc_docs = await doc_service.list_encounter_documents(encounter.id)
        assert len(enc_docs) == 1
        assert enc_docs[0].id == doc.id

        # 7. Verify Document
        verified_doc = await doc_service.verify_document(
            document_id=doc.id,
            verifier_id="DOC-001",
            notes="Radiology report verified. Normal chest radiograph."
        )
        assert verified_doc.is_verified is True
        assert verified_doc.status == "VERIFIED"
        assert verified_doc.verified_by == "DOC-001"

        # 8. Archive Document
        archived = await doc_service.archive_document(
            document_id=doc.id,
            actor_id="ADMIN-001",
            reason="Superseded by higher resolution CT scan"
        )
        assert archived.status == "ARCHIVED"


@pytest.mark.asyncio
async def test_clinical_document_api(auth_client, test_db):
    """Test clinical document REST API endpoints."""
    # 1. Register Patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Pooja",
        "last_name": "Hegde",
        "age": 31,
        "gender": "F",
        "blood_group": "B+",
        "contact_phone": "+919876543720",
        "emergency_contact": "+919876543721"
    })
    patient_id = p_res.json()["id"]

    # 2. POST /clinical-documents
    create_res = await auth_client.post("/api/v1/clinical-documents", json={
        "patient_id": patient_id,
        "document_type": "LAB_REPORT",
        "title": "Complete Blood Count",
        "storage_key": "docs/cbc_pooja.pdf",
        "storage_provider": "LOCAL",
        "original_filename": "cbc_report.pdf",
        "content_type": "application/pdf"
    })
    assert create_res.status_code == 201
    doc_id = create_res.json()["id"]

    # 3. GET /clinical-documents/{document_id}
    get_res = await auth_client.get(f"/api/v1/clinical-documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Complete Blood Count"

    # 4. POST /clinical-documents/{document_id}/verify
    verify_res = await auth_client.post(f"/api/v1/clinical-documents/{doc_id}/verify", json={
        "notes": "Verified by attending physician"
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["is_verified"] is True
    assert verify_res.json()["status"] == "VERIFIED"
