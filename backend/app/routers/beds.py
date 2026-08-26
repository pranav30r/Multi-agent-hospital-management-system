import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bed, BedAssignment, Department, Encounter, AuditLog, Staff
from app.auth.dependencies import require_roles

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Beds & Departments"])

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

@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(db: AsyncSession = Depends(get_db)):
    """List all hospital departments and current capacity metrics."""
    res = await db.execute(select(Department))
    return res.scalars().all()

@router.get("/beds", response_model=List[BedResponse])
async def list_beds(
    department_id: Optional[str] = None,
    bed_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List hospital beds with optional filters."""
    query = select(Bed)
    if department_id:
        query = query.where(Bed.department_id == department_id)
    if bed_status:
        query = query.where(Bed.status == bed_status)
    res = await db.execute(query)
    return res.scalars().all()

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
    # 1. Pessimistic Row Lock on target Bed
    res_bed = await db.execute(
        select(Bed).where(Bed.id == req.bed_id).with_for_update()
    )
    bed = res_bed.scalars().first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    if bed.status != "AVAILABLE":
        raise HTTPException(
            status_code=400,
            detail=f"Bed {req.bed_id} is in '{bed.status}' state and cannot be booked"
        )

    res_enc = await db.execute(select(Encounter).where(Encounter.id == req.encounter_id))
    encounter = res_enc.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    # 2. Update bed state to RESERVED
    old_status = bed.status
    bed.status = "RESERVED"
    bed.current_patient_id = req.patient_id
    bed.current_encounter_id = req.encounter_id

    # 3. Update encounter
    encounter.current_bed_id = req.bed_id
    encounter.bed_reserved_time = datetime.utcnow()
    encounter.patient_status = "BED_RESERVED"

    # 4. Create BedAssignment record using authenticated staff identity
    assignment = BedAssignment(
        bed_id=req.bed_id,
        encounter_id=req.encounter_id,
        patient_id=req.patient_id,
        assigned_by=current_staff.id,
        is_manual_override=True,
        status="RESERVED"
    )
    db.add(assignment)

    # 5. Log in Audit Trail using authenticated staff identity
    audit = AuditLog(
        entity_type="bed",
        entity_id=req.bed_id,
        field_changed="status",
        old_value=old_status,
        new_value="RESERVED",
        changed_by=current_staff.id,
        change_reason=f"Manual Bed Booking by {current_staff.role}: {req.reason}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(bed)
    logger.info(f"Manual Bed Booking: Bed {req.bed_id} RESERVED for patient {req.patient_id} by authenticated staff {current_staff.id}")
    return bed

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
    res_bed = await db.execute(
        select(Bed).where(Bed.id == bed_id).with_for_update()
    )
    bed = res_bed.scalars().first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    if bed.status != "RESERVED":
        raise HTTPException(status_code=400, detail=f"Bed {bed_id} status is '{bed.status}', expected 'RESERVED'")

    old_status = bed.status
    bed.status = "OCCUPIED"

    if bed.current_encounter_id:
        res_enc = await db.execute(select(Encounter).where(Encounter.id == bed.current_encounter_id))
        encounter = res_enc.scalars().first()
        if encounter:
            encounter.bed_occupied_time = datetime.utcnow()
            encounter.patient_status = "ADMITTED"

    audit = AuditLog(
        entity_type="bed",
        entity_id=bed_id,
        field_changed="status",
        old_value=old_status,
        new_value="OCCUPIED",
        changed_by=current_staff.id,
        change_reason="Confirmed physical arrival of patient at bed"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(bed)
    logger.info(f"Physical arrival confirmed: Bed {bed_id} is now OCCUPIED by {current_staff.id}")
    return bed
