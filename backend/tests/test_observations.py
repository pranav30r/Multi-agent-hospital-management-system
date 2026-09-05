import pytest
from httpx import AsyncClient
from app.auth.security import create_access_token


@pytest.mark.asyncio
async def test_record_single_observation_and_query_history(client: AsyncClient):
    """Test creating and retrieving longitudinal vitals measurements for an encounter."""
    token = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Rajesh Sharma",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Register Patient
    p_res = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": "Clinical",
            "last_name": "VitalsTest",
            "age": 52,
            "gender": "M",
            "blood_group": "AB+",
            "contact_phone": "+919812345678",
            "emergency_contact": "+919812345679"
        }
    )
    assert p_res.status_code == 201
    pid = p_res.json()["id"]

    # 2. Create Encounter
    e_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers,
        json={
            "patient_id": pid,
            "chief_complaint": "Acute chest discomfort",
            "current_department_id": "DEP-ER"
        }
    )
    assert e_res.status_code == 201
    eid = e_res.json()["id"]

    # 3. Record Single Observation
    obs_res = await client.post(
        "/api/v1/observations",
        headers=headers,
        json={
            "patient_id": pid,
            "encounter_id": eid,
            "observation_type": "HEART_RATE",
            "value_numeric": 98.0,
            "unit": "bpm",
            "source": "DEVICE"
        }
    )
    assert obs_res.status_code == 201
    obs_data = obs_res.json()
    obs_id = obs_data["id"]
    assert obs_data["observation_type"] == "HEART_RATE"
    assert obs_data["value_numeric"] == 98.0
    assert obs_data["status"] == "ACTIVE"

    # 4. Query Patient Observations
    list_res = await client.get(f"/api/v1/observations/patient/{pid}", headers=headers)
    assert list_res.status_code == 200
    observations = list_res.json()
    assert len(observations) >= 1
    assert any(o["id"] == obs_id for o in observations)


@pytest.mark.asyncio
async def test_batch_vitals_recording_and_latest_summary(client: AsyncClient):
    """Test telemetry device batch recording and latest vitals summary aggregation."""
    token = create_access_token({
        "sub": "NUR-001",
        "role": "NURSE",
        "name": "Nurse One",
        "department_id": "DEP-ICU",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Register Patient & Encounter
    p_res = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": "Telemetry",
            "last_name": "Monitor",
            "age": 60,
            "gender": "F",
            "blood_group": "A+",
            "contact_phone": "+919877788899",
            "emergency_contact": "+919877788800"
        }
    )
    pid = p_res.json()["id"]

    e_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers,
        json={
            "patient_id": pid,
            "chief_complaint": "ICU Cardiac monitoring",
            "current_department_id": "DEP-ICU"
        }
    )
    eid = e_res.json()["id"]

    # Record Batch
    batch_res = await client.post(
        "/api/v1/observations/batch",
        headers=headers,
        json={
            "patient_id": pid,
            "encounter_id": eid,
            "source": "DEVICE",
            "observations": [
                {"observation_type": "HEART_RATE", "value_numeric": 72.0, "unit": "bpm"},
                {"observation_type": "BP_SYSTOLIC", "value_numeric": 120.0, "unit": "mmHg"},
                {"observation_type": "BP_DIASTOLIC", "value_numeric": 80.0, "unit": "mmHg"},
                {"observation_type": "SPO2", "value_numeric": 99.0, "unit": "%"}
            ]
        }
    )
    assert batch_res.status_code == 201
    assert len(batch_res.json()) == 4

    # Query Latest Vitals Summary
    latest_res = await client.get(f"/api/v1/observations/patient/{pid}/latest", headers=headers)
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["patient_id"] == pid
    vitals = latest_data["vitals"]
    assert vitals["HEART_RATE"]["value_numeric"] == 72.0
    assert vitals["BP_SYSTOLIC"]["value_numeric"] == 120.0
    assert vitals["SPO2"]["value_numeric"] == 99.0


@pytest.mark.asyncio
async def test_append_only_observation_correction_workflow(client: AsyncClient):
    """Verify that clinical observation corrections are immutable, preserving historical data."""
    token = create_access_token({
        "sub": "DOC-001",
        "role": "DOCTOR",
        "name": "Dr. Rajesh Sharma",
        "department_id": "DEP-ER",
        "tenant_id": "HOSP-DEFAULT"
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Patient & Encounter
    p_res = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": "Correction",
            "last_name": "AuditCheck",
            "age": 40,
            "gender": "M",
            "blood_group": "O-",
            "contact_phone": "+919866655544",
            "emergency_contact": "+919866655545"
        }
    )
    pid = p_res.json()["id"]

    e_res = await client.post(
        "/api/v1/patients/encounters",
        headers=headers,
        json={
            "patient_id": pid,
            "chief_complaint": "Triage vitals check",
            "current_department_id": "DEP-ER"
        }
    )
    eid = e_res.json()["id"]

    # Initial Observation with Typo (e.g. 198 bpm entered accidentally instead of 98 bpm)
    obs_res = await client.post(
        "/api/v1/observations",
        headers=headers,
        json={
            "patient_id": pid,
            "encounter_id": eid,
            "observation_type": "HEART_RATE",
            "value_numeric": 198.0,
            "unit": "bpm",
            "source": "MANUAL"
        }
    )
    orig_id = obs_res.json()["id"]

    # Submit Correction
    corr_res = await client.post(
        f"/api/v1/observations/{orig_id}/correct",
        headers=headers,
        json={
            "new_value_numeric": 98.0,
            "new_unit": "bpm",
            "reason": "Clinician transcription typo on manual chart intake."
        }
    )
    assert corr_res.status_code == 200
    corr_data = corr_res.json()
    assert corr_data["id"] != orig_id
    assert corr_data["value_numeric"] == 98.0
    assert corr_data["correction_of"] == orig_id
    assert corr_data["status"] == "ACTIVE"
    assert "transcription typo" in corr_data["correction_reason"]
