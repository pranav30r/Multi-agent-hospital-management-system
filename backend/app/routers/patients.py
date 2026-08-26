import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Patient, Encounter, AuditLog, Staff
from app.auth.dependencies import require_roles
from app.schemas.patient import PatientCreate, PatientResponse, EncounterCreate, EncounterResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["Patients & Intake"])

@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_in: PatientCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Register a new patient in the hospital system with RBAC enforcement."""
    patient = Patient(
        first_name=patient_in.first_name,
        last_name=patient_in.last_name,
        age=patient_in.age,
        gender=patient_in.gender,
        blood_group=patient_in.blood_group,
        contact_phone=patient_in.contact_phone,
        emergency_contact=patient_in.emergency_contact,
        allergies=patient_in.allergies,
        chronic_conditions=patient_in.chronic_conditions
    )
    db.add(patient)
    await db.flush()

    audit = AuditLog(
        entity_type="patient",
        entity_id=patient.id,
        field_changed="registration",
        old_value=None,
        new_value="REGISTERED",
        changed_by=current_staff.id,
        change_reason=f"Patient registered by {current_staff.role}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(patient)
    logger.info(f"Registered patient: {patient.id} ({patient.first_name} {patient.last_name}) by {current_staff.id}")
    return patient

@router.get("", response_model=List[PatientResponse])
async def list_patients(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List all registered patients."""
    result = await db.execute(select(Patient).offset(skip).limit(limit))
    return result.scalars().all()

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Get patient details by ID."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.post("/encounters", response_model=EncounterResponse, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    encounter_in: EncounterCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Create a new hospital intake encounter for a patient with RBAC enforcement."""
    # Verify patient exists
    res = await db.execute(select(Patient).where(Patient.id == encounter_in.patient_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail=f"Patient {encounter_in.patient_id} not found")

    encounter = Encounter(
        patient_id=encounter_in.patient_id,
        chief_complaint=encounter_in.chief_complaint,
        encounter_type=encounter_in.encounter_type,
        current_department_id=encounter_in.current_department_id,
        heart_rate=encounter_in.heart_rate,
        bp_systolic=encounter_in.bp_systolic,
        bp_diastolic=encounter_in.bp_diastolic,
        spo2=encounter_in.spo2,
        temperature_f=encounter_in.temperature_f,
        pain_level=encounter_in.pain_level,
        respiratory_rate=encounter_in.respiratory_rate,
        gcs_score=encounter_in.gcs_score,
        patient_status="REGISTERED"
    )
    db.add(encounter)
    await db.flush()

    audit = AuditLog(
        entity_type="encounter",
        entity_id=encounter.id,
        field_changed="intake",
        old_value=None,
        new_value="REGISTERED",
        changed_by=current_staff.id,
        change_reason=f"Encounter created for patient {encounter_in.patient_id}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(encounter)
    logger.info(f"Created intake encounter {encounter.id} for patient {encounter.patient_id} by {current_staff.id}")
    return encounter

@router.get("/encounters/active", response_model=List[EncounterResponse])
async def list_active_encounters(db: AsyncSession = Depends(get_db)):
    """List all active hospital encounters."""
    result = await db.execute(select(Encounter).where(Encounter.status == "ACTIVE"))
    return result.scalars().all()
