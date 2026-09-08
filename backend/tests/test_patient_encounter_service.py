import pytest
from fastapi import HTTPException
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService

@pytest.mark.asyncio
async def test_patient_service_lifecycle(test_db):
    """Direct unit test for PatientService operations."""
    async with test_db() as session:
        service = PatientService(session)

        # 1. Register a new patient
        patient = await service.register_patient(
            first_name="Sunita",
            last_name="Verma",
            age=42,
            gender="F",
            blood_group="AB+",
            contact_phone="+919876543301",
            emergency_contact="+919876543302",
            actor_id="REC-001",
            actor_role="RECEPTIONIST",
            allergies=["Penicillin"],
            chronic_conditions=["Hypertension"]
        )
        assert patient.id.startswith("PAT-")
        assert patient.first_name == "Sunita"

        # 2. Get patient by ID
        found = await service.get_patient_by_id(patient.id)
        assert found is not None
        assert found.id == patient.id

        # 3. Lookup by phone
        phone_found = await service.find_patient_by_phone("+919876543301")
        assert phone_found is not None
        assert phone_found.id == patient.id

        # 4. Search patients
        search_res = await service.search_patients("Verma")
        assert any(p.id == patient.id for p in search_res)

        # 5. Update patient
        updated = await service.update_patient(
            patient_id=patient.id,
            updates={"age": 43, "allergies": ["Penicillin", "Sulfa drugs"]},
            actor_id="REC-001"
        )
        assert updated.age == 43
        assert "Sulfa drugs" in updated.allergies

        # 6. Invalid patient lookup
        invalid_p = await service.get_patient_by_id("PAT-NON-EXISTENT-999")
        assert invalid_p is None


@pytest.mark.asyncio
async def test_encounter_service_lifecycle(test_db):
    """Direct unit test for EncounterService operations."""
    async with test_db() as session:
        p_service = PatientService(session)
        enc_service = EncounterService(session)

        # 1. Register a patient first
        p = await p_service.register_patient(
            first_name="Vikram",
            last_name="Malhotra",
            age=58,
            gender="M",
            blood_group="O+",
            contact_phone="+919876543310",
            emergency_contact="+919876543311",
            actor_id="REC-001",
            actor_role="RECEPTIONIST"
        )

        # 2. Reject encounter creation for non-existent patient
        with pytest.raises(HTTPException) as exc_info:
            await enc_service.create_encounter(
                patient_id="PAT-FAKE-999",
                chief_complaint="Chest discomfort",
                encounter_type="EMERGENCY",
                current_department_id="DEP-ER",
                actor_id="DOC-001"
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

        # 3. Create valid encounter
        encounter = await enc_service.create_encounter(
            patient_id=p.id,
            chief_complaint="Chest pain and shortness of breath",
            encounter_type="EMERGENCY",
            current_department_id="DEP-ER",
            actor_id="DOC-001",
            heart_rate=110,
            bp_systolic=150,
            bp_diastolic=95,
            spo2=91,
            pain_level=8
        )
        assert encounter.id.startswith("ENC-")
        assert encounter.status == "ACTIVE"
        assert encounter.patient_status == "REGISTERED"

        # 4. Update vitals
        updated_vitals = await enc_service.update_encounter_vitals(
            encounter_id=encounter.id,
            vitals={"heart_rate": 95, "spo2": 96, "pain_level": 5},
            actor_id="NUR-001"
        )
        assert updated_vitals.heart_rate == 95
        assert updated_vitals.spo2 == 96
        assert updated_vitals.triage_time is not None

        # 5. Update clinical state (assign doctor, bed, priority)
        updated_state = await enc_service.update_clinical_state(
            encounter_id=encounter.id,
            actor_id="DOC-001",
            assigned_doctor_id="DOC-001",
            esi_level=2,
            priority=1,
            patient_status="TRIAGED"
        )
        assert updated_state.esi_level == 2
        assert updated_state.patient_status == "TRIAGED"

        # 6. Retrieve patient history through PatientService
        history = await p_service.get_patient_history(p.id)
        assert len(history) >= 1
        assert history[0].id == encounter.id

        # 7. Valid status transition: ACTIVE -> COMPLETED
        completed_enc = await enc_service.update_encounter_status(
            encounter_id=encounter.id,
            new_status="COMPLETED",
            actor_id="DOC-001",
            reason="Patient stabilized and discharged"
        )
        assert completed_enc.status == "COMPLETED"
        assert completed_enc.discharge_time is not None

        # 8. Invalid status transition: COMPLETED -> ACTIVE rejection
        with pytest.raises(HTTPException) as exc_trans:
            await enc_service.update_encounter_status(
                encounter_id=encounter.id,
                new_status="ACTIVE",
                actor_id="DOC-001"
            )
        assert exc_trans.value.status_code == 400
        assert "Cannot reactivate" in exc_trans.value.detail
