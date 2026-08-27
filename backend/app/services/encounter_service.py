import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.department import Department
from app.models.agent import AuditLog

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
        gcs_score: Optional[int] = None
    ) -> Encounter:
        """
        Create a new clinical intake encounter for a validated patient.
        State: -> ACTIVE (patient_status: REGISTERED)
        """
        # 1. Confirm patient exists
        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        # 2. Validate department reference
        target_dept_id = current_department_id or "DEP-ER"
        d_res = await self.db.execute(select(Department.id).where(Department.id == target_dept_id))
        dept = d_res.scalars().first()
        if not dept:
            # Fallback check for any valid department
            d_fallback = await self.db.execute(select(Department.id).limit(1))
            fallback_id = d_fallback.scalars().first()
            target_dept_id = fallback_id or "DEP-ER"

        encounter = Encounter(
            patient_id=patient_id,
            chief_complaint=chief_complaint,
            encounter_type=encounter_type.upper(),
            status="ACTIVE",
            current_department_id=target_dept_id,
            heart_rate=heart_rate,
            bp_systolic=bp_systolic,
            bp_diastolic=bp_diastolic,
            spo2=spo2,
            temperature_f=temperature_f,
            pain_level=pain_level,
            respiratory_rate=respiratory_rate,
            gcs_score=gcs_score,
            patient_status="REGISTERED",
            arrival_time=datetime.utcnow(),
            registration_time=datetime.utcnow()
        )
        self.db.add(encounter)
        await self.db.flush()

        audit = AuditLog(
            entity_type="encounter",
            entity_id=encounter.id,
            field_changed="intake",
            old_value=None,
            new_value="REGISTERED",
            changed_by=actor_id,
            change_reason=f"Encounter created for patient {patient_id} ({chief_complaint})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(encounter)
        logger.info(f"Created intake encounter {encounter.id} for patient {patient_id} by {actor_id}")
        return encounter

    async def get_encounter_by_id(self, encounter_id: str) -> Optional[Encounter]:
        """Fetch encounter details by ID."""
        result = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
        return result.scalars().first()

    async def list_active_encounters(self) -> List[Encounter]:
        """Query all currently active hospital encounters."""
        result = await self.db.execute(
            select(Encounter).where(Encounter.status == "ACTIVE").order_by(desc(Encounter.arrival_time))
        )
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

        encounter.triage_time = datetime.utcnow()

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
            encounter.doctor_assigned_time = datetime.utcnow()
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
            encounter.discharge_time = datetime.utcnow()
            encounter.patient_status = "DISCHARGED"

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
