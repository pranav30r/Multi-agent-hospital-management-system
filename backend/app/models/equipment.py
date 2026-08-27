from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # RES-CT-01, RES-MRI-01, RES-VENT-01
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)  # CT_SCANNER, MRI, XRAY, ULTRASOUND, VENTILATOR, ECG_MACHINE, LAB_ANALYZER, OPERATING_THEATRE
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")  # AVAILABLE, IN_USE, RESERVED, MAINTENANCE, OUT_OF_SERVICE
    slot_duration_mins: Mapped[int] = mapped_column(Integer, default=30)
    current_patient_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_encounter_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class EquipmentBooking(Base):
    __tablename__ = "equipment_bookings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"EQB-{uuid.uuid4().hex[:6].upper()}")
    equipment_id: Mapped[str] = mapped_column(String, ForeignKey("equipment.id"), nullable=False)
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    
    start_time: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")  # SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED
    notes: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
