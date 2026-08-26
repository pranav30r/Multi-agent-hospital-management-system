import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment import Equipment, EquipmentBooking
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class EquipmentService:
    """
    Application Service for Medical Equipment & Resource Management.
    Encapsulates slot booking, lifecycle status transitions, pessimistic row locking, and audit coordination.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_equipment(
        self,
        resource_type: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Equipment]:
        """Query equipment with optional resource type, department, and status filters."""
        query = select(Equipment)
        if resource_type:
            query = query.where(Equipment.resource_type == resource_type.upper())
        if department_id:
            query = query.where(Equipment.department_id == department_id)
        if status:
            query = query.where(Equipment.status == status.upper())
        result = await self.db.execute(query.order_by(Equipment.resource_type, Equipment.id))
        return result.scalars().all()

    async def get_equipment_by_id(self, equipment_id: str) -> Optional[Equipment]:
        """Fetch equipment details by ID."""
        result = await self.db.execute(select(Equipment).where(Equipment.id == equipment_id))
        return result.scalars().first()

    async def update_equipment_status(
        self,
        equipment_id: str,
        status: str,
        reason: str,
        actor_id: str
    ) -> Equipment:
        """
        Update equipment operational status with pessimistic row-level lock.
        State transition: e.g. AVAILABLE -> MAINTENANCE, MAINTENANCE -> AVAILABLE
        """
        result = await self.db.execute(
            select(Equipment).where(Equipment.id == equipment_id).with_for_update()
        )
        eq = result.scalars().first()
        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        old_status = eq.status
        eq.status = status.upper()

        if status.upper() == "AVAILABLE":
            eq.current_patient_id = None
            eq.current_encounter_id = None

        audit = AuditLog(
            entity_type="equipment",
            entity_id=equipment_id,
            field_changed="status",
            old_value=old_status,
            new_value=status.upper(),
            changed_by=actor_id,
            change_reason=reason
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(eq)
        logger.info(f"Equipment {equipment_id} status: {old_status} → {status.upper()} by {actor_id}")
        return eq

    async def book_equipment(
        self,
        equipment_id: str,
        encounter_id: str,
        patient_id: str,
        notes: Optional[str],
        actor_id: str
    ) -> EquipmentBooking:
        """
        Atomically book a medical equipment resource for an encounter with pessimistic row lock.
        State transition: AVAILABLE -> IN_USE
        """
        result = await self.db.execute(
            select(Equipment).where(Equipment.id == equipment_id).with_for_update()
        )
        eq = result.scalars().first()
        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")
        if eq.status != "AVAILABLE":
            raise HTTPException(
                status_code=400,
                detail=f"Equipment {equipment_id} is in '{eq.status}' state and cannot be booked"
            )

        eq.status = "IN_USE"
        eq.current_patient_id = patient_id
        eq.current_encounter_id = encounter_id

        booking = EquipmentBooking(
            equipment_id=equipment_id,
            encounter_id=encounter_id,
            patient_id=patient_id,
            requested_by=actor_id,
            notes=notes,
            status="IN_PROGRESS"
        )
        self.db.add(booking)

        audit = AuditLog(
            entity_type="equipment",
            entity_id=equipment_id,
            field_changed="status",
            old_value="AVAILABLE",
            new_value="IN_USE",
            changed_by=actor_id,
            change_reason=f"Equipment booked for encounter {encounter_id}: {notes or 'No notes'}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(booking)
        logger.info(f"Equipment booking created: {booking.id} for {equipment_id} by {actor_id}")
        return booking

    async def list_active_bookings(self) -> List[EquipmentBooking]:
        """List all currently active equipment bookings."""
        result = await self.db.execute(
            select(EquipmentBooking).where(EquipmentBooking.status.in_(["SCHEDULED", "IN_PROGRESS"]))
        )
        return result.scalars().all()

    async def complete_booking(
        self,
        booking_id: str,
        actor_id: str
    ) -> EquipmentBooking:
        """
        Atomically mark a booking as completed and release the associated equipment to AVAILABLE.
        State transition: Booking IN_PROGRESS -> COMPLETED, Equipment IN_USE -> AVAILABLE
        """
        result = await self.db.execute(
            select(EquipmentBooking).where(EquipmentBooking.id == booking_id).with_for_update()
        )
        booking = result.scalars().first()
        if not booking:
            raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")
        if booking.status == "COMPLETED":
            raise HTTPException(status_code=400, detail=f"Booking {booking_id} is already completed")

        booking.status = "COMPLETED"
        booking.end_time = datetime.utcnow()

        # Atomically lock and release associated equipment
        eq_result = await self.db.execute(
            select(Equipment).where(Equipment.id == booking.equipment_id).with_for_update()
        )
        eq = eq_result.scalars().first()
        if eq:
            eq.status = "AVAILABLE"
            eq.current_patient_id = None
            eq.current_encounter_id = None

        audit = AuditLog(
            entity_type="equipment",
            entity_id=booking.equipment_id,
            field_changed="status",
            old_value="IN_USE",
            new_value="AVAILABLE",
            changed_by=actor_id,
            change_reason=f"Booking {booking_id} completed and equipment released"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(booking)
        logger.info(f"Equipment booking completed: {booking_id}, equipment {booking.equipment_id} released by {actor_id}")
        return booking
