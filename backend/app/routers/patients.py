import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.schemas.patient import PatientCreate, PatientResponse, EncounterCreate, EncounterResponse
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["Patients & Intake"])


# ─── Patient Endpoints ──────────────────────────────────────────────────────

@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_in: PatientCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Register a new patient in the hospital system with RBAC enforcement."""
    service = PatientService(db)
    return await service.register_patient(
        first_name=patient_in.first_name,
        last_name=patient_in.last_name,
        age=patient_in.age,
        gender=patient_in.gender,
        blood_group=patient_in.blood_group,
        contact_phone=patient_in.contact_phone,
        emergency_contact=patient_in.emergency_contact,
        allergies=patient_in.allergies,
        chronic_conditions=patient_in.chronic_conditions,
        actor_id=current_staff.id,
        actor_role=current_staff.role
    )


@router.get("", response_model=List[PatientResponse])
async def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by name, phone, or ID"),
    db: AsyncSession = Depends(get_db)
):
    """List all registered patients with optional pagination and search."""
    service = PatientService(db)
    if search:
        return await service.search_patients(query_str=search, limit=limit)
    return await service.list_patients(skip=skip, limit=limit)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Get patient details by ID."""
    service = PatientService(db)
    patient = await service.get_patient_by_id(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/history", response_model=List[EncounterResponse])
async def get_patient_history(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve full chronological hospital encounter history for a patient."""
    service = PatientService(db)
    return await service.get_patient_history(patient_id)


@router.get("/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve full unified chronological medical timeline across encounters and clinical intakes."""
    service = PatientService(db)
    return await service.get_patient_timeline(patient_id)


# ─── Encounter Endpoints ────────────────────────────────────────────────────

@router.post("/encounters", response_model=EncounterResponse, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    encounter_in: EncounterCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Create a new hospital intake encounter for a patient with RBAC enforcement."""
    service = EncounterService(db)
    return await service.create_encounter(
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
        actor_id=current_staff.id
    )


@router.get("/encounters/active", response_model=List[EncounterResponse])
async def list_active_encounters(db: AsyncSession = Depends(get_db)):
    """List all active hospital encounters."""
    service = EncounterService(db)
    return await service.list_active_encounters()


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(encounter_id: str, db: AsyncSession = Depends(get_db)):
    """Get details of a specific encounter."""
    service = EncounterService(db)
    encounter = await service.get_encounter_by_id(encounter_id)
    if not encounter:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return encounter
