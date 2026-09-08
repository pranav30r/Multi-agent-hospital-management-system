import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.clinical_intake_service import ClinicalIntakeService
from app.schemas.intake import (
    IntakeSessionCreate, IntakeSessionResponse,
    IntakeQuestionResponse, IntakeResponseSubmit, IntakeResponseModel,
    IntakeReviewRequest
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinical-intakes", tags=["Clinical Intake & Patient Medical History"])


@router.post("", response_model=IntakeSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_clinical_intake(
    session_in: IntakeSessionCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a structured clinical intake session for a patient with foundational clinical questions.
    """
    service = ClinicalIntakeService(db)
    return await service.start_intake_session(
        patient_id=session_in.patient_id,
        encounter_id=session_in.encounter_id,
        language=session_in.language,
        interaction_mode=session_in.interaction_mode,
        chief_complaint_raw=session_in.chief_complaint_raw,
        custom_questions=session_in.custom_questions,
        actor_id=current_staff.id
    )


@router.get("/{session_id}", response_model=IntakeSessionResponse)
async def get_clinical_intake_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get clinical intake session metadata and progress metrics."""
    service = ClinicalIntakeService(db)
    session = await service.get_intake_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Clinical intake session {session_id} not found")
    return session


@router.get("/{session_id}/current-question", response_model=Optional[IntakeQuestionResponse])
async def get_current_intake_question(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the next unanswered active question in sequence, automatically evaluating conditional branch triggers.
    """
    service = ClinicalIntakeService(db)
    return await service.get_current_question(session_id)


@router.post("/{session_id}/responses", response_model=IntakeResponseModel, status_code=status.HTTP_201_CREATED)
async def submit_intake_response(
    session_id: str,
    resp_in: IntakeResponseSubmit,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a patient response for a specific intake question with type validation and progress recalculation.
    """
    service = ClinicalIntakeService(db)
    return await service.submit_response(
        session_id=session_id,
        question_id=resp_in.question_id,
        raw_response=resp_in.raw_response,
        structured_value=resp_in.structured_value,
        actor_id=current_staff.id
    )


@router.post("/{session_id}/questions/{question_id}/skip", response_model=IntakeQuestionResponse)
async def skip_optional_intake_question(
    session_id: str,
    question_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Skip an optional question in the clinical intake sequence.
    """
    service = ClinicalIntakeService(db)
    return await service.skip_question(
        session_id=session_id,
        question_id=question_id,
        actor_id=current_staff.id
    )


@router.post("/{session_id}/complete", response_model=IntakeSessionResponse)
async def complete_clinical_intake(
    session_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Finalize the intake session and synthesize structured clinical history once all required questions are answered.
    """
    service = ClinicalIntakeService(db)
    return await service.complete_intake_session(
        session_id=session_id,
        actor_id=current_staff.id
    )


@router.post("/{session_id}/review", response_model=IntakeSessionResponse)
async def review_clinical_intake(
    session_id: str,
    review_in: IntakeReviewRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Physician review of the completed clinical intake before consultation.
    """
    service = ClinicalIntakeService(db)
    return await service.review_intake_session(
        session_id=session_id,
        reviewer_id=current_staff.id,
        notes=review_in.notes
    )


@router.get("/doctor-view/{encounter_id}")
async def get_doctor_clinical_view(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Consolidated clinical pre-consultation view for doctors:
    Patient + Encounter Vitals + Completed Clinical Intake + Structured History + Previous Visits.
    """
    service = ClinicalIntakeService(db)
    return await service.get_doctor_clinical_view(encounter_id)


@router.get("/encounter/{encounter_id}", response_model=Optional[IntakeSessionResponse])
async def get_intake_by_encounter(
    encounter_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the clinical intake session associated with a specific encounter."""
    service = ClinicalIntakeService(db)
    session = await service.get_intake_by_encounter(encounter_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No clinical intake found for encounter {encounter_id}")
    return session


@router.get("/timeline/{patient_id}")
async def get_patient_clinical_timeline(
    patient_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve full chronological medical timeline for a patient."""
    service = ClinicalIntakeService(db)
    return await service.get_patient_timeline(patient_id)


@router.get("/{session_id}/structured")
async def get_structured_clinical_intake(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve formatted structured pre-consultation medical history for physician workflows.
    """
    service = ClinicalIntakeService(db)
    return await service.get_structured_intake(session_id)


@router.get("/patient/{patient_id}", response_model=List[IntakeSessionResponse])
async def list_patient_intake_sessions(
    patient_id: str,
    db: AsyncSession = Depends(get_db)
):
    """List historical clinical intake sessions for a patient."""
    service = ClinicalIntakeService(db)
    return await service.list_patient_intakes(patient_id)
