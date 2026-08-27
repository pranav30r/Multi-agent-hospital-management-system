from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class IntakeSessionCreate(BaseModel):
    patient_id: str = Field(..., example="PAT-001")
    encounter_id: Optional[str] = Field(None, example="ENC-001")
    language: str = Field(default="en", example="en")
    interaction_mode: str = Field(default="TEXT", example="TEXT")  # TEXT, VOICE
    chief_complaint_raw: Optional[str] = Field(None, example="Severe headache and nausea for 2 days")
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

    class Config:
        from_attributes = True


class IntakeResponseSubmit(BaseModel):
    question_id: str = Field(..., example="QST-001")
    raw_response: str = Field(..., example="I have had a high fever since yesterday evening.")
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

    class Config:
        from_attributes = True


class IntakeSessionResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: Optional[str]
    status: str
    language: str
    interaction_mode: str
    chief_complaint_raw: Optional[str]
    total_questions: int
    answered_questions: int
    completion_percentage: float
    structured_summary: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IntakeReviewRequest(BaseModel):
    notes: Optional[str] = Field(None, example="Reviewed and verified pre-consultation intake.")
