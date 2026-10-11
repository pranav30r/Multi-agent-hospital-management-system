from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey, JSON, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.datetime_utils import utc_now


class ClinicalObservation(Base):
    """
    Normalized longitudinal clinical observation / vitals entity.
    Provides immutable, time-series clinical measurement tracking with append-only
    correction audit trails and multi-tenant scoping.
    """
    __tablename__ = "clinical_observations"
    __table_args__ = (
        Index("idx_obs_tenant_patient_observed", "tenant_id", "patient_id", "observed_at"),
        Index("idx_obs_tenant_patient_type_observed", "tenant_id", "patient_id", "observation_type", "observed_at"),
    )

    id: Mapped[str] = mapped_column(
        String(50), 
        primary_key=True, 
        default=lambda: f"OBS-{uuid.uuid4().hex[:8].upper()}"
    )
    patient_id: Mapped[str] = mapped_column(String(50), ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str] = mapped_column(String(50), ForeignKey("encounters.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), nullable=False, index=True)

    observation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    source: Mapped[str] = mapped_column(String(30), default="MANUAL", nullable=False)  # MANUAL, DEVICE, INTAKE, IMPORT

    # Append-only correction model
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)  # ACTIVE, CORRECTED, ENTERED_IN_ERROR
    correction_of: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("clinical_observations.id"), nullable=True)
    correction_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
