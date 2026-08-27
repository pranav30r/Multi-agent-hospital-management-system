import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class PatientService:
    """
    Application Service for Patient Master Records, Registration, and Medical Profile Lookup.
    Encapsulates duplicate checks, patient lookup, profile mutations, and clinical history queries.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_patient(
        self,
        first_name: str,
        last_name: str,
        age: int,
        gender: str,
        blood_group: str,
        contact_phone: str,
        emergency_contact: str,
        actor_id: str,
        actor_role: str,
        allergies: Optional[List[str]] = None,
        chronic_conditions: Optional[List[str]] = None
    ) -> Patient:
        """
        Register a new patient master record with audit trail.
        """
        # Conservative lookup: check if identical patient already exists
        existing_res = await self.db.execute(
            select(Patient).where(
                Patient.contact_phone == contact_phone,
                func.lower(Patient.first_name) == first_name.strip().lower(),
                func.lower(Patient.last_name) == last_name.strip().lower()
            )
        )
        existing = existing_res.scalars().first()
        if existing:
            logger.info(f"Returning existing patient record {existing.id} for phone {contact_phone}")
            return existing

        patient = Patient(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            age=age,
            gender=gender.upper(),
            blood_group=blood_group.upper(),
            contact_phone=contact_phone.strip(),
            emergency_contact=emergency_contact.strip(),
            allergies=allergies or [],
            chronic_conditions=chronic_conditions or [],
            created_at=datetime.utcnow()
        )
        self.db.add(patient)
        await self.db.flush()

        audit = AuditLog(
            entity_type="patient",
            entity_id=patient.id,
            field_changed="registration",
            old_value=None,
            new_value="REGISTERED",
            changed_by=actor_id,
            change_reason=f"Patient registered by {actor_role}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(patient)
        logger.info(f"Registered patient {patient.id} ({patient.first_name} {patient.last_name}) by {actor_id}")
        return patient

    async def list_patients(self, skip: int = 0, limit: int = 50) -> List[Patient]:
        """List registered patients with pagination."""
        result = await self.db.execute(select(Patient).offset(skip).limit(limit))
        return result.scalars().all()

    async def get_patient_by_id(self, patient_id: str) -> Optional[Patient]:
        """Retrieve patient details by primary key ID."""
        result = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        return result.scalars().first()

    async def find_patient_by_phone(self, phone: str) -> Optional[Patient]:
        """Find an existing patient by primary contact phone number."""
        result = await self.db.execute(select(Patient).where(Patient.contact_phone == phone.strip()))
        return result.scalars().first()

    async def search_patients(self, query_str: str, limit: int = 20) -> List[Patient]:
        """Search patients by ID, first name, last name, or phone."""
        term = f"%{query_str.strip().lower()}%"
        stmt = select(Patient).where(
            or_(
                func.lower(Patient.id).like(term),
                func.lower(Patient.first_name).like(term),
                func.lower(Patient.last_name).like(term),
                Patient.contact_phone.like(term)
            )
        ).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_patient(
        self,
        patient_id: str,
        updates: Dict[str, Any],
        actor_id: str
    ) -> Patient:
        """Update patient demographics or medical profile with row-level lock and audit."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id).with_for_update()
        )
        patient = result.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        allowed_fields = [
            "first_name", "last_name", "age", "gender", "blood_group",
            "contact_phone", "emergency_contact", "allergies", "chronic_conditions"
        ]
        changed_fields = []
        for field in allowed_fields:
            if field in updates and updates[field] is not None:
                setattr(patient, field, updates[field])
                changed_fields.append(field)

        if changed_fields:
            audit = AuditLog(
                entity_type="patient",
                entity_id=patient_id,
                field_changed="profile_update",
                old_value=None,
                new_value=",".join(changed_fields),
                changed_by=actor_id,
                change_reason=f"Updated fields: {', '.join(changed_fields)}"
            )
            self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def get_patient_history(self, patient_id: str) -> List[Encounter]:
        """Retrieve full chronological hospital encounter history for a patient."""
        patient = await self.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        res = await self.db.execute(
            select(Encounter).where(Encounter.patient_id == patient_id).order_by(Encounter.arrival_time.desc())
        )
        return res.scalars().all()

    async def get_patient_timeline(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieve unified chronological clinical timeline for a patient."""
        from app.services.clinical_intake_service import ClinicalIntakeService
        intake_service = ClinicalIntakeService(self.db)
        return await intake_service.get_patient_timeline(patient_id)
