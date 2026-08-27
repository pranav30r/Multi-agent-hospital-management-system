import logging
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediction import PredictionRun
from app.models.bed import Bed
from app.models.patient import Encounter
from app.models.staff import Staff
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

VALID_PREDICTION_TYPES = {
    "ICU_DEMAND",
    "BED_TURNOVER",
    "ED_SURGE",
    "SURGE_FORECAST",
    "LENGTH_OF_STAY",
    "MORTALITY_RISK",
    "ICU_BED_DEMAND"
}


class PredictionService:
    """
    Application Service for Operational Forecasting, ML Model Inferences, and Hospital Telemetry.
    Encapsulates predictive runs, historical lookups, confidence telemetry, and operational recommendations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 1. Run & Record Predictions ────────────────────────────────────────

    async def record_prediction_run(
        self,
        model_name: str,
        model_version: str,
        prediction_type: str,
        input_features: Dict[str, Any],
        prediction_output: Dict[str, Any],
        confidence_score: float,
        inference_time_ms: float,
        actor_id: str,
        forecast_horizon_hours: int = 2,
        predicted_value: Optional[float] = None,
        unit: str = "beds",
        recommended_action: Optional[str] = None,
        target_date: Optional[datetime] = None
    ) -> PredictionRun:
        """
        Persist an inference result from the prediction engine or AI agents with audit logging.
        """
        type_clean = prediction_type.upper()
        if type_clean not in VALID_PREDICTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prediction type '{prediction_type}'. Valid types: {sorted(list(VALID_PREDICTION_TYPES))}"
            )

        if not (0.0 <= confidence_score <= 1.0):
            raise HTTPException(status_code=400, detail="Confidence score must be between 0.0 and 1.0")

        if forecast_horizon_hours <= 0:
            raise HTTPException(status_code=400, detail="Forecast horizon hours must be greater than 0")

        prediction = PredictionRun(
            model_name=model_name,
            model_version=model_version,
            prediction_type=type_clean,
            forecast_horizon_hours=forecast_horizon_hours,
            predicted_value=predicted_value if predicted_value is not None else float(prediction_output.get("predicted_value", 0.0)),
            unit=unit,
            confidence_score=confidence_score,
            input_features=input_features,
            prediction_output=prediction_output,
            recommended_action=recommended_action or prediction_output.get("recommended_action"),
            inference_time_ms=inference_time_ms,
            target_date=target_date or datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        self.db.add(prediction)
        await self.db.flush()

        audit = AuditLog(
            entity_type="prediction",
            entity_id=prediction.id,
            field_changed="inference",
            old_value=None,
            new_value=type_clean,
            changed_by=actor_id,
            change_reason=f"Recorded model inference for {model_name} (confidence {confidence_score})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(prediction)
        logger.info(f"Prediction recorded: {prediction.id} ({model_name} / {type_clean}) by {actor_id}")
        return prediction

    async def run_prediction(
        self,
        prediction_type: str,
        forecast_horizon_hours: int = 2,
        department_id: Optional[str] = None,
        actor_id: str = "SYSTEM"
    ) -> PredictionRun:
        """
        Execute an automated operational forecast against real-time hospital database state.
        """
        type_clean = prediction_type.upper()
        if type_clean not in VALID_PREDICTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prediction type '{prediction_type}'. Valid types: {sorted(list(VALID_PREDICTION_TYPES))}"
            )

        if forecast_horizon_hours <= 0:
            raise HTTPException(status_code=400, detail="Forecast horizon must be greater than 0 hours")

        start_time = time.perf_counter()

        # Query live database features
        active_enc_res = await self.db.execute(
            select(func.count(Encounter.id)).where(Encounter.status == "ACTIVE")
        )
        active_encounters = active_enc_res.scalar() or 0

        occupied_beds_res = await self.db.execute(
            select(func.count(Bed.id)).where(Bed.status == "OCCUPIED")
        )
        occupied_beds = occupied_beds_res.scalar() or 0

        available_beds_res = await self.db.execute(
            select(func.count(Bed.id)).where(Bed.status == "AVAILABLE")
        )
        available_beds = available_beds_res.scalar() or 0

        # Execute deterministic domain forecast logic based on type
        if type_clean in ["ICU_DEMAND", "ICU_BED_DEMAND"]:
            icu_occ_res = await self.db.execute(
                select(func.count(Bed.id)).where(Bed.department_id == "DEP-ICU", Bed.status == "OCCUPIED")
            )
            icu_occupied = icu_occ_res.scalar() or 0
            predicted_val = round(icu_occupied * 1.15 + (active_encounters * 0.1), 1)
            unit = "beds"
            recommendation = f"Prepare {max(1, int(predicted_val - icu_occupied))} additional ICU beds for {forecast_horizon_hours}h horizon"
            features = {"current_icu_occupied": icu_occupied, "active_hospital_encounters": active_encounters}
            output = {"predicted_icu_demand": predicted_val, "urgency": "HIGH" if predicted_val > 6 else "MEDIUM"}
            confidence = 0.88
            model_name = "ICUDemandForecaster_v1"

        elif type_clean == "ED_SURGE":
            er_enc_res = await self.db.execute(
                select(func.count(Encounter.id)).where(Encounter.current_department_id == "DEP-ER", Encounter.status == "ACTIVE")
            )
            er_active = er_enc_res.scalar() or 0
            predicted_val = float(er_active + (2 * forecast_horizon_hours))
            unit = "patients"
            recommendation = f"Monitor ED triage arrival queues; forecasted surge of {int(predicted_val)} patients"
            features = {"current_er_active": er_active, "forecast_horizon_hours": forecast_horizon_hours}
            output = {"expected_er_surge": predicted_val, "surge_level": "MODERATE" if predicted_val < 15 else "HIGH"}
            confidence = 0.85
            model_name = "EDSurgePredictor_v1"

        elif type_clean == "BED_TURNOVER":
            predicted_val = round(occupied_beds * 0.25, 1)
            unit = "turnovers/day"
            recommendation = f"Anticipate {int(predicted_val)} bed turnovers across wards within {forecast_horizon_hours}h"
            features = {"occupied_beds": occupied_beds, "available_beds": available_beds}
            output = {"predicted_turnover_rate": predicted_val}
            confidence = 0.82
            model_name = "BedTurnoverEstimator_v1"

        else:  # SURGE_FORECAST / LENGTH_OF_STAY / MORTALITY_RISK
            predicted_val = round(active_encounters * 1.2, 1)
            unit = "surge_index"
            recommendation = "Hospital operational load normal; maintain standard bed reservation workflow"
            features = {"active_encounters": active_encounters, "total_occupied_beds": occupied_beds}
            output = {"surge_index": predicted_val}
            confidence = 0.89
            model_name = "SurgeForecaster_v1"

        inference_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return await self.record_prediction_run(
            model_name=model_name,
            model_version="1.0.0",
            prediction_type=type_clean,
            input_features=features,
            prediction_output=output,
            confidence_score=confidence,
            inference_time_ms=inference_ms,
            actor_id=actor_id,
            forecast_horizon_hours=forecast_horizon_hours,
            predicted_value=predicted_val,
            unit=unit,
            recommended_action=recommendation,
            target_date=datetime.utcnow() + timedelta(hours=forecast_horizon_hours)
        )

    # ─── 2. Query & History Operations ──────────────────────────────────────

    async def get_prediction_by_id(self, prediction_id: str) -> Optional[PredictionRun]:
        """Retrieve a specific prediction record by ID."""
        result = await self.db.execute(select(PredictionRun).where(PredictionRun.id == prediction_id))
        return result.scalars().first()

    async def get_latest_predictions(
        self,
        prediction_type: Optional[str] = None,
        limit: int = 5
    ) -> List[PredictionRun]:
        """Retrieve most recent prediction runs for real-time dashboard telemetry."""
        query = select(PredictionRun)
        if prediction_type:
            query = query.where(PredictionRun.prediction_type == prediction_type.upper())
        query = query.order_by(desc(PredictionRun.created_at)).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_prediction_history(
        self,
        model_name: Optional[str] = None,
        prediction_type: Optional[str] = None,
        limit: int = 50
    ) -> List[PredictionRun]:
        """Query historical model prediction runs with optional filters."""
        query = select(PredictionRun)
        if model_name:
            query = query.where(PredictionRun.model_name == model_name)
        if prediction_type:
            query = query.where(PredictionRun.prediction_type == prediction_type.upper())
        query = query.order_by(desc(PredictionRun.created_at)).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_prediction_metrics(self) -> Dict[str, Any]:
        """Summary statistics for prediction models (total runs, average confidence, latency, active models)."""
        result = await self.db.execute(select(PredictionRun))
        runs = result.scalars().all()

        if not runs:
            return {
                "total_runs": 0,
                "average_confidence": 0.0,
                "average_inference_ms": 0.0,
                "models_active": []
            }

        total_conf = sum(r.confidence_score for r in runs)
        total_time = sum(r.inference_time_ms or 0.0 for r in runs)
        models = list({r.model_name for r in runs if r.model_name})

        return {
            "total_runs": len(runs),
            "average_confidence": round(total_conf / len(runs), 3),
            "average_inference_ms": round(total_time / len(runs), 2),
            "models_active": models
        }
