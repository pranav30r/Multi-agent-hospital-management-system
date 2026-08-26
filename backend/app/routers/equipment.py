import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.equipment_service import EquipmentService

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
    reason: str = Field(default="Scheduled maintenance")


class EquipmentBookingCreate(BaseModel):
    equipment_id: str = Field(..., example="RES-CT-01")
    encounter_id: str = Field(..., example="ENC-0001")
    patient_id: str = Field(..., example="PAT-0001")
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
    service = EquipmentService(db)
    return await service.list_equipment(
        resource_type=resource_type,
        department_id=department_id,
        status=status
    )


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(equipment_id: str, db: AsyncSession = Depends(get_db)):
    """Get details of a specific equipment resource."""
    service = EquipmentService(db)
    eq = await service.get_equipment_by_id(equipment_id)
    if not eq:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")
    return eq


@router.patch("/{equipment_id}/status", response_model=EquipmentResponse)
async def update_equipment_status(
    equipment_id: str,
    req: EquipmentStatusUpdate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "TECHNICIAN"])),
    db: AsyncSession = Depends(get_db)
):
    """Update equipment operational status with pessimistic lock."""
    service = EquipmentService(db)
    return await service.update_equipment_status(
        equipment_id=equipment_id,
        status=req.status,
        reason=req.reason,
        actor_id=current_staff.id
    )


# ─── Bookings ───────────────────────────────────────────────────────────────

@router.post("/bookings", response_model=EquipmentBookingResponse, status_code=201)
async def create_equipment_booking(
    booking_in: EquipmentBookingCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "TECHNICIAN", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Book a piece of equipment for a patient encounter with row-level locking."""
    service = EquipmentService(db)
    return await service.book_equipment(
        equipment_id=booking_in.equipment_id,
        encounter_id=booking_in.encounter_id,
        patient_id=booking_in.patient_id,
        notes=booking_in.notes,
        actor_id=current_staff.id
    )


@router.get("/bookings/active", response_model=List[EquipmentBookingResponse])
async def list_active_bookings(db: AsyncSession = Depends(get_db)):
    """List all currently active equipment bookings."""
    service = EquipmentService(db)
    return await service.list_active_bookings()


@router.post("/bookings/{booking_id}/complete", response_model=EquipmentBookingResponse)
async def complete_booking(
    booking_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "TECHNICIAN", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Mark an equipment booking as completed and atomically release the equipment."""
    service = EquipmentService(db)
    return await service.complete_booking(
        booking_id=booking_id,
        actor_id=current_staff.id
    )
