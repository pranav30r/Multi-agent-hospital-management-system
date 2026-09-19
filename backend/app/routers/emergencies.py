import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.emergency_service import EmergencyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emergencies", tags=["Emergency Operations"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class DeclareEmergencyRequest(BaseModel):
    event_type: str = Field(..., examples=["MASS_CASUALTY"])  # MASS_CASUALTY, PANDEMIC_SURGE, INFRASTRUCTURE_FAILURE, STAFF_CRISIS
    severity: str = Field(default="HIGH", examples=["CRITICAL"])
    description: str = Field(..., examples=["Major highway multivehicle collision; expecting 8 critical trauma arrivals"])
    affected_departments: List[str] = Field(default_factory=list, description="List of affected department IDs")
    expected_patient_surge: int = Field(default=8, ge=1, le=50)


class EmergencyResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    description: str
    affected_departments: List[str]
    expected_patient_surge: int
    declared_by: str
    status: str
    declared_at: datetime
    resolved_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CrewRunResponse(BaseModel):
    id: str
    tenant_id: str
    crew_name: str
    trigger_event: str
    agents_count: int
    tasks_count: int
    output_summary: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/declare", response_model=EmergencyResponse, status_code=status.HTTP_201_CREATED)
async def declare_emergency(
    req: DeclareEmergencyRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Declare a hospital-wide emergency event with RBAC & tenant enforcement.
    Triggers all emergency agents and escalates risk levels.
    """
    service = EmergencyService(db)
    return await service.declare_emergency(
        event_type=req.event_type,
        severity=req.severity,
        description=req.description,
        affected_departments=req.affected_departments,
        expected_patient_surge=req.expected_patient_surge,
        actor_id=current_staff.id,
        tenant_id=current_staff.tenant_id
    )


@router.get("/active", response_model=List[EmergencyResponse])
async def list_active_emergencies(
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get active emergency events for the authenticated tenant."""
    service = EmergencyService(db)
    return await service.list_active_emergencies(tenant_id=current_staff.tenant_id)


@router.post("/{emergency_id}/resolve", response_model=EmergencyResponse)
async def resolve_emergency(
    emergency_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Resolve an emergency event with row-level lock and RBAC."""
    service = EmergencyService(db)
    return await service.resolve_emergency(
        emergency_id=emergency_id,
        actor_id=current_staff.id,
        tenant_id=current_staff.tenant_id
    )


@router.get("/crew-runs", response_model=List[CrewRunResponse])
async def list_emergency_crew_runs(
    skip: int = 0,
    limit: int = 20,
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List historical collaborative emergency surge crew executions."""
    service = EmergencyService(db)
    return await service.list_crew_runs(tenant_id=current_staff.tenant_id, skip=skip, limit=limit)


@router.post("/{emergency_id}/run-crew", response_model=CrewRunResponse)
async def dispatch_emergency_crew(
    emergency_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Dispatch the Multi-Agent Emergency Surge Crew for an active emergency event.
    Coordinates Triage Lead, Bed Marshall, Workforce Marshall, and Logistics Officer to synthesize surge action plan.
    """
    service = EmergencyService(db)
    return await service.run_emergency_crew(
        emergency_id=emergency_id,
        actor_id=current_staff.id,
        tenant_id=current_staff.tenant_id
    )
