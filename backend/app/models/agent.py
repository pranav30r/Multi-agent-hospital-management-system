from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.datetime_utils import utc_now

class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"DEC-{uuid.uuid4().hex[:6].upper()}")
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)  # triage_agent, bed_agent, etc.
    event_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    encounter_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("encounters.id"), nullable=True)
    
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # SUGGEST_TRIAGE_PRIORITY, RECOMMEND_BED, REASSIGN_STAFF
    proposed_action: Mapped[dict] = mapped_column(JSON, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.90)
    alternatives: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    
    risk_level: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # LOW, MEDIUM, HIGH
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")     # PROPOSED, APPROVED, MODIFIED, REJECTED, EXPIRED
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"MSG-{uuid.uuid4().hex[:6].upper()}")
    sender_agent: Mapped[str] = mapped_column(String(50), nullable=False)
    receiver_agent: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    encounter_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    message_type: Mapped[str] = mapped_column(String(20), default="INFORM")  # REQUEST, INFORM, ALERT, RESPONSE
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default="DELIVERED")    # SENT, DELIVERED, READ, RESPONDED
    response_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"OPT-{uuid.uuid4().hex[:6].upper()}")
    trigger_event_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)  # BED_ASSIGNMENT, STAFF_REASSIGNMENT, SURGE_RESPONSE
    encounter_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    agents_involved: Mapped[dict] = mapped_column(JSON, default=list)
    candidates_count: Mapped[int] = mapped_column(Integer, default=3)
    candidates: Mapped[dict] = mapped_column(JSON, default=list)
    
    selected_plan_index: Mapped[int] = mapped_column(Integer, default=0)
    selected_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    
    objective_score: Mapped[float] = mapped_column(Float, default=0.85)
    waiting_time_score: Mapped[float] = mapped_column(Float, default=0.85)
    resource_util_score: Mapped[float] = mapped_column(Float, default=0.85)
    staff_balance_score: Mapped[float] = mapped_column(Float, default=0.85)
    constraint_violations: Mapped[int] = mapped_column(Integer, default=0)
    hard_constraint_pass: Mapped[bool] = mapped_column(Boolean, default=True)
    
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    computation_time_ms: Mapped[int] = mapped_column(Integer, default=25)

class CrewRun(Base):
    __tablename__ = "crew_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"CRW-{uuid.uuid4().hex[:6].upper()}")
    crew_name: Mapped[str] = mapped_column(String(50), nullable=False)  # EmergencySurgeCrew
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False)
    agents_count: Mapped[int] = mapped_column(Integer, default=3)
    tasks_count: Mapped[int] = mapped_column(Integer, default=3)
    
    output_summary: Mapped[Text] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class LangGraphCheckpoint(Base):
    __tablename__ = "langgraph_checkpoints"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"CKP-{uuid.uuid4().hex[:6].upper()}")
    thread_id: Mapped[str] = mapped_column(String, nullable=False)  # Encounter ID or Session ID
    node_name: Mapped[str] = mapped_column(String(50), nullable=False)
    state_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class ApprovalItem(Base):
    __tablename__ = "approval_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"APR-{uuid.uuid4().hex[:6].upper()}")
    decision_id: Mapped[str] = mapped_column(String, ForeignKey("agent_decisions.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    
    proposed_action: Mapped[dict] = mapped_column(JSON, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, APPROVED, MODIFIED, REJECTED, EXPIRED
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    review_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # APPROVE, MODIFY, REJECT
    modification: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"AUD-{uuid.uuid4().hex[:6].upper()}")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # patient, bed, staff, resource
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    
    field_changed: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    changed_by: Mapped[str] = mapped_column(String, nullable=False)  # Agent ID, Staff ID, or SYSTEM
    change_reason: Mapped[str] = mapped_column(String(200), nullable=False)
    decision_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approval_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
