import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Staff, StaffShift, StaffSkill, AuditLog

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
    changed_by: str = Field(default="ADM-001")
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
    query = select(Staff)
    if role:
        query = query.where(Staff.role == role.upper())
    if department_id:
        query = query.where(Staff.department_id == department_id)
    if status:
        query = query.where(Staff.status == status.upper())
    result = await db.execute(query.order_by(Staff.role, Staff.id))
    return result.scalars().all()


@router.get("/{staff_id}", response_model=StaffResponse)
async def get_staff_member(staff_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed information for a specific staff member."""
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    staff = result.scalars().first()
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")
    return staff


@router.patch("/{staff_id}/status", response_model=StaffResponse)
async def update_staff_status(
    staff_id: str,
    req: StaffStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a staff member's operational status (AVAILABLE, BUSY, ON_BREAK, etc.)."""
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    staff = result.scalars().first()
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

    old_status = staff.status
    staff.status = req.status.upper()

    audit = AuditLog(
        entity_type="staff",
        entity_id=staff_id,
        field_changed="status",
        old_value=old_status,
        new_value=req.status.upper(),
        changed_by=req.changed_by,
        change_reason=req.reason
    )
    db.add(audit)

    await db.commit()
    await db.refresh(staff)
    logger.info(f"Staff {staff_id} status: {old_status} → {req.status.upper()} by {req.changed_by}")
    return staff


@router.patch("/{staff_id}/workload")
async def increment_workload(
    staff_id: str,
    delta: int = Query(1, description="Increment (+1) or decrement (-1) workload"),
    db: AsyncSession = Depends(get_db)
):
    """Adjust a staff member's active patient workload count."""
    result = await db.execute(select(Staff).where(Staff.id == staff_id))
    staff = result.scalars().first()
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff member {staff_id} not found")

    old_load = staff.current_workload
    staff.current_workload = max(0, staff.current_workload + delta)

    # Auto-set BUSY if at max
    if staff.current_workload >= staff.max_workload:
        staff.status = "BUSY"
    elif staff.status == "BUSY" and staff.current_workload < staff.max_workload:
        staff.status = "AVAILABLE"

    await db.commit()
    await db.refresh(staff)
    logger.info(f"Staff {staff_id} workload: {old_load} → {staff.current_workload}")
    return {"id": staff.id, "current_workload": staff.current_workload, "status": staff.status}


@router.get("/departments/{department_id}/ratios")
async def get_department_staffing_ratios(department_id: str, db: AsyncSession = Depends(get_db)):
    """Get current nurse:patient and doctor:patient ratios for a department."""
    doctors = await db.execute(
        select(Staff).where(Staff.department_id == department_id, Staff.role == "DOCTOR", Staff.status.in_(["AVAILABLE", "BUSY"]))
    )
    nurses = await db.execute(
        select(Staff).where(Staff.department_id == department_id, Staff.role.in_(["NURSE", "CHARGE_NURSE"]), Staff.status.in_(["AVAILABLE", "BUSY"]))
    )

    doc_list = doctors.scalars().all()
    nurse_list = nurses.scalars().all()

    total_patients = sum(s.current_workload for s in nurse_list)

    return {
        "department_id": department_id,
        "active_doctors": len(doc_list),
        "active_nurses": len(nurse_list),
        "total_active_patients": total_patients,
        "nurse_patient_ratio": f"1:{round(total_patients / max(len(nurse_list), 1))}",
        "doctor_patient_ratio": f"1:{round(total_patients / max(len(doc_list), 1))}"
    }


# ─── Shifts ─────────────────────────────────────────────────────────────────

@router.get("/shifts/all", response_model=List[StaffShiftResponse])
async def list_shifts(
    staff_id: Optional[str] = None,
    shift_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List staff shift schedules."""
    query = select(StaffShift)
    if staff_id:
        query = query.where(StaffShift.staff_id == staff_id)
    if shift_type:
        query = query.where(StaffShift.shift_type == shift_type.upper())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/shifts", response_model=StaffShiftResponse, status_code=201)
async def create_shift(shift_in: StaffShiftCreate, db: AsyncSession = Depends(get_db)):
    """Schedule a new shift for a staff member."""
    # Verify staff exists
    res = await db.execute(select(Staff).where(Staff.id == shift_in.staff_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail=f"Staff {shift_in.staff_id} not found")

    shift = StaffShift(
        staff_id=shift_in.staff_id,
        department_id=shift_in.department_id,
        shift_type=shift_in.shift_type.upper(),
        start_time=shift_in.start_time,
        end_time=shift_in.end_time
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    logger.info(f"Shift created: {shift.id} for {shift_in.staff_id} ({shift_in.shift_type})")
    return shift


# ─── Skills ─────────────────────────────────────────────────────────────────

@router.get("/{staff_id}/skills", response_model=List[StaffSkillResponse])
async def list_staff_skills(staff_id: str, db: AsyncSession = Depends(get_db)):
    """List all certified skills for a staff member."""
    result = await db.execute(select(StaffSkill).where(StaffSkill.staff_id == staff_id))
    return result.scalars().all()


@router.post("/skills", response_model=StaffSkillResponse, status_code=201)
async def add_staff_skill(skill_in: StaffSkillCreate, db: AsyncSession = Depends(get_db)):
    """Register a new certification/skill for a staff member."""
    res = await db.execute(select(Staff).where(Staff.id == skill_in.staff_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail=f"Staff {skill_in.staff_id} not found")

    skill = StaffSkill(
        staff_id=skill_in.staff_id,
        skill_name=skill_in.skill_name,
        certification_date=datetime.utcnow()
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    logger.info(f"Skill added: {skill_in.skill_name} for {skill_in.staff_id}")
    return skill
