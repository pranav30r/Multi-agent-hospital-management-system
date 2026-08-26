import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import EmergencyEvent, AuditLog, Staff
from app.auth.dependencies import require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emergencies", tags=["Emergency Operations"])

class DeclareEmergencyRequest(BaseModel):
    event_type: str = Field(..., example="MASS_CASUALTY")  # MASS_CASUALTY, PANDEMIC_SURGE, INFRASTRUCTURE_FAILURE, STAFF_CRISIS
    severity: str = Field(default="HIGH", example="CRITICAL")
    description: str = Field(..., example="Major highway multivehicle collision; expecting 8 critical trauma arrivals")
    affected_departments: List[str] = Field(default_factory=lambda: ["DEP-ER", "DEP-ICU"])
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

    class Config:
        from_attributes = True

@router.post("/declare", response_model=EmergencyResponse, status_code=status.HTTP_201_CREATED)
async def declare_emergency(
    req: DeclareEmergencyRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Declare a hospital-wide emergency event with RBAC enforcement.
    Triggers all emergency agents and escalates risk levels.
    """
    emergency = EmergencyEvent(
        event_type=req.event_type,
        severity=req.severity,
        description=req.description,
        affected_departments=req.affected_departments,
        expected_patient_surge=req.expected_patient_surge,
        declared_by=current_staff.id,
        status="ACTIVE"
    )
    db.add(emergency)

    audit = AuditLog(
        entity_type="emergency",
        entity_id="HOSPITAL-WIDE",
        field_changed="status",
        old_value="NORMAL",
        new_value=f"EMERGENCY_{req.event_type}",
        changed_by=current_staff.id,
        change_reason=f"Emergency Declared: {req.description}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(emergency)
    logger.info(f"EMERGENCY DECLARED: {emergency.id} ({req.event_type}) by {current_staff.id}")
    return emergency

@router.get("/active", response_model=List[EmergencyResponse])
async def list_active_emergencies(db: AsyncSession = Depends(get_db)):
    """Get active emergency events."""
    res = await db.execute(select(EmergencyEvent).where(EmergencyEvent.status == "ACTIVE"))
    return res.scalars().all()

@router.post("/{emergency_id}/resolve", response_model=EmergencyResponse)
async def resolve_emergency(
    emergency_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Resolve an emergency event with row-level lock and RBAC."""
    res = await db.execute(
        select(EmergencyEvent).where(EmergencyEvent.id == emergency_id).with_for_update()
    )
    emergency = res.scalars().first()
    if not emergency:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    if emergency.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Emergency event is already resolved")

    emergency.status = "RESOLVED"
    emergency.resolved_at = datetime.utcnow()

    audit = AuditLog(
        entity_type="emergency",
        entity_id=emergency_id,
        field_changed="status",
        old_value="ACTIVE",
        new_value="RESOLVED",
        changed_by=current_staff.id,
        change_reason="Emergency event resolved by authorized staff"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(emergency)
    logger.info(f"EMERGENCY RESOLVED: {emergency.id} by {current_staff.id}")
    return emergency
