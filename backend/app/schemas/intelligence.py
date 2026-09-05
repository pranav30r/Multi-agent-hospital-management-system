from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class IntelligenceExecutionRequest(BaseModel):
    trigger_reason: Optional[str] = Field(
        None,
        description="Reason for triggering clinical intelligence evaluation (e.g., TRIAGE_COMPLETION, VITALS_UPDATE)"
    )
    context_notes: Optional[str] = Field(
        None,
        description="Optional clinician notes or context"
    )
    force_recalculate: bool = Field(
        False,
        description="Force recalculation even if an active decision exists"
    )


class AgentMessageResponse(BaseModel):
    id: str
    sender_agent: str
    receiver_agent: str
    encounter_id: Optional[str] = None
    message_type: str
    subject: str
    payload: Dict[str, Any]
    status: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidatePlanSummary(BaseModel):
    plan_index: int
    plan_type: str
    care_level: str
    target_bed_id: Optional[str] = None
    target_department_id: Optional[str] = None
    assigned_doctor_id: Optional[str] = None
    assigned_nurse_id: Optional[str] = None
    objective_score: float
    waiting_time_score: float
    resource_util_score: float
    staff_balance_score: float
    hard_constraint_pass: bool
    description: str


class OptimizationRunResponse(BaseModel):
    id: str
    encounter_id: Optional[str] = None
    trigger_type: str
    agents_involved: List[str]
    candidates_count: int
    candidates: List[Dict[str, Any]]
    selected_plan_index: int
    selected_plan: Dict[str, Any]
    objective_score: float
    waiting_time_score: float
    resource_util_score: float
    staff_balance_score: float
    constraint_violations: int
    hard_constraint_pass: bool
    status: str
    computation_time_ms: int
    started_at: datetime
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntelligenceDecisionResponse(BaseModel):
    id: str
    encounter_id: str
    patient_id: str
    agent_id: str
    action_type: str
    risk_level: str
    confidence: float
    proposed_action: Dict[str, Any]
    reasoning: str
    requires_human_approval: bool
    approval_item_id: Optional[str] = None
    status: str
    optimization_run_id: Optional[str] = None
    selected_plan: Optional[Dict[str, Any]] = None
    candidate_plans: Optional[List[Dict[str, Any]]] = None
    conflicts: Optional[List[Dict[str, Any]]] = None
    agent_messages_count: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClinicalIntelligenceAssessmentResponse(BaseModel):
    id: str
    encounter_id: str
    intake_session_id: Optional[str] = None
    patient_id: str
    severity: str
    score: float
    requires_priority_attention: bool
    priority_reason: Optional[str] = None
    red_flags: List[Dict[str, Any]]
    reasons: List[str]
    supporting_factors: List[str]
    missing_information: List[str]
    generated_summary: Dict[str, Any]
    generated_at: datetime
    generated_by: str
    version: str

    model_config = ConfigDict(from_attributes=True)
