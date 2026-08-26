from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class EmergencyDeclareRequest(BaseModel):
    name: str = Field(..., example="Mass Casualty Incident - Highway Accident")
    emergency_type: str = Field(..., example="MASS_CASUALTY")
    declared_by: str = Field(default="ADM-001")
    affected_departments: List[str] = Field(default=["DEP-ER", "DEP-ICU", "DEP-SUR"])
    notes: Optional[str] = None

class EmergencyResponse(BaseModel):
    id: str
    name: str
    emergency_type: str
    status: str
    severity_level: int
    declared_at: datetime
    resolved_at: Optional[datetime]
    declared_by: str
    affected_departments: List[str]
    notes: Optional[str]

    class Config:
        from_attributes = True

class ApprovalItemResponse(BaseModel):
    id: str
    decision_id: str
    agent_id: str
    recommendation_type: str
    patient_id: Optional[str]
    encounter_id: Optional[str]
    risk_level: str
    proposed_payload: Dict[str, Any]
    status: str
    human_notes: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class ApprovalReviewRequest(BaseModel):
    action: str = Field(..., example="APPROVE")  # APPROVE, MODIFY, REJECT
    reviewed_by: str = Field(default="DOC-001")
    modified_payload: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
