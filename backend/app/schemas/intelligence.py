from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


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
    created_at: datetime

    class Config:
        from_attributes = True


class ClinicalIntelligenceAssessmentResponse(BaseModel):
    id: str
    encounter_id: str
    intake_session_id: Optional[str]
    patient_id: str
    severity: str
    score: float
    requires_priority_attention: bool
    priority_reason: Optional[str]
    red_flags: List[Dict[str, Any]]
    reasons: List[str]
    supporting_factors: List[str]
    missing_information: List[str]
    generated_summary: Dict[str, Any]
    generated_at: datetime
    generated_by: str
    version: str

    class Config:
        from_attributes = True
