import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Department, Bed, Staff, Equipment, Encounter,
    ApprovalItem, EmergencyEvent, AuditLog, AgentDecision, AgentMessage
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Hospital Dashboard State"])


@router.get("/state")
async def get_hospital_state(db: AsyncSession = Depends(get_db)):
    """
    Single unified endpoint returning the complete hospital operational state.
    This is the primary data source for the Command Center frontend.
    Designed to be polled every 2-3 seconds for near-real-time updates.
    """

    # Departments
    dept_result = await db.execute(select(Department))
    departments = dept_result.scalars().all()

    # Bed counts by status
    beds_result = await db.execute(select(Bed))
    all_beds = beds_result.scalars().all()
    bed_counts = {"AVAILABLE": 0, "RESERVED": 0, "OCCUPIED": 0, "CLEANING": 0, "MAINTENANCE": 0, "BLOCKED": 0}
    for b in all_beds:
        bed_counts[b.status] = bed_counts.get(b.status, 0) + 1

    # Dynamic Department ID resolution from database
    icu_dept_ids = {d.id for d in departments if d.code == "ICU"}
    er_dept_ids = {d.id for d in departments if d.code == "ER"}

    # ICU specific
    icu_beds = [b for b in all_beds if b.department_id in icu_dept_ids or b.bed_type == "ICU"]
    icu_occupied = sum(1 for b in icu_beds if b.status in ("OCCUPIED", "RESERVED"))
    icu_total = len(icu_beds)

    # ER specific
    er_beds = [b for b in all_beds if b.department_id in er_dept_ids or b.bed_type == "EMERGENCY"]
    er_occupied = sum(1 for b in er_beds if b.status in ("OCCUPIED", "RESERVED"))

    # Staff counts by status
    staff_result = await db.execute(select(Staff))
    all_staff = staff_result.scalars().all()
    staff_available = sum(1 for s in all_staff if s.status == "AVAILABLE")
    staff_busy = sum(1 for s in all_staff if s.status == "BUSY")
    doctors_on = sum(1 for s in all_staff if s.role == "DOCTOR" and s.status in ("AVAILABLE", "BUSY"))
    nurses_on = sum(1 for s in all_staff if s.role in ("NURSE", "CHARGE_NURSE") and s.status in ("AVAILABLE", "BUSY"))

    # Equipment
    eq_result = await db.execute(select(Equipment))
    all_eq = eq_result.scalars().all()
    eq_available = sum(1 for e in all_eq if e.status == "AVAILABLE")
    eq_in_use = sum(1 for e in all_eq if e.status == "IN_USE")

    # Active encounters
    enc_result = await db.execute(select(Encounter).where(Encounter.status == "ACTIVE"))
    active_encounters = enc_result.scalars().all()

    # Pending approvals
    apr_result = await db.execute(select(ApprovalItem).where(ApprovalItem.status == "PENDING"))
    pending_approvals = apr_result.scalars().all()

    # Active emergencies
    emr_result = await db.execute(select(EmergencyEvent).where(EmergencyEvent.status == "ACTIVE"))
    active_emergencies = emr_result.scalars().all()

    # Agent decisions stats
    dec_result = await db.execute(select(AgentDecision))
    all_decisions = dec_result.scalars().all()
    total_decisions = len(all_decisions)
    approved_decisions = sum(1 for d in all_decisions if d.status == "APPROVED")
    acceptance_rate = round((approved_decisions / max(total_decisions, 1)) * 100, 1)

    # Audit log count
    audit_count_result = await db.execute(select(func.count(AuditLog.id)))
    audit_count = audit_count_result.scalar() or 0

    return {
        "hospital_mode": "EMERGENCY" if active_emergencies else "NORMAL",
        "active_emergencies": len(active_emergencies),

        "beds": {
            "total": len(all_beds),
            **bed_counts,
            "utilization_pct": round(((bed_counts["OCCUPIED"] + bed_counts["RESERVED"]) / max(len(all_beds), 1)) * 100, 1),
        },
        "icu": {
            "total": icu_total,
            "occupied": icu_occupied,
            "available": icu_total - icu_occupied,
            "utilization_pct": round((icu_occupied / max(icu_total, 1)) * 100, 1),
        },
        "er": {
            "beds_occupied": er_occupied,
            "beds_total": len(er_beds),
            "active_patients": sum(1 for e in active_encounters if e.current_department_id in er_dept_ids),
        },

        "staff": {
            "total": len(all_staff),
            "available": staff_available,
            "busy": staff_busy,
            "doctors_on_duty": doctors_on,
            "nurses_on_duty": nurses_on,
        },

        "equipment": {
            "total": len(all_eq),
            "available": eq_available,
            "in_use": eq_in_use,
        },

        "patients": {
            "active_encounters": len(active_encounters),
            "pending_triage": sum(1 for e in active_encounters if e.patient_status in ("ARRIVED", "REGISTERED")),
            "waiting_for_doctor": sum(1 for e in active_encounters if e.patient_status == "WAITING_FOR_DOCTOR"),
            "under_treatment": sum(1 for e in active_encounters if e.patient_status == "IN_TREATMENT"),
        },

        "approvals": {
            "pending": len(pending_approvals),
        },

        "agent_performance": {
            "total_decisions": total_decisions,
            "approved": approved_decisions,
            "acceptance_rate_pct": acceptance_rate,
        },

        "audit_log_entries": audit_count,
    }


@router.get("/departments/summary")
async def get_departments_summary(db: AsyncSession = Depends(get_db)):
    """Get per-department summary with bed utilization and staffing data."""
    dept_result = await db.execute(select(Department))
    departments = dept_result.scalars().all()

    beds_result = await db.execute(select(Bed))
    all_beds = beds_result.scalars().all()

    staff_result = await db.execute(select(Staff).where(Staff.status.in_(["AVAILABLE", "BUSY"])))
    active_staff = staff_result.scalars().all()

    summaries = []
    for dept in departments:
        dept_beds = [b for b in all_beds if b.department_id == dept.id]
        occupied = sum(1 for b in dept_beds if b.status in ("OCCUPIED", "RESERVED"))
        dept_doctors = sum(1 for s in active_staff if s.department_id == dept.id and s.role == "DOCTOR")
        dept_nurses = sum(1 for s in active_staff if s.department_id == dept.id and s.role in ("NURSE", "CHARGE_NURSE"))

        summaries.append({
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "beds_total": len(dept_beds),
            "beds_occupied": occupied,
            "beds_available": len(dept_beds) - occupied,
            "utilization_pct": round((occupied / max(len(dept_beds), 1)) * 100, 1) if dept_beds else 0,
            "doctors_active": dept_doctors,
            "nurses_active": dept_nurses,
            "min_doctors_required": dept.min_doctors,
            "min_nurses_required": dept.min_nurses,
            "staffing_adequate": dept_doctors >= dept.min_doctors and dept_nurses >= dept.min_nurses,
        })

    return summaries
