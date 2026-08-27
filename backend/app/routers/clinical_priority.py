import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.clinical_priority_service import ClinicalPriorityService
from app.schemas.priority import (
    PriorityAcknowledgeRequest, PriorityOverrideRequest, PriorityRecommendationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinical-priority", tags=["Clinical Priority & Routing Recommendations"])


@router.post("/{encounter_id}/evaluate", response_model=PriorityRecommendationResponse)
async def evaluate_clinical_priority(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluate/recalculate deterministic clinical priority classification and routing recommendation for an encounter.
    """
    service = ClinicalPriorityService(db)
    return await service.evaluate_priority(encounter_id=encounter_id, actor_id=current_staff.id)


@router.get("/{encounter_id}", response_model=PriorityRecommendationResponse)
@router.get("/{encounter_id}/recommendation", response_model=PriorityRecommendationResponse)
async def get_clinical_priority_recommendation(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve deterministic clinical priority classification and routing recommendation for an encounter.
    Automatically evaluates on demand if not yet generated.
    """
    service = ClinicalPriorityService(db)
    return await service.get_recommendation(encounter_id=encounter_id)


@router.post("/{encounter_id}/acknowledge", response_model=PriorityRecommendationResponse)
async def acknowledge_clinical_priority(
    encounter_id: str,
    ack_in: PriorityAcknowledgeRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Acknowledge clinical priority and routing recommendation by attending medical staff.
    """
    service = ClinicalPriorityService(db)
    return await service.acknowledge_recommendation(
        encounter_id=encounter_id,
        actor_id=current_staff.id,
        notes=ack_in.notes
    )


@router.post("/{encounter_id}/override", response_model=PriorityRecommendationResponse)
async def override_clinical_priority(
    encounter_id: str,
    override_in: PriorityOverrideRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Physician manual override of priority level and routing with mandatory clinical rationale.
    """
    service = ClinicalPriorityService(db)
    return await service.override_recommendation(
        encounter_id=encounter_id,
        actor_id=current_staff.id,
        override_priority=override_in.override_priority,
        override_route=override_in.override_route,
        override_reason=override_in.override_reason
    )
