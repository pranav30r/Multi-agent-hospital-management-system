import pytest

@pytest.mark.asyncio
async def test_emergency_declaration_and_resolution(admin_client):
    """Test declaring a hospital emergency and resolving it with authenticated admin."""
    # 1. Declare emergency
    emg_payload = {
        "event_type": "MASS_CASUALTY",
        "severity": "CRITICAL",
        "description": "Code Red: 10 incoming trauma victims",
        "affected_departments": ["DEP-ER", "DEP-ICU", "DEP-SUR"],
        "expected_patient_surge": 10
    }
    dec_res = await admin_client.post("/api/v1/emergencies/declare", json=emg_payload)
    assert dec_res.status_code == 201
    emg = dec_res.json()
    assert emg["status"] == "ACTIVE"
    emg_id = emg["id"]

    # 2. Check active emergencies
    act_res = await admin_client.get("/api/v1/emergencies/active")
    assert act_res.status_code == 200
    assert len(act_res.json()) == 1

    # 3. Resolve emergency
    res_res = await admin_client.post(
        f"/api/v1/emergencies/{emg_id}/resolve"
    )
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "RESOLVED"

    # 4. Check active emergencies is now 0
    act_res_after = await admin_client.get("/api/v1/emergencies/active")
    assert len(act_res_after.json()) == 0


@pytest.mark.asyncio
async def test_approvals_list(client):
    """Test approval queue query endpoint."""
    res = await client.get("/api/v1/approvals/pending")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
