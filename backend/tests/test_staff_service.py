import pytest
from fastapi import HTTPException
from app.services.staff_service import StaffService

@pytest.mark.asyncio
async def test_staff_service_crud_and_lifecycle(test_db):
    """Test StaffService creation, lookup, search, update, and department validation."""
    async with test_db() as session:
        service = StaffService(session)

        # 1. Reject staff creation with non-existent department
        with pytest.raises(HTTPException) as exc_dept:
            await service.create_staff(
                id="DOC-SVC-999",
                first_name="Ananya",
                last_name="Deshmukh",
                role="DOCTOR",
                department_id="DEP-NON-EXISTENT",
                actor_id="ADM-001"
            )
        assert exc_dept.value.status_code == 400
        assert "Referenced department" in exc_dept.value.detail

        # 2. Create valid staff
        staff = await service.create_staff(
            id="DOC-SVC-001",
            first_name="Ananya",
            last_name="Deshmukh",
            role="DOCTOR",
            department_id="DEP-ER",
            specialization="Trauma Surgery",
            max_workload=4,
            actor_id="ADM-001"
        )
        assert staff.id == "DOC-SVC-001"
        assert staff.status == "AVAILABLE"
        assert staff.current_workload == 0

        # 3. Reject duplicate staff ID
        with pytest.raises(HTTPException) as exc_dup:
            await service.create_staff(
                id="DOC-SVC-001",
                first_name="Duplicate",
                last_name="Doctor",
                role="DOCTOR",
                department_id="DEP-ER",
                actor_id="ADM-001"
            )
        assert exc_dup.value.status_code == 400
        assert "already exists" in exc_dup.value.detail

        # 4. Get by ID
        fetched = await service.get_staff_by_id("DOC-SVC-001")
        assert fetched is not None
        assert fetched.first_name == "Ananya"

        # 5. Search staff
        results = await service.search_staff("Deshmukh")
        assert any(s.id == "DOC-SVC-001" for s in results)

        # 6. Update staff
        updated = await service.update_staff(
            staff_id="DOC-SVC-001",
            updates={"specialization": "Emergency Medicine"},
            actor_id="ADM-001"
        )
        assert updated.specialization == "Emergency Medicine"


@pytest.mark.asyncio
async def test_staff_status_and_workload(test_db):
    """Test StaffService status transitions, workload adjustments, and available staff discovery."""
    async with test_db() as session:
        service = StaffService(session)

        # 1. Valid status update
        staff = await service.update_staff_status(
            staff_id="DOC-001",
            new_status="BUSY",
            actor_id="DOC-001",
            reason="In emergency surgery"
        )
        assert staff.status == "BUSY"

        # 2. Invalid status rejection
        with pytest.raises(HTTPException) as exc_stat:
            await service.update_staff_status(
                staff_id="DOC-001",
                new_status="SLEEPING",
                actor_id="DOC-001"
            )
        assert exc_stat.value.status_code == 400
        assert "Invalid staff status" in exc_stat.value.detail

        # 3. Workload increments
        res_work = await service.adjust_workload(staff_id="DOC-001", delta=1, actor_id="DOC-001")
        assert res_work["current_workload"] >= 1

        # 4. Decrement workload
        res_dec = await service.adjust_workload(staff_id="DOC-001", delta=-10, actor_id="DOC-001")
        assert res_dec["current_workload"] == 0
        assert res_dec["status"] == "AVAILABLE"

        # 5. Find available staff
        avail = await service.find_available_staff(department_id="DEP-ER", role="DOCTOR")
        assert len(avail) >= 1


@pytest.mark.asyncio
async def test_staff_shifts_and_skills(test_db):
    """Test StaffService shift scheduling, status transitions, and skills tracking."""
    async with test_db() as session:
        service = StaffService(session)

        # 1. Create shift
        shift = await service.create_shift(
            staff_id="DOC-001",
            department_id="DEP-ER",
            shift_type="MORNING",
            start_time="06:00",
            end_time="14:00",
            actor_id="ADM-001"
        )
        assert shift.status == "SCHEDULED"

        # 2. Update shift status: SCHEDULED -> ACTIVE -> COMPLETED
        active_shift = await service.update_shift_status(
            shift_id=shift.id,
            new_status="ACTIVE",
            actor_id="ADM-001"
        )
        assert active_shift.status == "ACTIVE"

        comp_shift = await service.update_shift_status(
            shift_id=shift.id,
            new_status="COMPLETED",
            actor_id="ADM-001"
        )
        assert comp_shift.status == "COMPLETED"

        # 3. Reject invalid transition: COMPLETED -> ACTIVE
        with pytest.raises(HTTPException) as exc_shift:
            await service.update_shift_status(
                shift_id=shift.id,
                new_status="ACTIVE",
                actor_id="ADM-001"
            )
        assert exc_shift.value.status_code == 400
        assert "Cannot reactivate" in exc_shift.value.detail

        # 4. Add skill
        skill = await service.add_staff_skill(
            staff_id="DOC-001",
            skill_name="ACLS_CERTIFIED",
            actor_id="ADM-001"
        )
        assert skill.skill_name == "ACLS_CERTIFIED"

        # 5. Check skill
        has_acls = await service.has_skill("DOC-001", "ACLS_CERTIFIED")
        assert has_acls is True

        has_pals = await service.has_skill("DOC-001", "NON_EXISTENT_SKILL")
        assert has_pals is False

        # 6. List skills
        skills = await service.list_staff_skills("DOC-001")
        assert any(s.skill_name == "ACLS_CERTIFIED" for s in skills)
