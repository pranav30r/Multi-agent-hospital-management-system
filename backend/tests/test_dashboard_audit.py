import pytest

@pytest.mark.asyncio
async def test_dashboard_state_snapshot(client):
    """Test full hospital dashboard state snapshot endpoint."""
    res = await client.get("/api/v1/dashboard/state")
    assert res.status_code == 200
    state = res.json()
    assert "hospital_mode" in state
    assert state["hospital_mode"] == "NORMAL"
    assert state["beds"]["total"] == 44
    assert state["staff"]["total"] == 33
    assert state["equipment"]["total"] == 15
    assert state["icu"]["total"] == 8


@pytest.mark.asyncio
async def test_dashboard_departments_summary(client):
    """Test per-department summary with capacity metrics."""
    res = await client.get("/api/v1/dashboard/departments/summary")
    assert res.status_code == 200
    depts = res.json()
    assert len(depts) == 9
    er_dept = next(d for d in depts if d["code"] == "ER")
    assert er_dept["beds_total"] == 6
    assert er_dept["doctors_active"] == 2
    assert er_dept["staffing_adequate"] is True


@pytest.mark.asyncio
async def test_audit_logs_and_stats(client):
    """Test querying audit logs and audit statistics."""
    res = await client.get("/api/v1/audit")
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)

    stats_res = await client.get("/api/v1/audit/stats")
    assert stats_res.status_code == 200
    assert "total_entries" in stats_res.json()
