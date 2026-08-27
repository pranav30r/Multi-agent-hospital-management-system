import logging
from typing import List, Optional, Set
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency import EmergencyEvent
from app.models.department import Department
from app.models.agent import AuditLog
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = {
    "MASS_CASUALTY",
    "PANDEMIC_SURGE",
    "INFRASTRUCTURE_FAILURE",
    "STAFF_CRISIS",
    "CYBER_ATTACK",
    "FIRE_HAZARD"
}

VALID_SEVERITIES = {"HIGH", "CRITICAL"}

class EmergencyService:
    """
    Application Service for Hospital-Wide Emergency Declarations, Surge Operations, and Escalation.
    Encapsulates emergency lifecycle (ACTIVE -> ESCALATED -> RESOLVED), department validation, and audit tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_active_emergencies(self) -> List[EmergencyEvent]:
        """Query all currently active or escalated hospital emergency events."""
        res = await self.db.execute(
            select(EmergencyEvent).where(EmergencyEvent.status.in_(["ACTIVE", "ESCALATED"]))
        )
        return res.scalars().all()

    async def get_emergency_by_id(self, emergency_id: str) -> Optional[EmergencyEvent]:
        """Fetch an emergency event by its unique ID."""
        res = await self.db.execute(select(EmergencyEvent).where(EmergencyEvent.id == emergency_id))
        return res.scalars().first()

    async def get_affected_departments(self) -> List[str]:
        """Get unique list of department IDs affected across all active emergencies."""
        active_events = await self.list_active_emergencies()
        affected: Set[str] = set()
        for ev in active_events:
            if isinstance(ev.affected_departments, list):
                affected.update(ev.affected_departments)
        return sorted(list(affected))

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
        Declare a hospital-wide emergency event with department validation and audit trail.
        State: -> ACTIVE
        """
        event_type_clean = event_type.upper()
        severity_clean = severity.upper()

        if event_type_clean not in VALID_EVENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid emergency event type '{event_type}'. Valid types: {sorted(list(VALID_EVENT_TYPES))}"
            )

        if severity_clean not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid emergency severity '{severity}'. Valid severities: {sorted(list(VALID_SEVERITIES))}"
            )

        # Validate that referenced affected departments exist in PostgreSQL database
        if affected_departments:
            dept_res = await self.db.execute(
                select(Department.id).where(Department.id.in_(affected_departments))
            )
            existing_depts = set(dept_res.scalars().all())
            invalid_depts = set(affected_departments) - existing_depts
            if invalid_depts:
                raise HTTPException(
                    status_code=400,
                    detail=f"Referenced departments do not exist: {sorted(list(invalid_depts))}"
                )

        emergency = EmergencyEvent(
            event_type=event_type_clean,
            severity=severity_clean,
            description=description,
            affected_departments=affected_departments,
            expected_patient_surge=expected_patient_surge,
            declared_by=actor_id,
            status="ACTIVE",
            declared_at=utc_now()
        )
        self.db.add(emergency)

        audit = AuditLog(
            entity_type="emergency",
            entity_id="HOSPITAL-WIDE",
            field_changed="status",
            old_value="NORMAL",
            new_value=f"EMERGENCY_{event_type_clean}",
            changed_by=actor_id,
            change_reason=f"Emergency Declared ({severity_clean}): {description}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(emergency)
        logger.info(f"EMERGENCY DECLARED: {emergency.id} ({event_type_clean}) by {actor_id}")
        return emergency

    async def escalate_emergency(
        self,
        emergency_id: str,
        additional_surge: int,
        additional_departments: Optional[List[str]],
        reason: str,
        actor_id: str
    ) -> EmergencyEvent:
        """
        Escalate an active emergency event with pessimistic row-level lock.
        State transition: ACTIVE -> ESCALATED
        """
        res = await self.db.execute(
            select(EmergencyEvent).where(EmergencyEvent.id == emergency_id).with_for_update()
        )
        emergency = res.scalars().first()
        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency event not found")
        if emergency.status == "RESOLVED":
            raise HTTPException(status_code=400, detail="Cannot escalate an already resolved emergency")

        # Validate additional departments if provided
        if additional_departments:
            dept_res = await self.db.execute(
                select(Department.id).where(Department.id.in_(additional_departments))
            )
            existing_depts = set(dept_res.scalars().all())
            invalid_depts = set(additional_departments) - existing_depts
            if invalid_depts:
                raise HTTPException(
                    status_code=400,
                    detail=f"Referenced departments do not exist: {sorted(list(invalid_depts))}"
                )
            merged_depts = list(set((emergency.affected_departments or []) + additional_departments))
            emergency.affected_departments = merged_depts

        old_status = emergency.status
        emergency.status = "ESCALATED"
        emergency.severity = "CRITICAL"
        emergency.expected_patient_surge += max(0, additional_surge)

        audit = AuditLog(
            entity_type="emergency",
            entity_id=emergency_id,
            field_changed="status",
            old_value=old_status,
            new_value="ESCALATED",
            changed_by=actor_id,
            change_reason=f"Emergency Escalated: {reason}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(emergency)
        logger.info(f"EMERGENCY ESCALATED: {emergency.id} by {actor_id}")
        return emergency

    async def resolve_emergency(
        self,
        emergency_id: str,
        actor_id: str
    ) -> EmergencyEvent:
        """
        Resolve an active or escalated emergency event with pessimistic row-level lock.
        State transition: ACTIVE / ESCALATED -> RESOLVED
        """
        res = await self.db.execute(
            select(EmergencyEvent).where(EmergencyEvent.id == emergency_id).with_for_update()
        )
        emergency = res.scalars().first()
        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency event not found")
        if emergency.status == "RESOLVED":
            raise HTTPException(status_code=400, detail="Emergency event is already resolved")

        old_status = emergency.status
        emergency.status = "RESOLVED"
        emergency.resolved_at = utc_now()

        audit = AuditLog(
            entity_type="emergency",
            entity_id=emergency_id,
            field_changed="status",
            old_value=old_status,
            new_value="RESOLVED",
            changed_by=actor_id,
            change_reason="Emergency event resolved by authorized staff"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(emergency)
        logger.info(f"EMERGENCY RESOLVED: {emergency.id} by {actor_id}")
        return emergency
