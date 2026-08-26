import pytest

@pytest.mark.asyncio
async def test_workflow_definition_and_lifecycle(auth_client):
    """Test starting a workflow instance and advancing its steps with authenticated staff."""
    # List definitions
    res = await auth_client.get("/api/v1/workflows/definitions")
    assert res.status_code == 200
    defs = res.json()
    assert len(defs) == 3

    # Start instance
    start_payload = {
        "workflow_definition_id": "WFD-EMERGENCY-ADMISSION",
        "encounter_id": "ENC-TEST-WF",
        "patient_id": "PAT-TEST-WF"
    }
    start_res = await auth_client.post("/api/v1/workflows/instances", json=start_payload)
    assert start_res.status_code == 201
    instance = start_res.json()
    assert instance["current_step_number"] == 1
    assert instance["current_step_name"] == "Registration"
    instance_id = instance["id"]

    # Advance to step 2 (ESI Triage Assessment)
    adv_res = await auth_client.post(
        f"/api/v1/workflows/instances/{instance_id}/advance",
        json={"notes": "Registration verified"}
    )
    assert adv_res.status_code == 200
    adv_data = adv_res.json()
    assert adv_data["current_step_number"] == 2
    assert adv_data["current_step_name"] == "ESI Triage Assessment"


@pytest.mark.asyncio
async def test_predictions_record_and_metrics(auth_client):
    """Test recording a model inference run and querying metrics with authenticated staff."""
    # Record prediction
    pred_payload = {
        "model_name": "SurgeForecaster_v1",
        "model_version": "1.0.0",
        "prediction_type": "SURGE_FORECAST",
        "input_features": {"current_er_occupancy": 5, "active_emergencies": 1},
        "prediction_output": {"forecasted_admissions_next_2h": 8, "risk_level": "HIGH"},
        "confidence_score": 0.92,
        "inference_time_ms": 14.5
    }
    rec_res = await auth_client.post("/api/v1/predictions/record", json=pred_payload)
    assert rec_res.status_code == 201
    pred = rec_res.json()
    assert pred["model_name"] == "SurgeForecaster_v1"
    assert pred["confidence_score"] == 0.92

    # Query latest
    latest_res = await auth_client.get("/api/v1/predictions/latest?prediction_type=SURGE_FORECAST")
    assert latest_res.status_code == 200
    assert len(latest_res.json()) >= 1

    # Query metrics
    metrics_res = await auth_client.get("/api/v1/predictions/metrics")
    assert metrics_res.status_code == 200
    m = metrics_res.json()
    assert m["total_runs"] >= 1
    assert m["average_confidence"] > 0.0
