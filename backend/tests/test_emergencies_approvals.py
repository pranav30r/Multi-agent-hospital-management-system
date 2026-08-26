import pytest

@pytest.mark.asyncio
async def test_emergency_declaration_and_resolution(client):
    """Test declaring a hospital emergency and resolving it."""
    # 1. Declare emergency
    emg_payload = {
        "name": "Mass Casualty - Multi-Vehicle Collision",
        "emergency_type": "MASS_CASUALTY",
        "declared_by": "ADM-001",
        "affected_departments": ["DEP-ER", "DEP-ICU", "DEP-SUR"],
        "notes": "Code Red: 10 incoming trauma victims"
    }
    dec_res = await client.post("/api/v1/emergencies/declare", json=emg_payload)
    assert dec_res.status_code == 200
    emg = dec_res.json()
    assert emg["status"] == "ACTIVE"
    emg_id = emg["id"]

    # 2. Check active emergencies
    act_res = await client.get("/api/v1/emergencies/active")
    assert act_res.status_code == 200
    assert len(act_res.json()) == 1

    # 3. Resolve emergency
    res_res = await client.post(
        f"/api/v1/emergencies/{emg_id}/resolve",
        json={"resolved_by": "ADM-001"}
    )
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "RESOLVED"

    # 4. Check active emergencies is now 0
    act_res_after = await client.get("/api/v1/emergencies/active")
    assert len(act_res_after.json()) == 0


@pytest.mark.asyncio
async def test_approvals_list(client):
    """Test approval queue query endpoint."""
    res = await client.get("/api/v1/approvals/pending")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
