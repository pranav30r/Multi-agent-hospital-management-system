import pytest

@pytest.mark.asyncio
async def test_patient_registration_and_lookup(auth_client):
    """Test registering a new patient and fetching by ID with authenticated client."""
    patient_data = {
        "first_name": "Rohan",
        "last_name": "Kulkarni",
        "age": 39,
        "gender": "M",
        "blood_group": "B+",
        "contact_phone": "+919876543210",
        "emergency_contact": "+919876543211",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Hypertension"]
    }
    create_res = await auth_client.post("/api/v1/patients", json=patient_data)
    assert create_res.status_code == 201
    p_data = create_res.json()
    assert p_data["first_name"] == "Rohan"
    patient_id = p_data["id"]

    get_res = await auth_client.get(f"/api/v1/patients/{patient_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == patient_id


@pytest.mark.asyncio
async def test_encounter_creation_and_active_list(auth_client):
    """Test creating an emergency encounter with vitals and querying active encounters."""
    # First create a patient
    p_res = await auth_client.post("/api/v1/patients", json={
        "first_name": "Ananya",
        "last_name": "Sen",
        "age": 31,
        "gender": "F",
        "blood_group": "A+",
        "contact_phone": "+919876543212",
        "emergency_contact": "+919876543213"
    })
    patient_id = p_res.json()["id"]

    encounter_data = {
        "patient_id": patient_id,
        "encounter_type": "EMERGENCY",
        "current_department_id": "DEP-ER",
        "chief_complaint": "Acute severe substernal chest pain",
        "heart_rate": 115,
        "bp_systolic": 165,
        "bp_diastolic": 95,
        "spo2": 93,
        "temperature_f": 99.0,
        "pain_level": 9,
        "respiratory_rate": 24
    }
    enc_res = await auth_client.post("/api/v1/patients/encounters", json=encounter_data)
    assert enc_res.status_code == 201
    enc_data = enc_res.json()
    assert enc_data["patient_id"] == patient_id
    assert enc_data["current_department_id"] == "DEP-ER"
    assert enc_data["status"] == "ACTIVE"

    # Query active encounters
    active_res = await auth_client.get("/api/v1/patients/encounters/active")
    assert active_res.status_code == 200
    encs = active_res.json()
    assert len(encs) >= 1
    assert any(e["patient_id"] == patient_id for e in encs)
