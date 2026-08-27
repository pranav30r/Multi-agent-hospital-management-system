from datetime import datetime
import uuid
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.datetime_utils import utc_now

class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"PAT-{uuid.uuid4().hex[:6].upper()}")
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    blood_group: Mapped[str] = mapped_column(String(5), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    emergency_contact: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Clinical History
    allergies: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    chronic_conditions: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    encounters: Mapped[List["Encounter"]] = relationship("Encounter", back_populates="patient")

class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"ENC-{uuid.uuid4().hex[:6].upper()}")
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    encounter_type: Mapped[str] = mapped_column(String(20), default="EMERGENCY")  # EMERGENCY, ADMISSION, OPD
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")             # ACTIVE, COMPLETED, CANCELLED
    
    # Current Clinical State
    current_department_id: Mapped[str] = mapped_column(String, nullable=False)
    current_bed_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assigned_doctor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assigned_nurse_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    esi_level: Mapped[int] = mapped_column(Integer, default=3)                    # ESI 1 to 5
    priority: Mapped[int] = mapped_column(Integer, default=3)                     # Priority 1 to 5
    patient_status: Mapped[str] = mapped_column(String(30), default="ARRIVED")
    
    # Intake Vitals
    chief_complaint: Mapped[str] = mapped_column(Text, nullable=False)
    heart_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bp_systolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bp_diastolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spo2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature_f: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pain_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    respiratory_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gcs_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Known conditions & Diagnosis
    diagnosed_diseases: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    diagnosis_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    arrival_time: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    registration_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    triage_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    doctor_assigned_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bed_requested_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bed_reserved_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bed_occupied_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    admission_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    discharge_initiated_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    discharge_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="encounters")
