import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import get_current_staff, get_current_tenant, require_roles
from app.schemas.observation import (
    ObservationCreate, ObservationBatchCreate, ObservationCorrectionRequest,
    ObservationResponse, LatestVitalsResponse
)
from app.services.observation_service import ObservationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/observations", tags=["Longitudinal Clinical Observations"])


@router.post("", response_model=ObservationResponse, status_code=status.HTTP_201_CREATED)
async def record_observation(
    req: ObservationCreate,
    current_staff: Staff = Depends(require_roles(["DOCTOR", "NURSE", "CHARGE_NURSE", "TECHNICIAN", "ADMINISTRATOR"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Record a single clinical observation / vital measurement.
    Strictly tenant-scoped with append-only audit trail.
    """
    service = ObservationService(db)
    return await service.record_observation(req=req, tenant_id=tenant_id, actor_id=current_staff.id)


@router.post("/batch", response_model=List[ObservationResponse], status_code=status.HTTP_201_CREATED)
async def record_batch_observations(
    req: ObservationBatchCreate,
    current_staff: Staff = Depends(require_roles(["DOCTOR", "NURSE", "CHARGE_NURSE", "TECHNICIAN", "ADMINISTRATOR"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Record a batch of clinical observations (e.g. from monitoring devices or bulk intake).
    """
    service = ObservationService(db)
    return await service.record_batch(req=req, tenant_id=tenant_id, actor_id=current_staff.id)


@router.get("/patient/{patient_id}", response_model=List[ObservationResponse])
async def get_patient_observations(
    patient_id: str,
    observation_type: Optional[str] = Query(None, description="Filter by vital/observation type (e.g. HEART_RATE)"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    before: Optional[datetime] = Query(None, description="Cursor timestamp for pagination"),
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve longitudinal clinical observation history for a patient.
    """
    service = ObservationService(db)
    return await service.get_patient_observations(
        patient_id=patient_id,
        tenant_id=tenant_id,
        observation_type=observation_type,
        limit=limit,
        before_timestamp=before
    )


@router.get("/patient/{patient_id}/latest", response_model=LatestVitalsResponse)
async def get_latest_vitals(
    patient_id: str,
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve the single most recent active measurement for each standard vital sign type.
    """
    service = ObservationService(db)
    return await service.get_latest_vitals(patient_id=patient_id, tenant_id=tenant_id)


@router.get("/encounter/{encounter_id}", response_model=List[ObservationResponse])
async def get_encounter_observations(
    encounter_id: str,
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all clinical observations recorded for an encounter.
    """
    service = ObservationService(db)
    return await service.get_encounter_observations(encounter_id=encounter_id, tenant_id=tenant_id)


@router.post("/{observation_id}/correct", response_model=ObservationResponse)
async def correct_observation(
    observation_id: str,
    req: ObservationCorrectionRequest,
    current_staff: Staff = Depends(require_roles(["DOCTOR", "CHARGE_NURSE", "ADMINISTRATOR"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Perform an append-only clinical correction of a recorded measurement.
    Preserves original record in 'CORRECTED' state while creating a new active record
    with forward/backward audit links.
    """
    service = ObservationService(db)
    return await service.correct_observation(
        observation_id=observation_id,
        tenant_id=tenant_id,
        req=req,
        actor_id=current_staff.id
    )
