import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff, get_current_tenant
from app.services.clinical_intelligence_service import ClinicalIntelligenceService
from app.services.intelligence_engine_service import IntelligenceEngineService
from app.schemas.intelligence import (
    IntelligenceExecutionRequest,
    IntelligenceDecisionResponse,
    AgentMessageResponse,
    OptimizationRunResponse
)
from app.schemas.hospital_workflow import HospitalWorkflowState

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


@router.post("/{encounter_id}/workflow-coordinate", response_model=HospitalWorkflowState, status_code=status.HTTP_200_OK)
async def coordinate_hospital_workflow(
    encounter_id: str,
    req: Optional[IntelligenceExecutionRequest] = None,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Executes the unified hospital multi-agent workflow coordinator.
    Invokes Triage -> Patient Flow -> Bed Matching -> Workforce -> Escalation in defined order,
    passes typed structured state, handles failures/conflicts, and enforces human-in-the-loop review.
    """
    from app.services.hospital_workflow_coordinator import HospitalWorkflowCoordinator
    coordinator = HospitalWorkflowCoordinator(db)
    trigger_reason = req.trigger_reason if req else None
    force_recalc = req.force_recalculate if req else False

    return await coordinator.coordinate_workflow(
        encounter_id=encounter_id,
        tenant_id=tenant_id,
        actor_id=current_staff.id,
        force_recalculate=force_recalc,
        trigger_reason=trigger_reason
    )


@router.post("/{encounter_id}/decide", response_model=IntelligenceDecisionResponse, status_code=status.HTTP_200_OK)
@router.post("/{encounter_id}/orchestrate", response_model=IntelligenceDecisionResponse, status_code=status.HTTP_200_OK)
async def execute_clinical_intelligence_decision(
    encounter_id: str,
    req: Optional[IntelligenceExecutionRequest] = None,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute cooperative multi-agent workflow evaluation for an encounter.
    Orchestrates Triage, Bed, and Staff agents under Coordinator synthesis.
    Produces structured decision records and routes consequential recommendations to the
    Human Review / Approval queue without mutating critical resources directly.
    """
    engine_service = IntelligenceEngineService(db)
    trigger_reason = req.trigger_reason if req else None
    force_recalc = req.force_recalculate if req else False

    decision_res = await engine_service.execute_intelligence(
        encounter_id=encounter_id,
        trigger_reason=trigger_reason,
        force_recalculate=force_recalc,
        actor_id=current_staff.id,
        tenant_id=tenant_id
    )
    return decision_res


@router.get("/{encounter_id}/messages", response_model=List[AgentMessageResponse])
async def get_encounter_agent_messages(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all structured inter-agent messages exchanged during multi-agent orchestration for an encounter."""
    engine_service = IntelligenceEngineService(db)
    return await engine_service.get_messages_for_encounter(encounter_id)


@router.get("/{encounter_id}/optimization-run", response_model=OptimizationRunResponse)
async def get_encounter_optimization_run(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the multi-objective candidate optimization run produced for an encounter."""
    engine_service = IntelligenceEngineService(db)
    opt_run = await engine_service.get_optimization_run(encounter_id)
    if not opt_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No optimization run found for encounter {encounter_id}")
    return opt_run
