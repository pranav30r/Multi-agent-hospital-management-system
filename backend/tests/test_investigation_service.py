import pytest
from fastapi import HTTPException
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService
from app.services.clinical_document_service import ClinicalDocumentService
from app.services.investigation_service import InvestigationService


@pytest.mark.asyncio
async def test_investigation_lifecycle(test_db):
    """Test ordering, recording results, linking document, and verifying investigations."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)
        doc_service = ClinicalDocumentService(session)
        inv_service = InvestigationService(session)

        # 1. Register Patient & Encounter
        patient = await p_service.register_patient(
            first_name="Sunil",
            last_name="Gavaskar",
            age=65,
            gender="M",
            blood_group="O+",
            contact_phone="+919876543750",
            emergency_contact="+919876543751",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )
        encounter = await enc_service.create_encounter(
            patient_id=patient.id,
            chief_complaint="Severe fatigue and paleness",
            encounter_type="OUTPATIENT",
            current_department_id="DEP-ER",
            actor_id="REC-001"
        )

        # 2. Order Investigation
        inv = await inv_service.create_investigation(
            patient_id=patient.id,
            encounter_id=encounter.id,
            investigation_type="BLOOD_TEST",
            test_name="Serum Ferritin & Iron Studies",
            ordered_by="DOC-001"
        )
        assert inv.id.startswith("INV-")
        assert inv.status == "ORDERED"
        assert inv.is_verified is False

        # 3. Record Results with abnormal findings
        updated_inv = await inv_service.record_investigation_results(
            investigation_id=inv.id,
            result_summary="Severe microcytic hypochromic anemia secondary to iron deficiency",
            result_values={
                "hemoglobin": {"value": 7.2, "unit": "g/dL", "ref_range": "13.0-17.0", "abnormal": True},
                "serum_ferritin": {"value": 6.0, "unit": "ng/mL", "ref_range": "20.0-250.0", "abnormal": True},
                "serum_iron": {"value": 25.0, "unit": "mcg/dL", "ref_range": "60.0-170.0", "abnormal": True}
            },
            is_abnormal=True,
            abnormal_flags=["SEVERE_ANEMIA", "LOW_FERRITIN"],
            actor_id="LAB-001"
        )
        assert updated_inv.status == "COMPLETED"
        assert updated_inv.is_abnormal is True
        assert len(updated_inv.abnormal_flags) == 2

        # 4. Create and Link Clinical Document
        doc = await doc_service.create_document(
            patient_id=patient.id,
            encounter_id=encounter.id,
            document_type="LAB_REPORT",
            title="Iron Profile Lab Report",
            storage_key="docs/iron_profile_sunil.pdf",
            actor_id="LAB-001"
        )
        linked = await inv_service.link_to_document(
            investigation_id=inv.id,
            document_id=doc.id,
            actor_id="LAB-001"
        )
        assert linked.document_id == doc.id

        # 5. Verify Investigation
        verified_inv = await inv_service.verify_investigation(
            investigation_id=inv.id,
            verifier_id="DOC-001",
            notes="Critically low hemoglobin confirmed. Prescribed intravenous iron sucrose infusion."
        )
        assert verified_inv.is_verified is True
        assert verified_inv.status == "VERIFIED"
        assert verified_inv.verified_by == "DOC-001"

        # 6. Reject editing verified investigation
        with pytest.raises(HTTPException) as exc_alter:
            await inv_service.record_investigation_results(
                investigation_id=inv.id,
                result_summary="Trying to alter verified results"
            )
        assert exc_alter.value.status_code == 400
        assert "Cannot alter results of verified investigation" in exc_alter.value.detail


@pytest.mark.asyncio
async def test_investigation_api(auth_client, test_db):
    """Test investigation REST API endpoints."""
    # 1. Register Patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Divya",
        "last_name": "Dutta",
        "age": 42,
        "gender": "F",
        "blood_group": "AB-",
        "contact_phone": "+919876543760",
        "emergency_contact": "+919876543761"
    })
    patient_id = p_res.json()["id"]

    # 2. POST /investigations
    inv_res = await auth_client.post("/api/v1/investigations", json={
        "patient_id": patient_id,
        "investigation_type": "URINE_TEST",
        "test_name": "Routine Urinalysis",
        "result_summary": "Trace proteinuria, negative for glycosuria",
        "is_abnormal": False
    })
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["id"]

    # 3. GET /investigations/{investigation_id}
    get_res = await auth_client.get(f"/api/v1/investigations/{inv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["test_name"] == "Routine Urinalysis"

    # 4. POST /investigations/{investigation_id}/verify
    v_res = await auth_client.post(f"/api/v1/investigations/{inv_id}/verify", json={
        "notes": "Verified normal urinalysis"
    })
    assert v_res.status_code == 200
    assert v_res.json()["is_verified"] is True
