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
async def test_manual_bed_booking_lifecycle(test_db, auth_client):
    """Test manual bed booking (AVAILABLE -> RESERVED) and arrival confirmation (RESERVED -> OCCUPIED)."""
    # Create patient & encounter
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Test",
        "last_name": "Patient",
        "age": 45,
        "gender": "M",
        "blood_group": "A+",
        "contact_phone": "+919876543200",
        "emergency_contact": "+919876543201"
    })
    patient_id = p_res.json()["id"]

    e_res = await auth_client.post("/api/v1/patients/encounters", json={
        "patient_id": patient_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Acute Respiratory Distress"
    })
    encounter_id = e_res.json()["id"]

    # 1. Book bed manually with authenticated doctor/admin
    book_payload = {
        "bed_id": "BED-ICU-01",
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "reason": "Direct critical ICU reservation"
    }
    book_res = await auth_client.post("/api/v1/beds/book-manual", json=book_payload)
    assert book_res.status_code == 200
    bed_data = book_res.json()
    assert bed_data["id"] == "BED-ICU-01"
    assert bed_data["status"] == "RESERVED"
    assert bed_data["current_patient_id"] == patient_id

    # 2. Confirm physical arrival
    arrive_res = await auth_client.post(
        "/api/v1/beds/BED-ICU-01/confirm-patient-in-bed"
    )
    assert arrive_res.status_code == 200
    occupied_data = arrive_res.json()
    assert occupied_data["status"] == "OCCUPIED"
