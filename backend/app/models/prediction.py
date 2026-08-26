from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class PredictionRun(Base):
    __tablename__ = "prediction_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"PRD-{uuid.uuid4().hex[:6].upper()}")
    model_name: Mapped[Optional[str]] = mapped_column(String(100), default="SurgeForecaster_v1")
    model_version: Mapped[Optional[str]] = mapped_column(String(50), default="1.0.0")
    prediction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ICU_DEMAND, BED_TURNOVER, ED_SURGE, SURGE_FORECAST
    forecast_horizon_hours: Mapped[int] = mapped_column(Integer, default=2)
    
    predicted_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    unit: Mapped[str] = mapped_column(String(30), default="beds")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85)
    
    input_features: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    prediction_output: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    recommended_action: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    inference_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
