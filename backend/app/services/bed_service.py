import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bed import Bed, BedAssignment
from app.models.department import Department
from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class BedService:
    """
    Application Service for Hospital Bed & Department Allocation.
    Encapsulates state transitions, pessimistic concurrency locking, and audit trail orchestration.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_departments(self, tenant_id: Optional[str] = None) -> List[Department]:
        """Query all hospital departments and current capacity metrics."""
        query = select(Department)
        if tenant_id:
            query = query.where(Department.tenant_id == tenant_id)
        res = await self.db.execute(query)
        return res.scalars().all()

    async def list_beds(
        self,
        department_id: Optional[str] = None,
        bed_status: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> List[Bed]:
        """Query hospital beds with optional department, status, and tenant filters."""
        query = select(Bed)
        if tenant_id:
            query = query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        if department_id:
            query = query.where(Bed.department_id == department_id)
        if bed_status:
            query = query.where(Bed.status == bed_status)
        res = await self.db.execute(query)
        return res.scalars().all()

    async def get_bed_by_id(self, bed_id: str, tenant_id: Optional[str] = None) -> Optional[Bed]:
        """Fetch a bed by its unique identifier."""
        query = select(Bed).where(Bed.id == bed_id)
        if tenant_id:
            query = query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        res = await self.db.execute(query)
        return res.scalars().first()

    async def reserve_bed(
        self,
        bed_id: str,
        patient_id: str,
        encounter_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "Direct clinician assignment",
        tenant_id: Optional[str] = None
    ) -> Bed:
        """
        Atomically reserve an AVAILABLE bed for a patient encounter.
        Enforces SELECT ... FOR UPDATE pessimistic row-level concurrency lock.
        State transition: AVAILABLE -> RESERVED
        """
        # 1. Pessimistic Row Lock on target Bed
        bed_query = select(Bed).where(Bed.id == bed_id)
        if tenant_id:
            bed_query = bed_query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        res_bed = await self.db.execute(bed_query.with_for_update())
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        if bed.status != "AVAILABLE":
            raise HTTPException(
                status_code=400,
                detail=f"Bed {bed_id} is in '{bed.status}' state and cannot be booked"
            )

        # 2. Verify Encounter existence
        enc_query = select(Encounter).where(Encounter.id == encounter_id)
        if tenant_id:
            enc_query = enc_query.join(Patient, Encounter.patient_id == Patient.id).where(Patient.tenant_id == tenant_id)
        res_enc = await self.db.execute(enc_query)
        encounter = res_enc.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")

        try:
            # 3. Apply atomic state mutation on Bed (guarantees single-winner concurrency across PostgreSQL and SQLite)
            old_status = bed.status
            upd_stmt = (
                update(Bed)
                .where(Bed.id == bed_id, Bed.status == "AVAILABLE")
                .values(
                    status="RESERVED",
                    current_patient_id=patient_id,
                    current_encounter_id=encounter_id
                )
            )
            upd_res = await self.db.execute(upd_stmt)
            if upd_res.rowcount == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Bed {bed_id} is in '{bed.status}' state and cannot be booked"
                )
            bed.status = "RESERVED"
            bed.current_patient_id = patient_id
            bed.current_encounter_id = encounter_id

            # 4. Synchronize Encounter status
            encounter.current_bed_id = bed_id
            encounter.bed_reserved_time = utc_now()
            encounter.patient_status = "BED_RESERVED"

            # 5. Insert BedAssignment record using trusted authenticated staff identity
            assignment = BedAssignment(
                bed_id=bed_id,
                encounter_id=encounter_id,
                patient_id=patient_id,
                assigned_by=actor_id,
                is_manual_override=True,
                status="RESERVED"
            )
            self.db.add(assignment)

            # 6. Record immutable AuditLog entry within the same transaction
            audit = AuditLog(
                tenant_id=tenant_id or "HOSP-DEFAULT",
                entity_type="bed",
                entity_id=bed_id,
                field_changed="status",
                old_value=old_status,
                new_value="RESERVED",
                changed_by=actor_id,
                change_reason=f"Manual Bed Booking by {actor_role}: {reason}"
            )
            self.db.add(audit)

            # 7. Commit atomic transaction
            await self.db.commit()
            await self.db.refresh(bed)
        except Exception:
            await self.db.rollback()
            raise
        logger.info(f"Manual Bed Booking: Bed {bed_id} RESERVED for patient {patient_id} by authenticated staff {actor_id}")

        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "BED_RESERVED",
            "tenant_id": tenant_id or "HOSP-DEFAULT",
            "source": "bed_service",
            "payload": {
                "bed_id": bed.id,
                "bed_type": bed.bed_type,
                "department_id": bed.department_id,
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "status": "RESERVED"
            }
        }, tenant_id=tenant_id or "HOSP-DEFAULT")

        return bed

    async def confirm_patient_arrival(
        self,
        bed_id: str,
        actor_id: str,
        actor_role: str,
        tenant_id: Optional[str] = None
    ) -> Bed:
        """
        Confirms physical arrival of patient at the reserved bed with row-level lock.
        State transition: RESERVED -> OCCUPIED
        """
        # 1. Pessimistic Row Lock on target Bed
        bed_query = select(Bed).where(Bed.id == bed_id)
        if tenant_id:
            bed_query = bed_query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        res_bed = await self.db.execute(bed_query.with_for_update())
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        if bed.status != "RESERVED":
            raise HTTPException(status_code=400, detail=f"Bed {bed_id} status is '{bed.status}', expected 'RESERVED'")

        try:
            # 2. Mutate Bed state
            old_status = bed.status
            bed.status = "OCCUPIED"

            # 3. Update Encounter admission timestamp
            if bed.current_encounter_id:
                res_enc = await self.db.execute(select(Encounter).where(Encounter.id == bed.current_encounter_id))
                encounter = res_enc.scalars().first()
                if encounter:
                    encounter.bed_occupied_time = utc_now()
                    encounter.patient_status = "ADMITTED"

            # 4. Record AuditLog entry
            audit = AuditLog(
                tenant_id=tenant_id or "HOSP-DEFAULT",
                entity_type="bed",
                entity_id=bed_id,
                field_changed="status",
                old_value=old_status,
                new_value="OCCUPIED",
                changed_by=actor_id,
                change_reason="Confirmed physical arrival of patient at bed"
            )
            self.db.add(audit)

            # 5. Commit atomic transaction
            await self.db.commit()
            await self.db.refresh(bed)
        except Exception:
            await self.db.rollback()
            raise
        logger.info(f"Patient Arrival Confirmed: Bed {bed_id} OCCUPIED")

        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "BED_OCCUPIED",
            "tenant_id": tenant_id or "HOSP-DEFAULT",
            "source": "bed_service",
            "payload": {
                "bed_id": bed.id,
                "bed_type": bed.bed_type,
                "department_id": bed.department_id,
                "patient_id": bed.current_patient_id,
                "encounter_id": bed.current_encounter_id,
                "status": "OCCUPIED"
            }
        }, tenant_id=tenant_id or "HOSP-DEFAULT")

        return bed

    async def release_bed(
        self,
        bed_id: str,
        actor_id: str,
        actor_role: str,
        tenant_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Bed:
        """
        Releases an OCCUPIED, RESERVED, or CLEANING bed with row-level lock.
        State transition: OCCUPIED/RESERVED -> AVAILABLE.
        Updates active BedAssignment to RELEASED and sets released_at timestamp.
        """
        # 1. Pessimistic Row Lock on target Bed
        bed_query = select(Bed).where(Bed.id == bed_id)
        if tenant_id:
            bed_query = bed_query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        res_bed = await self.db.execute(bed_query.with_for_update())
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        if bed.status not in ["OCCUPIED", "RESERVED", "CLEANING", "BLOCKED", "MAINTENANCE"]:
            raise HTTPException(status_code=400, detail=f"Bed {bed_id} is already '{bed.status}'")

        old_status = bed.status
        old_patient_id = bed.current_patient_id
        old_encounter_id = bed.current_encounter_id

        try:
            # 2. Mutate Bed state
            bed.status = "AVAILABLE"
            bed.current_patient_id = None
            bed.current_encounter_id = None
            bed.last_cleaned_at = utc_now()

            # 3. Update active BedAssignment record if exists
            assignment_query = select(BedAssignment).where(
                BedAssignment.bed_id == bed_id,
                BedAssignment.status.in_(["RESERVED", "OCCUPIED"])
            ).order_by(BedAssignment.reserved_at.desc())
            res_assign = await self.db.execute(assignment_query)
            assignment = res_assign.scalars().first()
            if assignment:
                assignment.status = "RELEASED"
                assignment.released_at = utc_now()

            # 4. If encounter was linked, update encounter bed assignment
            if old_encounter_id:
                res_enc = await self.db.execute(select(Encounter).where(Encounter.id == old_encounter_id))
                encounter = res_enc.scalars().first()
                if encounter and encounter.current_bed_id == bed_id:
                    encounter.current_bed_id = None

            # 5. Audit Log
            audit = AuditLog(
                tenant_id=tenant_id or "HOSP-DEFAULT",
                entity_type="bed",
                entity_id=bed_id,
                field_changed="status",
                old_value=old_status,
                new_value="AVAILABLE",
                changed_by=actor_id,
                change_reason=reason or "Bed discharged and released to available pool"
            )
            self.db.add(audit)

            # 6. Commit atomic transaction
            await self.db.commit()
            await self.db.refresh(bed)
        except Exception:
            await self.db.rollback()
            raise
        logger.info(f"Bed Released: Bed {bed_id} transitioned from {old_status} to AVAILABLE by {actor_id}")

        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "BED_RELEASED",
            "tenant_id": tenant_id or "HOSP-DEFAULT",
            "source": "bed_service",
            "payload": {
                "bed_id": bed.id,
                "bed_type": bed.bed_type,
                "department_id": bed.department_id,
                "previous_patient_id": old_patient_id,
                "previous_encounter_id": old_encounter_id,
                "status": "AVAILABLE"
            }
        }, tenant_id=tenant_id or "HOSP-DEFAULT")

        return bed

    async def update_bed_status(
        self,
        bed_id: str,
        status: str,
        actor_id: str,
        actor_role: str,
        tenant_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Bed:
        """
        Directly update bed status (AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE, CLEANING, BLOCKED)
        with pessimistic locking and audit trail.
        """
        valid_statuses = ["AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE", "CLEANING", "BLOCKED"]
        status = status.upper()
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of {valid_statuses}")

        bed_query = select(Bed).where(Bed.id == bed_id)
        if tenant_id:
            bed_query = bed_query.join(Department, Bed.department_id == Department.id).where(Department.tenant_id == tenant_id)
        res_bed = await self.db.execute(bed_query.with_for_update())
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")

        old_status = bed.status
        if old_status == status:
            return bed

        try:
            bed.status = status
            if status == "AVAILABLE":
                bed.current_patient_id = None
                bed.current_encounter_id = None
                bed.last_cleaned_at = utc_now()
                assignment_query = select(BedAssignment).where(
                    BedAssignment.bed_id == bed_id,
                    BedAssignment.status.in_(["RESERVED", "OCCUPIED"])
                ).order_by(BedAssignment.reserved_at.desc())
                res_assign = await self.db.execute(assignment_query)
                assignment = res_assign.scalars().first()
                if assignment:
                    assignment.status = "RELEASED"
                    assignment.released_at = utc_now()

            audit = AuditLog(
                tenant_id=tenant_id or "HOSP-DEFAULT",
                entity_type="bed",
                entity_id=bed_id,
                field_changed="status",
                old_value=old_status,
                new_value=status,
                changed_by=actor_id,
                change_reason=reason or f"Bed status manually changed from {old_status} to {status} by {actor_role} {actor_id}"
            )
            self.db.add(audit)
            await self.db.commit()
            await self.db.refresh(bed)
        except Exception:
            await self.db.rollback()
            raise

        logger.info(f"Bed Status Updated: {bed_id} transitioned from {old_status} to {status} by {actor_id}")

        event_name = "BED_RELEASED" if status == "AVAILABLE" else "BED_OCCUPIED" if status == "OCCUPIED" else "BED_RESERVED" if status == "RESERVED" else "BED_UPDATED"
        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": event_name,
            "tenant_id": tenant_id or "HOSP-DEFAULT",
            "source": "bed_service",
            "payload": {
                "bed_id": bed.id,
                "bed_type": bed.bed_type,
                "department_id": bed.department_id,
                "previous_status": old_status,
                "status": status,
                "reason": reason
            }
        }, tenant_id=tenant_id or "HOSP-DEFAULT")

        return bed

