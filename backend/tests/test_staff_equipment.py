import pytest

@pytest.mark.asyncio
async def test_staff_workload_and_status(client):
    """Test staff workload incrementation and auto-status handling."""
    # List doctors
    res = await client.get("/api/v1/staff?role=DOCTOR")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 8

    # Increment workload
    wl_res = await client.patch("/api/v1/staff/DOC-001/workload?delta=1")
    assert wl_res.status_code == 200
    assert wl_res.json()["current_workload"] == 1

    # Update status
    st_res = await client.patch("/api/v1/staff/DOC-001/status", json={
        "status": "BUSY",
        "changed_by": "ADM-001",
        "reason": "Attending emergency trauma case"
    })
    assert st_res.status_code == 200
    assert st_res.json()["status"] == "BUSY"


@pytest.mark.asyncio
async def test_equipment_booking_and_release(client):
    """Test equipment booking for a patient and subsequent completion/release."""
    # List equipment
    eq_res = await client.get("/api/v1/equipment?resource_type=CT_SCANNER")
    assert eq_res.status_code == 200
    scanners = eq_res.json()
    assert len(scanners) == 2

    # Book CT Scanner
    book_payload = {
        "equipment_id": "RES-CT-01",
        "encounter_id": "ENC-TEST-02",
        "patient_id": "PAT-TEST-02",
        "requested_by": "DOC-001",
        "notes": "Emergency Head CT for stroke protocol"
    }
    b_res = await client.post("/api/v1/equipment/bookings", json=book_payload)
    assert b_res.status_code == 201
    booking = b_res.json()
    assert booking["status"] == "IN_PROGRESS"
    booking_id = booking["id"]

    # Verify equipment status is IN_USE
    check_eq = await client.get("/api/v1/equipment/RES-CT-01")
    assert check_eq.json()["status"] == "IN_USE"

    # Complete booking
    comp_res = await client.post(f"/api/v1/equipment/bookings/{booking_id}/complete")
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "COMPLETED"

    # Verify equipment status returned to AVAILABLE
    released_eq = await client.get("/api/v1/equipment/RES-CT-01")
    assert released_eq.json()["status"] == "AVAILABLE"
