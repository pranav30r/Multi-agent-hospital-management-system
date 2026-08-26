import pytest
from fastapi import HTTPException
from app.services.equipment_service import EquipmentService
from app.models.patient import Patient, Encounter

@pytest.mark.asyncio
async def test_equipment_service_direct_operations(test_db):
    """
    Unit test for EquipmentService direct method invocation.
    Tests listing, status update, booking, double-booking rejection, and completion release.
    """
    async with test_db() as session:
        service = EquipmentService(session)

        # 1. Test list_equipment
        eq_list = await service.list_equipment(status="AVAILABLE")
        assert len(eq_list) > 0

        # 2. Test get_equipment_by_id
        target_eq_id = "RES-CT-01"
        eq = await service.get_equipment_by_id(target_eq_id)
        assert eq is not None
        assert eq.id == target_eq_id

        # 3. Test status update: AVAILABLE -> MAINTENANCE -> AVAILABLE
        maint_eq = await service.update_equipment_status(
            equipment_id=target_eq_id,
            status="MAINTENANCE",
            reason="Calibration check",
            actor_id="TECH-001"
        )
        assert maint_eq.status == "MAINTENANCE"

        avail_eq = await service.update_equipment_status(
            equipment_id=target_eq_id,
            status="AVAILABLE",
            reason="Calibration complete",
            actor_id="TECH-001"
        )
        assert avail_eq.status == "AVAILABLE"

        # 4. Create test patient and encounter
        p = Patient(
            id="PAT-EQ-SVC-01",
            first_name="Meera",
            last_name="Sen",
            age=32,
            gender="F",
            blood_group="B+",
            contact_phone="+919876543220",
            emergency_contact="+919876543221"
        )
        enc = Encounter(
            id="ENC-EQ-SVC-01",
            patient_id="PAT-EQ-SVC-01",
            chief_complaint="Suspected Pulmonary Embolism",
            current_department_id="DEP-ER"
        )
        session.add_all([p, enc])
        await session.commit()

        # 5. Test book_equipment
        booking = await service.book_equipment(
            equipment_id=target_eq_id,
            encounter_id="ENC-EQ-SVC-01",
            patient_id="PAT-EQ-SVC-01",
            notes="CT Angiography",
            actor_id="DOC-001"
        )
        assert booking.status == "IN_PROGRESS"
        assert booking.equipment_id == target_eq_id

        # Verify equipment is now IN_USE
        booked_eq = await service.get_equipment_by_id(target_eq_id)
        assert booked_eq.status == "IN_USE"
        assert booked_eq.current_patient_id == "PAT-EQ-SVC-01"

        # 6. Test double booking rejection
        with pytest.raises(HTTPException) as exc_info:
            await service.book_equipment(
                equipment_id=target_eq_id,
                encounter_id="ENC-EQ-SVC-02",
                patient_id="PAT-EQ-SVC-02",
                notes="Second booking",
                actor_id="DOC-002"
            )
        assert exc_info.value.status_code == 400
        assert "cannot be booked" in exc_info.value.detail

        # 7. Test complete_booking (releases equipment to AVAILABLE)
        completed_booking = await service.complete_booking(
            booking_id=booking.id,
            actor_id="TECH-001"
        )
        assert completed_booking.status == "COMPLETED"
        assert completed_booking.end_time is not None

        released_eq = await service.get_equipment_by_id(target_eq_id)
        assert released_eq.status == "AVAILABLE"
        assert released_eq.current_patient_id is None

        # 8. Test double completion rejection
        with pytest.raises(HTTPException) as exc_complete:
            await service.complete_booking(
                booking_id=booking.id,
                actor_id="TECH-001"
            )
        assert exc_complete.value.status_code == 400
        assert "already completed" in exc_complete.value.detail
