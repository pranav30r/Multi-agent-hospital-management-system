import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Equipment, EquipmentBooking, AuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/equipment", tags=["Equipment & Resources"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class EquipmentResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    department_id: str
    status: str
    slot_duration_mins: int
    current_patient_id: Optional[str]
    current_encounter_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class EquipmentStatusUpdate(BaseModel):
    status: str = Field(..., example="MAINTENANCE")
    changed_by: str = Field(default="TECH-001")
    reason: str = Field(default="Scheduled maintenance")


class EquipmentBookingCreate(BaseModel):
    equipment_id: str = Field(..., example="RES-CT-01")
    encounter_id: str = Field(..., example="ENC-0001")
    patient_id: str = Field(..., example="PAT-0001")
    requested_by: str = Field(default="DOC-001")
    notes: Optional[str] = Field(None, example="CT Chest with contrast for suspected PE")


class EquipmentBookingResponse(BaseModel):
    id: str
    equipment_id: str
    encounter_id: str
    patient_id: str
    requested_by: str
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    notes: Optional[str]

    class Config:
        from_attributes = True


# ─── Equipment CRUD ─────────────────────────────────────────────────────────

@router.get("", response_model=List[EquipmentResponse])
async def list_equipment(
    resource_type: Optional[str] = Query(None, description="Filter: CT_SCANNER, MRI, XRAY, VENTILATOR, ECG_MACHINE, etc."),
    department_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter: AVAILABLE, IN_USE, RESERVED, MAINTENANCE"),
    db: AsyncSession = Depends(get_db)
):
    """List all hospital equipment and resources with optional filters."""
    query = select(Equipment)
    if resource_type:
        query = query.where(Equipment.resource_type == resource_type.upper())
    if department_id:
        query = query.where(Equipment.department_id == department_id)
    if status:
        query = query.where(Equipment.status == status.upper())
    result = await db.execute(query.order_by(Equipment.resource_type, Equipment.id))
    return result.scalars().all()


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(equipment_id: str, db: AsyncSession = Depends(get_db)):
    """Get details of a specific equipment resource."""
    result = await db.execute(select(Equipment).where(Equipment.id == equipment_id))
    eq = result.scalars().first()
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")
    return eq


@router.patch("/{equipment_id}/status", response_model=EquipmentResponse)
async def update_equipment_status(
    equipment_id: str,
    req: EquipmentStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update equipment operational status (AVAILABLE, MAINTENANCE, OUT_OF_SERVICE)."""
    result = await db.execute(select(Equipment).where(Equipment.id == equipment_id))
    eq = result.scalars().first()
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    old_status = eq.status
    eq.status = req.status.upper()

    if req.status.upper() == "AVAILABLE":
        eq.current_patient_id = None
        eq.current_encounter_id = None

    audit = AuditLog(
        entity_type="equipment",
        entity_id=equipment_id,
        field_changed="status",
        old_value=old_status,
        new_value=req.status.upper(),
        changed_by=req.changed_by,
        change_reason=req.reason
    )
    db.add(audit)

    await db.commit()
    await db.refresh(eq)
    logger.info(f"Equipment {equipment_id} status: {old_status} → {req.status.upper()}")
    return eq


# ─── Bookings ───────────────────────────────────────────────────────────────

@router.post("/bookings", response_model=EquipmentBookingResponse, status_code=201)
async def create_equipment_booking(
    booking_in: EquipmentBookingCreate,
    db: AsyncSession = Depends(get_db)
):
    """Book a piece of equipment for a patient encounter (e.g., CT scan slot)."""
    result = await db.execute(select(Equipment).where(Equipment.id == booking_in.equipment_id))
    eq = result.scalars().first()
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {booking_in.equipment_id} not found")
    if eq.status not in ("AVAILABLE", "RESERVED"):
        raise HTTPException(status_code=400, detail=f"Equipment {booking_in.equipment_id} is {eq.status}, cannot book")

    eq.status = "IN_USE"
    eq.current_patient_id = booking_in.patient_id
    eq.current_encounter_id = booking_in.encounter_id

    booking = EquipmentBooking(
        equipment_id=booking_in.equipment_id,
        encounter_id=booking_in.encounter_id,
        patient_id=booking_in.patient_id,
        requested_by=booking_in.requested_by,
        notes=booking_in.notes,
        status="IN_PROGRESS"
    )
    db.add(booking)

    audit = AuditLog(
        entity_type="equipment",
        entity_id=booking_in.equipment_id,
        field_changed="status",
        old_value="AVAILABLE",
        new_value="IN_USE",
        changed_by=booking_in.requested_by,
        change_reason=f"Equipment booked for encounter {booking_in.encounter_id}: {booking_in.notes or 'No notes'}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(booking)
    logger.info(f"Equipment booking created: {booking.id} for {booking_in.equipment_id}")
    return booking


@router.get("/bookings/active", response_model=List[EquipmentBookingResponse])
async def list_active_bookings(db: AsyncSession = Depends(get_db)):
    """List all currently active equipment bookings."""
    result = await db.execute(
        select(EquipmentBooking).where(EquipmentBooking.status.in_(["SCHEDULED", "IN_PROGRESS"]))
    )
    return result.scalars().all()


@router.post("/bookings/{booking_id}/complete", response_model=EquipmentBookingResponse)
async def complete_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Mark an equipment booking as completed and release the equipment."""
    result = await db.execute(select(EquipmentBooking).where(EquipmentBooking.id == booking_id))
    booking = result.scalars().first()
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")

    booking.status = "COMPLETED"
    booking.end_time = datetime.utcnow()

    # Release equipment
    eq_result = await db.execute(select(Equipment).where(Equipment.id == booking.equipment_id))
    eq = eq_result.scalars().first()
    if eq:
        eq.status = "AVAILABLE"
        eq.current_patient_id = None
        eq.current_encounter_id = None

    await db.commit()
    await db.refresh(booking)
    logger.info(f"Equipment booking completed: {booking_id}, equipment {booking.equipment_id} released")
    return booking
