from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class PriorityAcknowledgeRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Clinical acknowledgement notes")


class PriorityOverrideRequest(BaseModel):
    override_priority: str = Field(..., description="Overridden priority level (CRITICAL, HIGH, MODERATE, ROUTINE)")
    override_route: str = Field(..., description="Overridden routing destination (EMERGENCY_TRIAGE, IMMEDIATE_DOCTOR_REVIEW, NURSE_TRIAGE, STANDARD_OPD_QUEUE, OBSERVATION, DEPARTMENT_REVIEW)")
    override_reason: str = Field(..., min_length=3, description="Justification reason for overriding the system recommendation")


class PriorityRecommendationResponse(BaseModel):
    id: str
    encounter_id: str
    patient_id: str
    assessment_id: Optional[str]
    priority_level: str
    route: str
    score: float
    requires_priority_attention: bool
    reasons: Optional[List[str]] = None
    supporting_factors: Optional[List[str]] = None
    red_flags: Optional[List[Dict[str, Any]]] = None
    missing_information: Optional[List[str]] = None
    status: str
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledgement_notes: Optional[str] = None
    overridden_by: Optional[str] = None
    overridden_at: Optional[datetime] = None
    override_priority_level: Optional[str] = None
    override_route: Optional[str] = None
    override_reason: Optional[str] = None
    generated_by: str
    created_at: datetime
    updated_at: datetime
    version: str

    model_config = ConfigDict(from_attributes=True)
