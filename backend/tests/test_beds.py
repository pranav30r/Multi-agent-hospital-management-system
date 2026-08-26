import pytest

@pytest.mark.asyncio
async def test_list_departments(client):
    """Test department query endpoint."""
    res = await client.get("/api/v1/departments")
    assert res.status_code == 200
    depts = res.json()
    assert len(depts) == 9
    dept_codes = {d["code"] for d in depts}
    assert "ER" in dept_codes
    assert "ICU" in dept_codes


@pytest.mark.asyncio
async def test_list_beds_filter(client):
    """Test bed listing and department filtering."""
    res = await client.get("/api/v1/beds?department_id=DEP-ICU")
    assert res.status_code == 200
    beds = res.json()
    assert len(beds) == 8
    assert all(b["department_id"] == "DEP-ICU" for b in beds)


@pytest.mark.asyncio
async def test_manual_bed_booking_lifecycle(client):
    """Test manual bed booking (AVAILABLE -> RESERVED) and arrival confirmation (RESERVED -> OCCUPIED)."""
    # 1. Book bed manually
    book_payload = {
        "bed_id": "BED-ICU-01",
        "encounter_id": "ENC-TEST-01",
        "patient_id": "PAT-TEST-01",
        "booked_by": "ADM-001",
        "reason": "Direct critical ICU reservation"
    }
    book_res = await client.post("/api/v1/beds/book-manual", json=book_payload)
    assert book_res.status_code == 200
    bed_data = book_res.json()
    assert bed_data["id"] == "BED-ICU-01"
    assert bed_data["status"] == "RESERVED"
    assert bed_data["current_patient_id"] == "PAT-TEST-01"

    # 2. Confirm physical arrival
    arrive_res = await client.post(
        "/api/v1/beds/BED-ICU-01/confirm-patient-in-bed",
        json={"confirmed_by": "NUR-001"}
    )
    assert arrive_res.status_code == 200
    occupied_data = arrive_res.json()
    assert occupied_data["status"] == "OCCUPIED"
