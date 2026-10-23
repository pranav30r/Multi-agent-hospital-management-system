import pytest
from fastapi import HTTPException
from app.services.bed_service import BedService
from app.models.patient import Patient, Encounter
from app.models.bed import Bed, BedAssignment

@pytest.mark.asyncio
async def test_bed_service_direct_operations(test_db):
    """
    Unit test for BedService direct method invocation.
    Tests list_departments, list_beds, reserve_bed, and confirm_patient_arrival directly.
    """
    async with test_db() as session:
        service = BedService(session)

        # 1. Test list_departments
        depts = await service.list_departments()
        assert len(depts) >= 9

        # 2. Test list_beds
        beds = await service.list_beds(bed_status="AVAILABLE")
        assert len(beds) > 0

        # 3. Create test patient and encounter
        p = Patient(
            id="PAT-SVC-01",
            first_name="Aarav",
            last_name="Sharma",
            age=45,
            gender="M",
            blood_group="O+",
            contact_phone="+919876543210",
            emergency_contact="+919876543211"
        )
        enc = Encounter(
            id="ENC-SVC-01",
            patient_id="PAT-SVC-01",
            chief_complaint="Chest Pain",
            current_department_id="DEP-ER"
        )
        session.add_all([p, enc])
        await session.commit()

        # 4. Test reserve_bed
        target_bed_id = "BED-ICU-07"
        reserved_bed = await service.reserve_bed(
            bed_id=target_bed_id,
            patient_id="PAT-SVC-01",
            encounter_id="ENC-SVC-01",
            actor_id="DOC-001",
            actor_role="DOCTOR",
            reason="Direct service test reservation"
        )
        assert reserved_bed.status == "RESERVED"
        assert reserved_bed.current_patient_id == "PAT-SVC-01"

        # 5. Test double booking prevention directly in service
        with pytest.raises(HTTPException) as exc_info:
            await service.reserve_bed(
                bed_id=target_bed_id,
                patient_id="PAT-SVC-02",
                encounter_id="ENC-SVC-02",
                actor_id="DOC-002",
                actor_role="DOCTOR"
            )
        assert exc_info.value.status_code == 400
        assert "cannot be booked" in exc_info.value.detail

        # 6. Test confirm_patient_arrival
        occupied_bed = await service.confirm_patient_arrival(
            bed_id=target_bed_id,
            actor_id="DOC-001",
            actor_role="DOCTOR"
        )
        assert occupied_bed.status == "OCCUPIED"


@pytest.mark.asyncio
async def test_confirming_transfer_releases_previous_ward_bed(test_db):
    async with test_db() as session:
        patient = Patient(
            id="PAT-TRANSFER-01", first_name="Vijay", last_name="Agrawal", age=43,
            gender="M", blood_group="O+", contact_phone="+919876540001",
            emergency_contact="+919876540002",
        )
        encounter = Encounter(
            id="ENC-TRANSFER-01", patient_id=patient.id, chief_complaint="Severe respiratory problem",
            current_department_id="DEP-WA", current_bed_id="BED-WA-01",
        )
        old_bed = await session.get(Bed, "BED-WA-01")
        icu_bed = await session.get(Bed, "BED-ICU-07")
        old_bed.status = "OCCUPIED"
        old_bed.current_patient_id = patient.id
        old_bed.current_encounter_id = encounter.id
        icu_bed.status = "RESERVED"
        icu_bed.current_patient_id = patient.id
        icu_bed.current_encounter_id = encounter.id
        session.add_all([
            patient,
            encounter,
            BedAssignment(bed_id=old_bed.id, encounter_id=encounter.id, patient_id=patient.id, assigned_by="DOC-001", status="OCCUPIED"),
            BedAssignment(bed_id=icu_bed.id, encounter_id=encounter.id, patient_id=patient.id, assigned_by="DOC-001", status="RESERVED"),
        ])
        await session.commit()

        await BedService(session).confirm_patient_arrival(
            bed_id=icu_bed.id, actor_id="DOC-001", actor_role="DOCTOR", tenant_id="HOSP-DEFAULT"
        )

        await session.refresh(old_bed)
        await session.refresh(icu_bed)
        await session.refresh(encounter)
        assert old_bed.status == "AVAILABLE"
        assert old_bed.current_encounter_id is None
        assert icu_bed.status == "OCCUPIED"
        assert encounter.current_bed_id == icu_bed.id
