import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.investigation_service import InvestigationService
from app.schemas.clinical_document import (
    InvestigationCreate, InvestigationUpdateResult, InvestigationResponse, InvestigationVerifyRequest
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/investigations", tags=["Clinical Diagnostic Investigations & Test Results"])


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    inv_in: InvestigationCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Order or record a new diagnostic clinical investigation."""
    service = InvestigationService(db)
    return await service.create_investigation(
        patient_id=inv_in.patient_id,
        investigation_type=inv_in.investigation_type,
        test_name=inv_in.test_name,
        encounter_id=inv_in.encounter_id,
        document_id=inv_in.document_id,
        result_summary=inv_in.result_summary,
        result_values=inv_in.result_values,
        is_abnormal=inv_in.is_abnormal,
        abnormal_flags=inv_in.abnormal_flags,
        ordered_by=current_staff.id
    )


@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(
    investigation_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve diagnostic investigation details and structured results by ID."""
    service = InvestigationService(db)
    inv = await service.get_investigation_by_id(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")
    return inv


@router.get("/patient/{patient_id}", response_model=List[InvestigationResponse])
async def list_patient_investigations(
    patient_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """List all diagnostic investigations recorded for a patient."""
    service = InvestigationService(db)
    return await service.list_patient_investigations(patient_id)


@router.get("/encounter/{encounter_id}", response_model=List[InvestigationResponse])
async def list_encounter_investigations(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """List all diagnostic investigations associated with a specific encounter."""
    service = InvestigationService(db)
    return await service.list_encounter_investigations(encounter_id)


@router.post("/{investigation_id}/results", response_model=InvestigationResponse)
async def update_investigation_results(
    investigation_id: str,
    update_in: InvestigationUpdateResult,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Record completed test results and abnormal flags for an investigation."""
    service = InvestigationService(db)
    return await service.record_investigation_results(
        investigation_id=investigation_id,
        result_summary=update_in.result_summary,
        result_values=update_in.result_values,
        is_abnormal=update_in.is_abnormal,
        abnormal_flags=update_in.abnormal_flags,
        status=update_in.status,
        actor_id=current_staff.id
    )


@router.post("/{investigation_id}/verify", response_model=InvestigationResponse)
async def verify_investigation(
    investigation_id: str,
    verify_in: InvestigationVerifyRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "RADIOLOGIST", "LAB_TECH"])),
    db: AsyncSession = Depends(get_db)
):
    """Physician verification of diagnostic test results."""
    service = InvestigationService(db)
    return await service.verify_investigation(
        investigation_id=investigation_id,
        verifier_id=current_staff.id,
        notes=verify_in.notes
    )
