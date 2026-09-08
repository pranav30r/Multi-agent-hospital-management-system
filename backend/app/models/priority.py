from datetime import datetime
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now


class ClinicalPriorityRecommendation(Base):
    """
    Domain entity representing deterministic clinical priority classification and operational
    routing recommendations (e.g. EMERGENCY_TRIAGE, IMMEDIATE_DOCTOR_REVIEW, NURSE_TRIAGE).
    Maintains complete explainability and physician acknowledgement/override audit trails.
    """
    __tablename__ = "clinical_priority_recommendations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"PR-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    assessment_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("clinical_assessments.id"), nullable=True, index=True)

    priority_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # CRITICAL, HIGH, MODERATE, ROUTINE
    route: Mapped[str] = mapped_column(String(50), nullable=False, index=True)            # EMERGENCY_TRIAGE, IMMEDIATE_DOCTOR_REVIEW, NURSE_TRIAGE, STANDARD_OPD_QUEUE, OBSERVATION, DEPARTMENT_REVIEW
    score: Mapped[float] = mapped_column(Float, default=0.0)
    requires_priority_attention: Mapped[bool] = mapped_column(Boolean, default=False)

    reasons: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    supporting_factors: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    red_flags: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    missing_information: Mapped[Optional[dict]] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(30), default="GENERATED", index=True)      # GENERATED, ACKNOWLEDGED, OVERRIDDEN, EXPIRED

    acknowledged_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledgement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    overridden_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overridden_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    override_priority_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    override_route: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    generated_by: Mapped[str] = mapped_column(String(50), default="SYSTEM")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
