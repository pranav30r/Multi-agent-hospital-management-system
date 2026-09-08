from datetime import datetime
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.datetime_utils import utc_now


class ClinicalIntakeSession(Base):
    """
    Tracks a patient's clinical intake session lifecycle, language preference,
    interaction mode, progress metrics, and aggregated structured medical history.
    """
    __tablename__ = "clinical_intake_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"INTK-{uuid.uuid4().hex[:6].upper()}")
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("encounters.id"), nullable=True, index=True)
    
    status: Mapped[str] = mapped_column(String(30), default="NOT_STARTED", index=True)  # NOT_STARTED, IN_PROGRESS, COMPLETED, REVIEWED
    language: Mapped[str] = mapped_column(String(10), default="en")                      # en, hi, mr, etc.
    interaction_mode: Mapped[str] = mapped_column(String(20), default="TEXT")            # TEXT, VOICE
    
    chief_complaint_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    answered_questions: Mapped[int] = mapped_column(Integer, default=0)
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Aggregated structured history output for the doctor workflow
    structured_summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    questions: Mapped[List["IntakeQuestion"]] = relationship("IntakeQuestion", back_populates="session", cascade="all, delete-orphan", order_by="IntakeQuestion.order_index")
    responses: Mapped[List["IntakeResponse"]] = relationship("IntakeResponse", back_populates="session", cascade="all, delete-orphan")


class IntakeQuestion(Base):
    """
    Represents an individual clinical question within an intake session,
    supporting typed responses, validation limits, and conditional tree triggers.
    """
    __tablename__ = "intake_questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"QST-{uuid.uuid4().hex[:6].upper()}")
    session_id: Mapped[str] = mapped_column(String, ForeignKey("clinical_intake_sessions.id"), nullable=False, index=True)
    
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # CHIEF_COMPLAINT, SYMPTOMS, DURATION, SEVERITY, LOCATION, PAST_HISTORY, MEDICATIONS, ALLERGIES, FAMILY_HISTORY, LIFESTYLE
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    
    response_type: Mapped[str] = mapped_column(String(30), nullable=False)  # TEXT, NUMBER, BOOLEAN, SINGLE_CHOICE, MULTI_CHOICE, SCALE
    allowed_options: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    scale_min: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    scale_max: Mapped[Optional[int]] = mapped_column(Integer, default=10)
    
    # Conditional branching
    parent_question_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("intake_questions.id"), nullable=True)
    trigger_condition: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # e.g., {"parent_value": True} or {"parent_value": "YES"}
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_answered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    session: Mapped["ClinicalIntakeSession"] = relationship("ClinicalIntakeSession", back_populates="questions")
    responses: Mapped[List["IntakeResponse"]] = relationship("IntakeResponse", back_populates="question", cascade="all, delete-orphan")


class IntakeResponse(Base):
    """
    Stores verbatim raw responses alongside structured parsed data for a clinical question.
    """
    __tablename__ = "intake_responses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"RSP-{uuid.uuid4().hex[:6].upper()}")
    session_id: Mapped[str] = mapped_column(String, ForeignKey("clinical_intake_sessions.id"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String, ForeignKey("intake_questions.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    structured_value: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    response_type: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    session: Mapped["ClinicalIntakeSession"] = relationship("ClinicalIntakeSession", back_populates="responses")
    question: Mapped["IntakeQuestion"] = relationship("IntakeQuestion", back_populates="responses")


class ClinicalAssessment(Base):
    """
    Persisted clinical intelligence assessment combining deterministic rule-based severity scoring,
    red-flag detection, evidence synthesis, and doctor-facing structured clinical summary.
    """
    __tablename__ = "clinical_assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"ASM-{uuid.uuid4().hex[:6].upper()}")
    encounter_id: Mapped[str] = mapped_column(String, ForeignKey("encounters.id"), nullable=False, index=True)
    intake_session_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("clinical_intake_sessions.id"), nullable=True, index=True)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # LOW, MEDIUM, HIGH
    score: Mapped[float] = mapped_column(Float, default=0.0)
    requires_priority_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    red_flags: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    reasons: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    supporting_factors: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    missing_information: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    generated_summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    generated_by: Mapped[str] = mapped_column(String(50), default="SYSTEM")
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
