import pytest
from fastapi import HTTPException
from app.services.prediction_service import PredictionService

@pytest.mark.asyncio
async def test_prediction_service_record_and_run(test_db):
    """Test PredictionService manual recording and automated domain runs."""
    async with test_db() as session:
        service = PredictionService(session)

        # 1. Record prediction run
        recorded = await service.record_prediction_run(
            model_name="SurgeForecaster_v1",
            model_version="1.0.0",
            prediction_type="SURGE_FORECAST",
            input_features={"active_encounters": 8},
            prediction_output={"surge_index": 10.5},
            confidence_score=0.91,
            inference_time_ms=8.5,
            actor_id="DOC-001",
            forecast_horizon_hours=4
        )
        assert recorded.id.startswith("PRD-")
        assert recorded.prediction_type == "SURGE_FORECAST"
        assert recorded.confidence_score == 0.91

        # 2. Automated run for ICU_DEMAND
        icu_run = await service.run_prediction(
            prediction_type="ICU_DEMAND",
            forecast_horizon_hours=2,
            actor_id="DOC-001"
        )
        assert icu_run.prediction_type == "ICU_DEMAND"
        assert icu_run.model_name == "ICUDemandForecaster_v1"
        assert icu_run.recommended_action is not None

        # 3. Automated run for ED_SURGE
        ed_run = await service.run_prediction(
            prediction_type="ED_SURGE",
            forecast_horizon_hours=3,
            actor_id="DOC-001"
        )
        assert ed_run.prediction_type == "ED_SURGE"
        assert ed_run.unit == "patients"

        # 4. Automated run for BED_TURNOVER
        turn_run = await service.run_prediction(
            prediction_type="BED_TURNOVER",
            forecast_horizon_hours=6,
            actor_id="DOC-001"
        )
        assert turn_run.prediction_type == "BED_TURNOVER"
        assert turn_run.unit == "turnovers/day"


@pytest.mark.asyncio
async def test_prediction_service_validations_and_queries(test_db):
    """Test validation errors and historical query metrics."""
    async with test_db() as session:
        service = PredictionService(session)

        # 1. Reject invalid prediction type
        with pytest.raises(HTTPException) as exc_type:
            await service.record_prediction_run(
                model_name="FakeModel",
                model_version="1.0.0",
                prediction_type="INVALID_PREDICTION_TYPE",
                input_features={},
                prediction_output={},
                confidence_score=0.85,
                inference_time_ms=10.0,
                actor_id="DOC-001"
            )
        assert exc_type.value.status_code == 400
        assert "Invalid prediction type" in exc_type.value.detail

        # 2. Reject invalid confidence score
        with pytest.raises(HTTPException) as exc_conf:
            await service.record_prediction_run(
                model_name="SurgeForecaster_v1",
                model_version="1.0.0",
                prediction_type="SURGE_FORECAST",
                input_features={},
                prediction_output={},
                confidence_score=1.5,  # Invalid > 1.0
                inference_time_ms=10.0,
                actor_id="DOC-001"
            )
        assert exc_conf.value.status_code == 400
        assert "Confidence score" in exc_conf.value.detail

        # 3. Reject invalid horizon
        with pytest.raises(HTTPException) as exc_horiz:
            await service.run_prediction(
                prediction_type="ICU_DEMAND",
                forecast_horizon_hours=0,
                actor_id="DOC-001"
            )
        assert exc_horiz.value.status_code == 400
        assert "Forecast horizon" in exc_horiz.value.detail

        # 4. Record valid prediction for query tests
        p_rec = await service.record_prediction_run(
            model_name="SurgeForecaster_v1",
            model_version="1.0.0",
            prediction_type="SURGE_FORECAST",
            input_features={"active_encounters": 5},
            prediction_output={"surge_index": 6.0},
            confidence_score=0.88,
            inference_time_ms=5.0,
            actor_id="DOC-001"
        )
        assert p_rec is not None

        # 5. Get latest predictions
        latest = await service.get_latest_predictions(limit=5)
        assert len(latest) >= 1

        # 6. List history
        history = await service.list_prediction_history(limit=10)
        assert len(history) >= 1

        # 7. Metrics
        metrics = await service.get_prediction_metrics()
        assert metrics["total_runs"] >= 1
        assert metrics["average_confidence"] > 0.0
