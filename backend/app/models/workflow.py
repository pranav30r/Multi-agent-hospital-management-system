from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Queue(Base):
    __tablename__ = "queues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"QUE-{uuid.uuid4().hex[:6].upper()}")
    queue_type: Mapped[str] = mapped_column(String(30), nullable=False)  # EMERGENCY_QUEUE, TRIAGE_QUEUE, DOCTOR_QUEUE, ADMISSION_QUEUE, LAB_QUEUE, RADIOLOGY_QUEUE, DISCHARGE_QUEUE
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    
    esi_level: Mapped[int] = mapped_column(Integer, default=3)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="WAITING")  # WAITING, CALLED, COMPLETED, CANCELLED
    
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    estimated_wait_mins: Mapped[int] = mapped_column(Integer, default=15)

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"TSK-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)  # TRIAGE, BED_TRANSFER, LAB_TEST, IMAGING, HANDOFF, DISCHARGE
    
    assigned_to_role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    assigned_to_staff_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_agent: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED, CANCELLED
    priority: Mapped[int] = mapped_column(Integer, default=3)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Admission(Base):
    __tablename__ = "admissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"ADM-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    bed_id: Mapped[str] = mapped_column(String, ForeignKey("beds.id"), nullable=False)
    department_id: Mapped[str] = mapped_column(String, ForeignKey("departments.id"), nullable=False)
    admitting_doctor_id: Mapped[str] = mapped_column(String, ForeignKey("staff.id"), nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="ADMITTED")
    admitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"TRN-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    
    from_department_id: Mapped[str] = mapped_column(String, nullable=False)
    to_department_id: Mapped[str] = mapped_column(String, nullable=False)
    from_bed_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_bed_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED")  # REQUESTED, APPROVED, COMPLETED, CANCELLED
    transferred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Discharge(Base):
    __tablename__ = "discharges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"DSC-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    discharging_doctor_id: Mapped[str] = mapped_column(String, nullable=False)
    
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discharged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# LangGraph / Clinical Workflow Automation Engine
class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # WFD-EMERGENCY-ADMISSION, WFD-OPD-VISIT
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    steps_json: Mapped[dict] = mapped_column(JSON, nullable=False)  # Ordered list of workflow step definitions
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"WFI-{uuid.uuid4().hex[:6].upper()}")
    definition_id: Mapped[str] = mapped_column(String, ForeignKey("workflow_definitions.id"), nullable=False)
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE, COMPLETED, BLOCKED, CANCELLED
    current_step_number: Mapped[int] = mapped_column(Integer, default=1)
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"WFS-{uuid.uuid4().hex[:6].upper()}")
    workflow_instance_id: Mapped[str] = mapped_column(String, ForeignKey("workflow_instances.id"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED, SKIPPED, BLOCKED
    assigned_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
