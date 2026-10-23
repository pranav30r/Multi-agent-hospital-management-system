import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.department import Department
from app.models.agent import AuditLog
from app.models.staff import Staff
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class EncounterService:
    """
    Application Service for Clinical Hospital Intake Encounters, Triage, and Operational Lifecycles.
    Encapsulates patient verification, department routing, vitals logging, state transitions, and audit tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_encounter(
        self,
        patient_id: str,
        chief_complaint: str,
        encounter_type: str,
        current_department_id: Optional[str],
        actor_id: str,
        heart_rate: Optional[int] = None,
        bp_systolic: Optional[int] = None,
        bp_diastolic: Optional[int] = None,
        spo2: Optional[int] = None,
        temperature_f: Optional[float] = None,
        pain_level: Optional[int] = None,
        respiratory_rate: Optional[int] = None,
        gcs_score: Optional[int] = None,
        tenant_id: str = "HOSP-DEFAULT"
    ) -> Encounter:
        """
        Create a new clinical intake encounter for a validated patient.
        State: -> ACTIVE (patient_status: REGISTERED)
        """
        tenant_id = tenant_id or "HOSP-DEFAULT"

        # 1. Confirm patient exists and belongs to authenticated tenant
        p_query = select(Patient).where(
            and_(
                Patient.id == patient_id,
                Patient.tenant_id == tenant_id
            )
        )
        p_res = await self.db.execute(p_query)
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        # 2. Validate department reference dynamically from database within tenant
        target_dept_id = current_department_id
        if target_dept_id:
            d_res = await self.db.execute(
                select(Department.id).where(
                    and_(
                        Department.id == target_dept_id,
                        Department.tenant_id == tenant_id
                    )
                )
            )
            dept = d_res.scalars().first()
            if not dept:
                raise HTTPException(status_code=400, detail=f"Department {target_dept_id} does not exist for tenant {tenant_id}")
        else:
            # Query default emergency department dynamically by code within tenant
            d_res = await self.db.execute(
                select(Department.id).where(
                    and_(
                        Department.code.in_(["ER", "ED", "EMERGENCY"]),
                        Department.tenant_id == tenant_id
                    )
                )
            )
            target_dept_id = d_res.scalars().first()
            if not target_dept_id:
                d_fallback = await self.db.execute(
                    select(Department.id).where(Department.tenant_id == tenant_id).limit(1)
                )
                target_dept_id = d_fallback.scalars().first()

        type_clean = encounter_type.upper() if encounter_type else "INPATIENT"

        encounter = Encounter(
            patient_id=patient_id,
            chief_complaint=chief_complaint,
            encounter_type=type_clean,
            current_department_id=target_dept_id or "DEP-ER",
            heart_rate=heart_rate,
            bp_systolic=bp_systolic,
            bp_diastolic=bp_diastolic,
            spo2=spo2,
            temperature_f=temperature_f,
            pain_level=pain_level,
            respiratory_rate=respiratory_rate,
            gcs_score=gcs_score,
            status="ACTIVE",
            patient_status="REGISTERED",
            arrival_time=utc_now(),
            registration_time=utc_now()
        )
        self.db.add(encounter)
        await self.db.flush()

        # Audit trail creation
        audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="encounter",
            entity_id=encounter.id,
            field_changed="creation",
            old_value=None,
            new_value="ACTIVE",
            changed_by=actor_id,
            change_reason=f"Created encounter for patient {patient_id}: {chief_complaint[:50]}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(encounter)
        logger.info(f"Created encounter {encounter.id} for patient {patient_id} by {actor_id}")
        return encounter

    async def get_encounter_by_id(self, encounter_id: str, tenant_id: Optional[str] = None) -> Optional[Encounter]:
        """Fetch encounter details by ID with optional tenant scope."""
        stmt = select(Encounter).where(Encounter.id == encounter_id)
        if tenant_id:
            stmt = stmt.join(Patient, Encounter.patient_id == Patient.id).where(Patient.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_active_encounters(
        self,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[Encounter]:
        """Query all currently active hospital encounters strictly scoped to tenant."""
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required to list active encounters")

        stmt = select(Encounter).join(
            Patient, Encounter.patient_id == Patient.id
        ).where(
            and_(
                Encounter.status == "ACTIVE",
                Patient.tenant_id == tenant_id
            )
        ).order_by(desc(Encounter.arrival_time)).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_patient_encounters(self, patient_id: str) -> List[Encounter]:
        """Query all encounters associated with a specific patient."""
        result = await self.db.execute(
            select(Encounter).where(Encounter.patient_id == patient_id).order_by(desc(Encounter.arrival_time))
        )
        return result.scalars().all()

    async def update_encounter_vitals(
        self,
        encounter_id: str,
        vitals: Dict[str, Any],
        actor_id: str
    ) -> Encounter:
        """Update clinical intake vitals with row-level lock and audit."""
        result = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = result.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
        if encounter.status != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Cannot update vitals on a {encounter.status} encounter")

        vital_fields = [
            "heart_rate", "bp_systolic", "bp_diastolic", "spo2",
            "temperature_f", "pain_level", "respiratory_rate", "gcs_score"
        ]
        for field in vital_fields:
            if field in vitals and vitals[field] is not None:
                setattr(encounter, field, vitals[field])

        encounter.triage_time = utc_now()

        audit = AuditLog(
            entity_type="encounter",
            entity_id=encounter_id,
            field_changed="vitals",
            old_value=None,
            new_value="UPDATED",
            changed_by=actor_id,
            change_reason="Updated triage vital signs"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(encounter)
        return encounter

    async def update_clinical_state(
        self,
        encounter_id: str,
        actor_id: str,
        current_department_id: Optional[str] = None,
        assigned_doctor_id: Optional[str] = None,
        assigned_nurse_id: Optional[str] = None,
        current_bed_id: Optional[str] = None,
        esi_level: Optional[int] = None,
        priority: Optional[int] = None,
        patient_status: Optional[str] = None,
        diagnosis_notes: Optional[str] = None,
        diagnosed_diseases: Optional[List[str]] = None
    ) -> Encounter:
        """Update clinical assignment, triage priority, or diagnosis with row-level lock."""
        result = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = result.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
        if encounter.status != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Cannot update clinical state on a {encounter.status} encounter")

        if current_department_id is not None:
            encounter.current_department_id = current_department_id
        if assigned_doctor_id is not None:
            encounter.assigned_doctor_id = assigned_doctor_id
            encounter.doctor_assigned_time = utc_now()
        if assigned_nurse_id is not None:
            encounter.assigned_nurse_id = assigned_nurse_id
        if current_bed_id is not None:
            encounter.current_bed_id = current_bed_id
        if esi_level is not None:
            encounter.esi_level = esi_level
        if priority is not None:
            encounter.priority = priority
        if patient_status is not None:
            encounter.patient_status = patient_status
        if diagnosis_notes is not None:
            encounter.diagnosis_notes = diagnosis_notes
        if diagnosed_diseases is not None:
            encounter.diagnosed_diseases = diagnosed_diseases

        audit = AuditLog(
            entity_type="encounter",
            entity_id=encounter_id,
            field_changed="clinical_state",
            old_value=None,
            new_value=patient_status or "UPDATED",
            changed_by=actor_id,
            change_reason="Clinical state update"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(encounter)
        return encounter

    async def update_encounter_status(
        self,
        encounter_id: str,
        new_status: str,
        actor_id: str,
        reason: Optional[str] = None
    ) -> Encounter:
        """
        Enforce valid encounter lifecycle transitions (ACTIVE -> COMPLETED / CANCELLED).
        """
        result = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = result.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        status_clean = new_status.upper()
        if status_clean not in ["ACTIVE", "COMPLETED", "CANCELLED"]:
            raise HTTPException(status_code=400, detail=f"Invalid encounter status: {new_status}")

        if encounter.status in ["COMPLETED", "CANCELLED"] and status_clean == "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Cannot reactivate an already {encounter.status} encounter")

        old_status = encounter.status
        encounter.status = status_clean
        if status_clean == "COMPLETED":
            encounter.discharge_time = utc_now()
            encounter.patient_status = "DISCHARGED"
        if status_clean in ["COMPLETED", "CANCELLED"]:
            for staff_id in {encounter.assigned_doctor_id, encounter.assigned_nurse_id} - {None}:
                staff_result = await self.db.execute(select(Staff).where(Staff.id == staff_id).with_for_update())
                staff_member = staff_result.scalars().first()
                other_assignment = await self.db.execute(
                    select(Encounter.id).where(
                        Encounter.status == "ACTIVE",
                        Encounter.id != encounter.id,
                        or_(Encounter.assigned_doctor_id == staff_id, Encounter.assigned_nurse_id == staff_id),
                    )
                )
                if staff_member and staff_member.status == "BUSY" and not other_assignment.first():
                    staff_member.status = "AVAILABLE"

        audit = AuditLog(
            entity_type="encounter",
            entity_id=encounter_id,
            field_changed="status",
            old_value=old_status,
            new_value=status_clean,
            changed_by=actor_id,
            change_reason=reason or f"Encounter status transitioned to {status_clean}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(encounter)
        return encounter
