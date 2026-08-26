import pytest

@pytest.mark.asyncio
async def test_patient_registration_and_lookup(client):
    """Test registering a new patient and fetching by ID."""
    patient_data = {
        "first_name": "Rohan",
        "last_name": "Kulkarni",
        "date_of_birth": "1985-04-12",
        "gender": "M",
        "contact_number": "+919876543210",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Hypertension"]
    }
    create_res = await client.post("/api/v1/patients", json=patient_data)
    assert create_res.status_code == 201
    p_data = create_res.json()
    assert p_data["first_name"] == "Rohan"
    patient_id = p_data["id"]

    get_res = await client.get(f"/api/v1/patients/{patient_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == patient_id


@pytest.mark.asyncio
async def test_encounter_creation_and_active_list(client):
    """Test creating an emergency encounter with vitals and querying active encounters."""
    # First create a patient
    p_res = await client.post("/api/v1/patients", json={
        "first_name": "Ananya",
        "last_name": "Sen",
        "date_of_birth": "1992-09-21",
        "gender": "F"
    })
    patient_id = p_res.json()["id"]

    encounter_data = {
        "patient_id": patient_id,
        "admission_type": "EMERGENCY",
        "chief_complaint": "Acute severe substernal chest pain",
        "initial_vitals": {
            "heart_rate": 115,
            "blood_pressure_systolic": 165,
            "blood_pressure_diastolic": 95,
            "oxygen_saturation": 93,
            "temperature_celsius": 37.2,
            "respiratory_rate": 24,
            "pain_scale": 9
        },
        "presenting_symptoms": ["chest pain", "shortness of breath", "diaphoresis"]
    }
    enc_res = await client.post("/api/v1/patients/encounters", json=encounter_data)
    assert enc_res.status_code == 201
    enc_data = enc_res.json()
    assert enc_data["patient_id"] == patient_id
    assert enc_data["current_department_id"] == "DEP-ER"
    assert enc_data["status"] == "ACTIVE"

    # Query active encounters
    active_res = await client.get("/api/v1/patients/encounters/active")
    assert active_res.status_code == 200
    encs = active_res.json()
    assert len(encs) >= 1
    assert any(e["patient_id"] == patient_id for e in encs)
