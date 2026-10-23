import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.models.patient import Patient
from app.auth.dependencies import require_roles, get_current_staff, get_current_tenant
from app.schemas.patient import PatientCreate, PatientResponse, EncounterCreate, EncounterResponse, EncounterStaffAssignment
from app.services.patient_service import PatientService
from app.services.encounter_service import EncounterService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["Patients & Intake"])


# ─── Patient Endpoints ──────────────────────────────────────────────────────

@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_in: PatientCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST"])),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Register a new patient in the hospital system with RBAC & tenant enforcement."""
    service = PatientService(db)
    return await service.register_patient(
        first_name=patient_in.first_name,
        last_name=patient_in.last_name,
        age=patient_in.age,
        gender=patient_in.gender,
        blood_group=patient_in.blood_group,
        contact_phone=patient_in.contact_phone,
        emergency_contact=patient_in.emergency_contact,
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        tenant_id=tenant_id,
        allergies=patient_in.allergies,
        chronic_conditions=patient_in.chronic_conditions
    )


@router.get("", response_model=List[PatientResponse])
async def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by name, phone, or ID"),
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List all registered patients for the authenticated hospital tenant."""
    service = PatientService(db)
    if search:
        return await service.search_patients(query_str=search, limit=limit, tenant_id=tenant_id)
    return await service.list_patients(skip=skip, limit=limit, tenant_id=tenant_id)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: str,
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get patient details by ID within authenticated tenant boundary."""
    service = PatientService(db)
    patient = await service.get_patient_by_id(patient_id, tenant_id=tenant_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/history", response_model=List[EncounterResponse])
async def get_patient_history(
    patient_id: str,
    current_staff: Staff = Depends(get_current_staff),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve full chronological hospital encounter history for a patient."""
    service = PatientService(db)
    return await service.get_patient_history(patient_id, tenant_id=tenant_id)


@router.get("/{patient_id}/timeline")
async def get_patient_timeline(
    patient_id: str,
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
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
    """Create a new hospital intake encounter for a patient with RBAC & tenant enforcement."""
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
        actor_id=current_staff.id,
        tenant_id=current_staff.tenant_id
    )


@router.get("/encounters/active", response_model=List[EncounterResponse])
async def list_active_encounters(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant_id: str = Depends(get_current_tenant),
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List all active hospital encounters scoped to the authenticated tenant."""
    service = EncounterService(db)
    encounters = await service.list_active_encounters(tenant_id=tenant_id, skip=skip, limit=limit)
    patient_ids = {encounter.patient_id for encounter in encounters}
    patients_result = await db.execute(
        select(Patient).where(Patient.id.in_(patient_ids), Patient.tenant_id == tenant_id)
    ) if patient_ids else None
    patients = {patient.id: patient for patient in patients_result.scalars().all()} if patients_result else {}
    response = []
    for encounter in encounters:
        item = EncounterResponse.model_validate(encounter).model_dump()
        patient = patients.get(encounter.patient_id)
        if patient:
            item.update({
                "patient_name": f"{patient.first_name} {patient.last_name}".strip(),
                "age": patient.age,
                "gender": patient.gender,
            })
        response.append(item)
    return response


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: str,
    tenant_id: str = Depends(get_current_tenant),
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific encounter within tenant boundary."""
    service = EncounterService(db)
    encounter = await service.get_encounter_by_id(encounter_id, tenant_id=tenant_id)
    if not encounter:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return encounter


@router.patch("/encounters/{encounter_id}/staff", response_model=EncounterResponse)
async def assign_encounter_staff(
    encounter_id: str,
    assignment: EncounterStaffAssignment,
    tenant_id: str = Depends(get_current_tenant),
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Manually assign currently available, unassigned clinicians to an active encounter."""
    service = EncounterService(db)
    encounter = await service.get_encounter_by_id(encounter_id, tenant_id=tenant_id)
    if not encounter or encounter.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Active encounter not found")

    choices = ((assignment.doctor_id, {"DOCTOR"}, "assigned_doctor_id"),
               (assignment.nurse_id, {"NURSE", "CHARGE_NURSE"}, "assigned_nurse_id"))
    for staff_id, roles, field in choices:
        if staff_id is None:
            continue
        staff_result = await db.execute(
            select(Staff).where(Staff.id == staff_id, Staff.tenant_id == tenant_id).with_for_update()
        )
        staff_member = staff_result.scalars().first()
        if not staff_member or staff_member.role not in roles:
            raise HTTPException(status_code=400, detail=f"{staff_id} is not an eligible {field.removeprefix('assigned_')}")
        if staff_member.status != "AVAILABLE" or staff_member.current_workload >= staff_member.max_workload:
            raise HTTPException(status_code=409, detail=f"{staff_id} is busy or at workload capacity")
        conflict_result = await db.execute(
            select(Encounter.id)
            .join(Patient, Encounter.patient_id == Patient.id)
            .where(
                Patient.tenant_id == tenant_id,
                Encounter.status == "ACTIVE",
                Encounter.id != encounter.id,
                getattr(Encounter, field) == staff_id,
            )
        )
        if conflict_result.first():
            raise HTTPException(status_code=409, detail=f"{staff_id} is already assigned to another active patient")
        setattr(encounter, field, staff_id)
        staff_member.status = "BUSY"

    await db.commit()
    await db.refresh(encounter)
    return encounter
