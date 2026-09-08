import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.bed import Bed
from app.models.staff import Staff
from app.models.equipment import Equipment
from app.models.patient import Encounter
from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.emergency import EmergencyEvent
from app.models.workflow import Queue, Task
from app.models.prediction import PredictionRun

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Application Service for Hospital Command Center Telemetry, Aggregated Metrics, and Department Summaries.
    Encapsulates read-side operational analytics across beds, staff, encounters, equipment, workflows, and predictions.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_hospital_state(self) -> Dict[str, Any]:
        """
        Produce a unified real-time operational state snapshot for the hospital command center.
        """
        # 1. Departments
        dept_result = await self.db.execute(select(Department))
        departments = dept_result.scalars().all()
        icu_dept_ids = {d.id for d in departments if d.code == "ICU"}
        er_dept_ids = {d.id for d in departments if d.code == "ER"}

        # 2. Beds
        beds_result = await self.db.execute(select(Bed))
        all_beds = beds_result.scalars().all()
        bed_counts = {"AVAILABLE": 0, "RESERVED": 0, "OCCUPIED": 0, "CLEANING": 0, "MAINTENANCE": 0, "BLOCKED": 0}
        for b in all_beds:
            bed_counts[b.status] = bed_counts.get(b.status, 0) + 1

        icu_beds = [b for b in all_beds if b.department_id in icu_dept_ids or b.bed_type == "ICU"]
        icu_occupied = sum(1 for b in icu_beds if b.status in ("OCCUPIED", "RESERVED"))
        icu_total = len(icu_beds)

        er_beds = [b for b in all_beds if b.department_id in er_dept_ids or b.bed_type == "EMERGENCY"]
        er_occupied = sum(1 for b in er_beds if b.status in ("OCCUPIED", "RESERVED"))

        # 3. Staff
        staff_result = await self.db.execute(select(Staff))
        all_staff = staff_result.scalars().all()
        staff_available = sum(1 for s in all_staff if s.status == "AVAILABLE")
        staff_busy = sum(1 for s in all_staff if s.status == "BUSY")
        doctors_on = sum(1 for s in all_staff if s.role == "DOCTOR" and s.status in ("AVAILABLE", "BUSY"))
        nurses_on = sum(1 for s in all_staff if s.role in ("NURSE", "CHARGE_NURSE") and s.status in ("AVAILABLE", "BUSY"))

        # 4. Equipment
        eq_result = await self.db.execute(select(Equipment))
        all_eq = eq_result.scalars().all()
        eq_available = sum(1 for e in all_eq if e.status == "AVAILABLE")
        eq_in_use = sum(1 for e in all_eq if e.status == "IN_USE")

        # 5. Active Encounters
        enc_result = await self.db.execute(select(Encounter).where(Encounter.status == "ACTIVE"))
        active_encounters = enc_result.scalars().all()

        # 6. Approvals
        apr_result = await self.db.execute(select(ApprovalItem).where(ApprovalItem.status == "PENDING"))
        pending_approvals = apr_result.scalars().all()

        # 7. Emergencies
        emr_result = await self.db.execute(select(EmergencyEvent).where(EmergencyEvent.status.in_(["ACTIVE", "ESCALATED"])))
        active_emergencies = emr_result.scalars().all()

        # 8. Agent Performance
        dec_result = await self.db.execute(select(AgentDecision))
        all_decisions = dec_result.scalars().all()
        total_decisions = len(all_decisions)
        approved_decisions = sum(1 for d in all_decisions if d.status == "APPROVED")
        acceptance_rate = round((approved_decisions / max(total_decisions, 1)) * 100, 1)

        # 9. Audit Entries
        audit_count_result = await self.db.execute(select(func.count(AuditLog.id)))
        audit_count = audit_count_result.scalar() or 0

        # 10. Clinical Priorities
        from app.models.priority import ClinicalPriorityRecommendation
        pri_result = await self.db.execute(select(ClinicalPriorityRecommendation))
        all_pri = pri_result.scalars().all()
        critical_pri = sum(1 for p in all_pri if p.priority_level == "CRITICAL" and p.status != "EXPIRED")
        high_pri = sum(1 for p in all_pri if p.priority_level == "HIGH" and p.status != "EXPIRED")
        mod_pri = sum(1 for p in all_pri if p.priority_level == "MODERATE" and p.status != "EXPIRED")
        routine_pri = sum(1 for p in all_pri if p.priority_level == "ROUTINE" and p.status != "EXPIRED")
        pending_ack = sum(1 for p in all_pri if p.status == "GENERATED")
        overridden_pri = sum(1 for p in all_pri if p.status == "OVERRIDDEN")

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

            "clinical_priorities": {
                "total": len(all_pri),
                "critical": critical_pri,
                "high": high_pri,
                "moderate": mod_pri,
                "routine": routine_pri,
                "pending_acknowledgement": pending_ack,
                "overridden": overridden_pri
            },

            "agent_performance": {
                "total_decisions": total_decisions,
                "approved": approved_decisions,
                "acceptance_rate_pct": acceptance_rate,
            },

            "audit_log_entries": audit_count,
        }

    async def get_departments_summary(self) -> List[Dict[str, Any]]:
        """
        Calculate per-department summary with capacity metrics, bed occupancy, and staffing adequacy.
        """
        dept_result = await self.db.execute(select(Department))
        departments = dept_result.scalars().all()

        beds_result = await self.db.execute(select(Bed))
        all_beds = beds_result.scalars().all()

        staff_result = await self.db.execute(select(Staff).where(Staff.status.in_(["AVAILABLE", "BUSY"])))
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

    async def get_department_overview(self, department_id: str) -> Dict[str, Any]:
        """
        Detailed single-department command center telemetry.
        """
        from fastapi import HTTPException
        dept_res = await self.db.execute(select(Department).where(Department.id == department_id))
        dept = dept_res.scalars().first()
        if not dept:
            raise HTTPException(status_code=404, detail=f"Department {department_id} not found")

        # Beds
        beds_res = await self.db.execute(select(Bed).where(Bed.department_id == department_id))
        dept_beds = beds_res.scalars().all()
        occupied = sum(1 for b in dept_beds if b.status in ("OCCUPIED", "RESERVED"))

        # Staff
        staff_res = await self.db.execute(select(Staff).where(Staff.department_id == department_id))
        dept_staff = staff_res.scalars().all()
        doctors = sum(1 for s in dept_staff if s.role == "DOCTOR" and s.status in ("AVAILABLE", "BUSY"))
        nurses = sum(1 for s in dept_staff if s.role in ("NURSE", "CHARGE_NURSE") and s.status in ("AVAILABLE", "BUSY"))

        # Encounters
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.current_department_id == department_id, Encounter.status == "ACTIVE")
        )
        active_encs = enc_res.scalars().all()

        # Emergencies affecting this department
        emr_res = await self.db.execute(
            select(EmergencyEvent).where(EmergencyEvent.status.in_(["ACTIVE", "ESCALATED"]))
        )
        all_emrs = emr_res.scalars().all()
        affecting_emrs = [e for e in all_emrs if isinstance(e.affected_departments, list) and department_id in e.affected_departments]

        return {
            "department": {
                "id": dept.id,
                "name": dept.name,
                "code": dept.code,
                "nurse_patient_ratio": dept.nurse_patient_ratio
            },
            "beds": {
                "total": len(dept_beds),
                "occupied": occupied,
                "available": len(dept_beds) - occupied,
                "utilization_pct": round((occupied / max(len(dept_beds), 1)) * 100, 1) if dept_beds else 0
            },
            "staff": {
                "total": len(dept_staff),
                "doctors_active": doctors,
                "nurses_active": nurses,
                "staffing_adequate": doctors >= dept.min_doctors and nurses >= dept.min_nurses
            },
            "active_patients": len(active_encs),
            "active_emergencies": len(affecting_emrs)
        }

    async def get_command_center_telemetry(self) -> Dict[str, Any]:
        """
        Aggregated top-level telemetry including hospital overview, live queues, tasks, and latest predictions.
        """
        hospital_state = await self.get_hospital_state()

        # Queues
        q_res = await self.db.execute(select(Queue).where(Queue.status == "WAITING"))
        waiting_queues = q_res.scalars().all()

        # Tasks
        t_res = await self.db.execute(select(Task).where(Task.status.in_(["PENDING", "IN_PROGRESS"])))
        active_tasks = t_res.scalars().all()

        # Predictions
        p_res = await self.db.execute(select(PredictionRun).order_by(PredictionRun.created_at.desc()).limit(3))
        recent_predictions = p_res.scalars().all()

        return {
            "hospital_state": hospital_state,
            "waiting_queue_depth": len(waiting_queues),
            "active_tasks_count": len(active_tasks),
            "recent_predictions": [
                {
                    "id": p.id,
                    "prediction_type": p.prediction_type,
                    "model_name": p.model_name,
                    "confidence_score": p.confidence_score,
                    "recommended_action": p.recommended_action,
                    "created_at": p.created_at
                }
                for p in recent_predictions
            ]
        }
