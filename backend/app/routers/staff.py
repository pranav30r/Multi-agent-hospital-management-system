import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.staff_service import StaffService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/staff", tags=["Staff & Workforce"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class StaffResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str]
    status: str
    current_workload: int
    max_workload: int
    skills: Optional[list]
    created_at: datetime

    class Config:
        from_attributes = True


class StaffStatusUpdate(BaseModel):
    status: str = Field(..., example="BUSY")
    reason: str = Field(default="Manual status update")


class StaffShiftResponse(BaseModel):
    id: str
    staff_id: str
    department_id: str
    shift_type: str
    start_time: str
    end_time: str
    status: str

    class Config:
        from_attributes = True


class StaffShiftCreate(BaseModel):
    staff_id: str
    department_id: str
    shift_type: str = Field(..., example="MORNING")
    start_time: str = Field(default="06:00")
    end_time: str = Field(default="14:00")


class StaffSkillResponse(BaseModel):
    id: str
    staff_id: str
    skill_name: str
    certification_date: Optional[datetime]

    class Config:
        from_attributes = True


class StaffSkillCreate(BaseModel):
    staff_id: str
    skill_name: str = Field(..., example="ICU_CERTIFIED")


# ─── Staff CRUD ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[StaffResponse])
async def list_staff(
    role: Optional[str] = Query(None, description="Filter by role: DOCTOR, NURSE, CHARGE_NURSE, TECHNICIAN, RECEPTIONIST, ADMINISTRATOR"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    status: Optional[str] = Query(None, description="Filter by status: AVAILABLE, BUSY, ON_BREAK, OFF_SHIFT"),
    db: AsyncSession = Depends(get_db)
):
    """List all hospital staff with optional filters."""
    service = StaffService(db)
    return await service.list_staff(role=role, department_id=department_id, status=status)


@router.get("/{staff_id}", response_model=StaffResponse)
async def get_staff_member(staff_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed information for a specific staff member."""
    service = StaffService(db)
    staff = await service.get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")
    return staff


@router.patch("/{staff_id}/status", response_model=StaffResponse)
async def update_staff_status(
    staff_id: str,
    req: StaffStatusUpdate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Update a staff member's operational status with row lock and RBAC."""
    service = StaffService(db)
    return await service.update_staff_status(
        staff_id=staff_id,
        new_status=req.status,
        actor_id=current_staff.id,
        reason=req.reason
    )


@router.patch("/{staff_id}/workload")
async def increment_workload(
    staff_id: str,
    delta: int = Query(1, description="Increment (+1) or decrement (-1) workload"),
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Adjust a staff member's active patient workload count with row lock."""
    service = StaffService(db)
    return await service.adjust_workload(
        staff_id=staff_id,
        delta=delta,
        actor_id=current_staff.id
    )


@router.get("/departments/{department_id}/ratios")
async def get_department_staffing_ratios(department_id: str, db: AsyncSession = Depends(get_db)):
    """Get current nurse:patient and doctor:patient ratios for a department."""
    service = StaffService(db)
    return await service.get_department_staffing_ratios(department_id=department_id)


# ─── Shifts ─────────────────────────────────────────────────────────────────

@router.get("/shifts/all", response_model=List[StaffShiftResponse])
async def list_shifts(
    staff_id: Optional[str] = None,
    shift_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List staff shift schedules."""
    service = StaffService(db)
    return await service.list_shifts(staff_id=staff_id, shift_type=shift_type)


@router.post("/shifts", response_model=StaffShiftResponse, status_code=201)
async def create_shift(
    shift_in: StaffShiftCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Schedule a new shift for a staff member."""
    service = StaffService(db)
    return await service.create_shift(
        staff_id=shift_in.staff_id,
        department_id=shift_in.department_id,
        shift_type=shift_in.shift_type,
        start_time=shift_in.start_time,
        end_time=shift_in.end_time,
        actor_id=current_staff.id
    )


# ─── Skills ─────────────────────────────────────────────────────────────────

@router.get("/{staff_id}/skills", response_model=List[StaffSkillResponse])
async def list_staff_skills(staff_id: str, db: AsyncSession = Depends(get_db)):
    """List all certified skills for a staff member."""
    service = StaffService(db)
    return await service.list_staff_skills(staff_id=staff_id)


@router.post("/skills", response_model=StaffSkillResponse, status_code=201)
async def add_staff_skill(
    skill_in: StaffSkillCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR"])),
    db: AsyncSession = Depends(get_db)
):
    """Register a new certification/skill for a staff member."""
    service = StaffService(db)
    return await service.add_staff_skill(
        staff_id=skill_in.staff_id,
        skill_name=skill_in.skill_name,
        actor_id=current_staff.id
    )
