from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Bed(Base):
    __tablename__ = "beds"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # BED-ICU-01, BED-ER-02
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    bed_type: Mapped[str] = mapped_column(String(30), nullable=False)  # ICU, EMERGENCY, GENERAL, ISOLATION, CARDIAC_MONITOR
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE") # AVAILABLE, RESERVED, OCCUPIED, CLEANING, MAINTENANCE, BLOCKED
    
    is_isolation: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ventilator: Mapped[bool] = mapped_column(Boolean, default=False)
    has_telemetry: Mapped[bool] = mapped_column(Boolean, default=False)
    
    current_patient_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_encounter_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_cleaned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class BedAssignment(Base):
    __tablename__ = "bed_assignments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"BAS-{uuid.uuid4().hex[:6].upper()}")
    bed_id: Mapped[str] = mapped_column(String, ForeignKey("beds.id"), nullable=False)
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    
    assigned_by: Mapped[str] = mapped_column(String, nullable=False)  # Agent ID or Staff ID
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    
    reserved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    occupied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")  # RESERVED, OCCUPIED, RELEASED, CANCELLED
