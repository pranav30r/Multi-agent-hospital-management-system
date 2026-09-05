from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class IntakeSessionCreate(BaseModel):
    patient_id: str = Field(..., description="Target patient ID")
    encounter_id: Optional[str] = Field(None, description="Active encounter ID")
    language: str = Field(default="en", description="Intake language code")
    interaction_mode: str = Field(default="TEXT", description="TEXT or VOICE")
    chief_complaint_raw: Optional[str] = Field(None, description="Verbatim raw chief complaint")
    custom_questions: Optional[List[Dict[str, Any]]] = None


class IntakeQuestionResponse(BaseModel):
    id: str
    session_id: str
    question_text: str
    category: str
    order_index: int
    is_required: bool
    response_type: str
    allowed_options: Optional[List[Any]] = None
    scale_min: Optional[int] = 1
    scale_max: Optional[int] = 10
    parent_question_id: Optional[str] = None
    is_active: bool
    is_answered: bool
    is_skipped: bool

    model_config = ConfigDict(from_attributes=True)


class IntakeResponseSubmit(BaseModel):
    question_id: str = Field(..., description="Target question ID")
    raw_response: str = Field(..., description="Patient raw text/voice transcription")
    structured_value: Optional[Dict[str, Any]] = Field(default_factory=dict)


class IntakeResponseModel(BaseModel):
    id: str
    session_id: str
    question_id: str
    patient_id: str
    raw_response: str
    structured_value: Optional[Dict[str, Any]] = None
    response_type: str
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeSessionResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: Optional[str] = None
    status: str
    language: str
    interaction_mode: str
    chief_complaint_raw: Optional[str] = None
    total_questions: int
    answered_questions: int
    completion_percentage: float
    structured_summary: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeReviewRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Review notes")
