import logging
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.bed_service import BedService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Beds & Departments"])


# ─── Request & Response Schemas ─────────────────────────────────────────────

class ManualBedBookRequest(BaseModel):
    patient_id: str = Field(..., example="PAT-0001")
    encounter_id: str = Field(..., example="ENC-0001")
    bed_id: str = Field(..., example="BED-ICU-07")
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

    class Config:
        from_attributes = True


class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    total_beds: int
    current_occupancy: int
    min_doctors: int
    min_nurses: int
    nurse_patient_ratio: str

    class Config:
        from_attributes = True


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(db: AsyncSession = Depends(get_db)):
    """List all hospital departments and current capacity metrics."""
    service = BedService(db)
    return await service.list_departments()


@router.get("/beds", response_model=List[BedResponse])
async def list_beds(
    department_id: Optional[str] = None,
    bed_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List hospital beds with optional department and status filters."""
    service = BedService(db)
    return await service.list_beds(department_id=department_id, bed_status=bed_status)


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
        reason=req.reason
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
        actor_role=current_staff.role
    )
