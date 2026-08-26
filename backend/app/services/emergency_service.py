import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency import EmergencyEvent
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class EmergencyService:
    """
    Application Service for Hospital-Wide Emergency Declarations & Operations.
    Encapsulates emergency escalation, department impact coordination, and resolution tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_active_emergencies(self) -> List[EmergencyEvent]:
        """Query all currently active hospital emergency events."""
        res = await self.db.execute(select(EmergencyEvent).where(EmergencyEvent.status == "ACTIVE"))
        return res.scalars().all()

    async def get_emergency_by_id(self, emergency_id: str) -> Optional[EmergencyEvent]:
        """Fetch an emergency event by its unique ID."""
        res = await self.db.execute(select(EmergencyEvent).where(EmergencyEvent.id == emergency_id))
        return res.scalars().first()

    async def declare_emergency(
        self,
        event_type: str,
        severity: str,
        description: str,
        affected_departments: List[str],
        expected_patient_surge: int,
        actor_id: str
    ) -> EmergencyEvent:
        """
        Declare a hospital-wide emergency event with RBAC and audit trail.
        State: -> ACTIVE
        """
        emergency = EmergencyEvent(
            event_type=event_type.upper(),
            severity=severity.upper(),
            description=description,
            affected_departments=affected_departments,
            expected_patient_surge=expected_patient_surge,
            declared_by=actor_id,
            status="ACTIVE"
        )
        self.db.add(emergency)

        audit = AuditLog(
            entity_type="emergency",
            entity_id="HOSPITAL-WIDE",
            field_changed="status",
            old_value="NORMAL",
            new_value=f"EMERGENCY_{event_type.upper()}",
            changed_by=actor_id,
            change_reason=f"Emergency Declared: {description}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(emergency)
        logger.info(f"EMERGENCY DECLARED: {emergency.id} ({event_type.upper()}) by {actor_id}")
        return emergency

    async def resolve_emergency(
        self,
        emergency_id: str,
        actor_id: str
    ) -> EmergencyEvent:
        """
        Resolve an active emergency event with pessimistic row-level lock.
        State transition: ACTIVE -> RESOLVED
        """
        res = await self.db.execute(
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
            changed_by=actor_id,
            change_reason="Emergency event resolved by authorized staff"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(emergency)
        logger.info(f"EMERGENCY RESOLVED: {emergency.id} by {actor_id}")
        return emergency
