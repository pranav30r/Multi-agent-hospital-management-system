from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Time, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # DOC-001, NUR-023, TECH-005, REC-001, ADM-001
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)  # DOCTOR, NURSE, CHARGE_NURSE, TECHNICIAN, RECEPTIONIST, ADMINISTRATOR
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    specialization: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")  # AVAILABLE, BUSY, ON_BREAK, ON_LEAVE, OFF_SHIFT, EMERGENCY_ASSIGNED
    current_workload: Mapped[int] = mapped_column(Integer, default=0)
    max_workload: Mapped[int] = mapped_column(Integer, default=5)
    skills: Mapped[Optional[dict]] = mapped_column(JSON, default=list)  # ["ICU_CERTIFIED", "VENTILATOR_TRAINED"]
    password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class StaffShift(Base):
    __tablename__ = "staff_shifts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"SFT-{uuid.uuid4().hex[:6].upper()}")
    staff_id: Mapped[str] = mapped_column(String, ForeignKey("staff.id"), nullable=False)
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    shift_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MORNING, AFTERNOON, NIGHT
    
    start_time: Mapped[str] = mapped_column(String(10), nullable=False)  # "06:00"
    end_time: Mapped[str] = mapped_column(String(10), nullable=False)    # "14:00"
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")  # SCHEDULED, ACTIVE, COMPLETED

class StaffSkill(Base):
    __tablename__ = "staff_skills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"SKL-{uuid.uuid4().hex[:6].upper()}")
    staff_id: Mapped[str] = mapped_column(String, ForeignKey("staff.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(50), nullable=False)
    certification_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
