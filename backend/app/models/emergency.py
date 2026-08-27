from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"EMR-{uuid.uuid4().hex[:6].upper()}")
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # MASS_CASUALTY, PANDEMIC_SURGE, INFRASTRUCTURE_FAILURE, STAFF_CRISIS
    severity: Mapped[str] = mapped_column(String(20), default="HIGH")     # HIGH, CRITICAL
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    affected_departments: Mapped[dict] = mapped_column(JSON, default=list)  # ["DEP-ER", "DEP-ICU"]
    expected_patient_surge: Mapped[int] = mapped_column(Integer, default=5)
    declared_by: Mapped[str] = mapped_column(String, nullable=False, default="ADM-001")
    
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")    # ACTIVE, RESOLVED, ESCALATED
    declared_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
