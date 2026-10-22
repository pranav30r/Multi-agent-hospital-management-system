import logging
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.bed_service import BedService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Beds & Departments"])


# ─── Request & Response Schemas ─────────────────────────────────────────────

class ManualBedBookRequest(BaseModel):
    patient_id: str = Field(..., examples=["PAT-0001"])
    encounter_id: str = Field(..., examples=["ENC-0001"])
    bed_id: str = Field(..., examples=["BED-ICU-07"])
    reason: str = Field(default="Direct clinician assignment due to urgent ICU need")


class BedResponse(BaseModel):
    id: str
    department_id: str
    bed_type: str
    status: str
    is_isolation: bool
    has_ventilator: bool
    has_telemetry: bool
    current_patient_id: Optional[str]
    current_encounter_id: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    total_beds: int
    current_occupancy: int
    min_doctors: int
    min_nurses: int
    nurse_patient_ratio: str

    model_config = ConfigDict(from_attributes=True)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List all hospital departments and current capacity metrics."""
    service = BedService(db)
    return await service.list_departments(tenant_id=current_staff.tenant_id)


@router.get("/beds", response_model=List[BedResponse])
async def list_beds(
    department_id: Optional[str] = None,
    bed_status: Optional[str] = None,
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List hospital beds with optional department and status filters."""
    service = BedService(db)
    return await service.list_beds(department_id=department_id, bed_status=bed_status, tenant_id=current_staff.tenant_id)


@router.post("/beds/book-manual", response_model=BedResponse)
async def book_bed_manually(
    req: ManualBedBookRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Directly book a bed for a patient with pessimistic row-level concurrency locking.
    State transition: AVAILABLE -> RESERVED (Atomic, prevents race-condition double booking).
    """
    service = BedService(db)
    return await service.reserve_bed(
        bed_id=req.bed_id,
        patient_id=req.patient_id,
        encounter_id=req.encounter_id,
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        reason=req.reason,
        tenant_id=current_staff.tenant_id
    )


@router.post("/beds/{bed_id}/confirm-patient-in-bed", response_model=BedResponse)
async def confirm_patient_in_bed(
    bed_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirms physical arrival of patient at the bed with pessimistic locking.
    State transition: RESERVED -> OCCUPIED.
    """
    service = BedService(db)
    return await service.confirm_patient_arrival(
        bed_id=bed_id,
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        tenant_id=current_staff.tenant_id
    )


@router.post("/beds/{bed_id}/release", response_model=BedResponse)
async def release_bed(
    bed_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Releases an occupied, reserved, or cleaning bed with pessimistic locking.
    State transition: OCCUPIED/RESERVED -> AVAILABLE.
    """
    service = BedService(db)
    return await service.release_bed(
        bed_id=bed_id,
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        tenant_id=current_staff.tenant_id,
        reason=f"Bed released by {current_staff.role} {current_staff.id}"
    )


class BedStatusUpdateRequest(BaseModel):
    status: str = Field(..., examples=["AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE", "CLEANING", "BLOCKED"])
    reason: Optional[str] = Field(default="Status manually updated by clinician")


@router.patch("/beds/{bed_id}/status", response_model=BedResponse)
@router.post("/beds/{bed_id}/status", response_model=BedResponse)
async def update_bed_status(
    bed_id: str,
    req: BedStatusUpdateRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE", "NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Directly update bed status (AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE, CLEANING, BLOCKED).
    Allows clinical staff to immediately mark beds as available, occupied/emergency, or maintenance.
    """
    service = BedService(db)
    return await service.update_bed_status(
        bed_id=bed_id,
        status=req.status.upper(),
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        tenant_id=current_staff.tenant_id,
        reason=req.reason
    )

