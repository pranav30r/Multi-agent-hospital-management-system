import pytest
from fastapi import HTTPException
from app.services.dashboard_service import DashboardService

@pytest.mark.asyncio
async def test_dashboard_service_hospital_state(test_db):
    """Direct unit test for DashboardService get_hospital_state."""
    async with test_db() as session:
        service = DashboardService(session)
        state = await service.get_hospital_state()

        assert "hospital_mode" in state
        assert state["hospital_mode"] in ["NORMAL", "EMERGENCY"]
        assert "beds" in state
        assert state["beds"]["total"] >= 40
        assert "icu" in state
        assert state["icu"]["total"] >= 8
        assert "staff" in state
        assert state["staff"]["total"] >= 30
        assert "equipment" in state
        assert state["equipment"]["total"] >= 15
        assert "patients" in state
        assert "approvals" in state
        assert "agent_performance" in state


@pytest.mark.asyncio
async def test_dashboard_service_departments_summary(test_db):
    """Direct unit test for DashboardService get_departments_summary."""
    async with test_db() as session:
        service = DashboardService(session)
        depts = await service.get_departments_summary()

        assert len(depts) >= 9
        er_dept = next(d for d in depts if d["code"] == "ER")
        assert er_dept["beds_total"] == 6
        assert er_dept["doctors_active"] >= 2
        assert er_dept["staffing_adequate"] is True


@pytest.mark.asyncio
async def test_dashboard_service_department_overview(test_db):
    """Direct unit test for DashboardService single department overview."""
    async with test_db() as session:
        service = DashboardService(session)

        # 1. Valid department
        er_overview = await service.get_department_overview("DEP-ER")
        assert er_overview["department"]["code"] == "ER"
        assert er_overview["beds"]["total"] == 6
        assert "active_patients" in er_overview
        assert "staff" in er_overview

        # 2. Invalid department rejection
        with pytest.raises(HTTPException) as exc_info:
            await service.get_department_overview("DEP-NON-EXISTENT")
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_dashboard_service_telemetry(test_db):
    """Direct unit test for DashboardService top-level command center telemetry."""
    async with test_db() as session:
        service = DashboardService(session)
        telemetry = await service.get_command_center_telemetry()

        assert "hospital_state" in telemetry
        assert "waiting_queue_depth" in telemetry
        assert "active_tasks_count" in telemetry
        assert "recent_predictions" in telemetry
        assert isinstance(telemetry["recent_predictions"], list)
