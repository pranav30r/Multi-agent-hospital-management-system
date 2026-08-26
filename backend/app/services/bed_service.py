import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bed import Bed, BedAssignment
from app.models.department import Department
from app.models.patient import Encounter
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class BedService:
    """
    Application Service for Hospital Bed & Department Allocation.
    Encapsulates state transitions, pessimistic concurrency locking, and audit trail orchestration.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_departments(self) -> List[Department]:
        """Query all hospital departments and current capacity metrics."""
        res = await self.db.execute(select(Department))
        return res.scalars().all()

    async def list_beds(
        self,
        department_id: Optional[str] = None,
        bed_status: Optional[str] = None
    ) -> List[Bed]:
        """Query hospital beds with optional department and status filters."""
        query = select(Bed)
        if department_id:
            query = query.where(Bed.department_id == department_id)
        if bed_status:
            query = query.where(Bed.status == bed_status)
        res = await self.db.execute(query)
        return res.scalars().all()

    async def get_bed_by_id(self, bed_id: str) -> Optional[Bed]:
        """Fetch a bed by its unique identifier."""
        res = await self.db.execute(select(Bed).where(Bed.id == bed_id))
        return res.scalars().first()

    async def reserve_bed(
        self,
        bed_id: str,
        patient_id: str,
        encounter_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "Direct clinician assignment"
    ) -> Bed:
        """
        Atomically reserve an AVAILABLE bed for a patient encounter.
        Enforces SELECT ... FOR UPDATE pessimistic row-level concurrency lock.
        State transition: AVAILABLE -> RESERVED
        """
        # 1. Pessimistic Row Lock on target Bed
        res_bed = await self.db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        if bed.status != "AVAILABLE":
            raise HTTPException(
                status_code=400,
                detail=f"Bed {bed_id} is in '{bed.status}' state and cannot be booked"
            )

        # 2. Verify Encounter existence
        res_enc = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
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
        encounter.bed_reserved_time = datetime.utcnow()
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
        return bed

    async def confirm_patient_arrival(
        self,
        bed_id: str,
        actor_id: str,
        actor_role: str
    ) -> Bed:
        """
        Confirms physical arrival of patient at the reserved bed with row-level lock.
        State transition: RESERVED -> OCCUPIED
        """
        # 1. Pessimistic Row Lock on target Bed
        res_bed = await self.db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
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
                encounter.bed_occupied_time = datetime.utcnow()
                encounter.patient_status = "ADMITTED"

        # 4. Record AuditLog entry
        audit = AuditLog(
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
        logger.info(f"Physical arrival confirmed: Bed {bed_id} is now OCCUPIED by {actor_id}")
        return bed
