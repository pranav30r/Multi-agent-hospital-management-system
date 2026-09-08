import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.clinical_intelligence_service import ClinicalIntelligenceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinical-intelligence", tags=["Clinical Intelligence & Decision Support"])


@router.get("/{encounter_id}")
async def get_clinical_intelligence(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve consolidated clinical intelligence assessment for an encounter.
    Generates assessment deterministically on demand if not yet computed.
    """
    service = ClinicalIntelligenceService(db)
    assessment = await service.get_assessment(encounter_id)
    return {
        "id": assessment.id,
        "encounter_id": assessment.encounter_id,
        "intake_session_id": assessment.intake_session_id,
        "patient_id": assessment.patient_id,
        "severity": assessment.severity,
        "score": assessment.score,
        "requires_priority_attention": assessment.requires_priority_attention,
        "priority_reason": assessment.priority_reason,
        "red_flags": assessment.red_flags or [],
        "reasons": assessment.reasons or [],
        "supporting_factors": assessment.supporting_factors or [],
        "missing_information": assessment.missing_information or [],
        "generated_summary": assessment.generated_summary or {},
        "generated_at": assessment.generated_at,
        "generated_by": assessment.generated_by,
        "version": assessment.version
    }


@router.post("/{encounter_id}/analyze", status_code=status.HTTP_200_OK)
async def analyze_clinical_intelligence(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger/recalculate deterministic clinical intelligence analysis for an encounter.
    """
    service = ClinicalIntelligenceService(db)
    assessment = await service.analyze_encounter(encounter_id, actor_id=current_staff.id)
    return {
        "id": assessment.id,
        "encounter_id": assessment.encounter_id,
        "severity": assessment.severity,
        "score": assessment.score,
        "requires_priority_attention": assessment.requires_priority_attention,
        "priority_reason": assessment.priority_reason,
        "red_flags_count": len(assessment.red_flags or []),
        "generated_at": assessment.generated_at
    }


@router.get("/{encounter_id}/severity")
async def get_clinical_severity(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve explainable severity classification and acuity score breakdown."""
    service = ClinicalIntelligenceService(db)
    return await service.get_severity(encounter_id)


@router.get("/{encounter_id}/red-flags")
async def get_clinical_red_flags(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve detected physiological and symptom red flags for an encounter."""
    service = ClinicalIntelligenceService(db)
    return await service.get_red_flags(encounter_id)


@router.get("/{encounter_id}/summary")
async def get_doctor_clinical_summary(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve structured doctor-facing clinical pre-consultation summary."""
    service = ClinicalIntelligenceService(db)
    return await service.get_summary(encounter_id)
