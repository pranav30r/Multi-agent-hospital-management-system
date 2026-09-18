import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
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

        # 3. Apply state mutation on Bed
        old_status = bed.status
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
