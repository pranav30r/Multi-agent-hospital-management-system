"""
Autonomous Staff Scheduler & Workload Balancing Agent.
Monitors clinician rosters, shift schedules, nurse-to-patient load ratios, and doctor availability
to propose balanced clinical team assignments and shift coverage without modifying staff records directly.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Encounter, Patient
from app.models.agent import ApprovalItem, AgentDecision
from app.models.staff import Staff
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class StaffSchedulerAgent(BaseAgent):
    """
    Autonomous Staff Scheduler & Workload Balancing Agent.
    Monitors clinician rosters, shift schedules, nurse-to-patient load ratios, and doctor availability
    to propose balanced clinical team assignments and shift coverage without modifying staff records directly.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db=db, agent_id="staff_scheduler_agent", name="Staff Scheduler & Workload Balancing Agent")

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Evaluates clinical staffing capacity in the proposed target department.
        """
        dept_id = bed_output.get("recommended_department_id") or encounter.current_department_id or "DEP-ER"

        # Query all active staff
        staff_query = select(Staff).where(
            and_(
                Staff.tenant_id == tenant_id,
                Staff.status == "AVAILABLE"
            )
        )
        res = await self.db.execute(staff_query)
        all_staff: List[Staff] = res.scalars().all()

        assigned_result = await self.db.execute(
            select(Encounter.assigned_doctor_id, Encounter.assigned_nurse_id)
            .join(Patient, Encounter.patient_id == Patient.id)
            .where(
                Patient.tenant_id == tenant_id,
                Encounter.status == "ACTIVE",
                Encounter.id != encounter.id,
            )
        )
        occupied_staff_ids = {
            staff_id
            for assignment in assigned_result.all()
            for staff_id in assignment
            if staff_id
        }
        pending_result = await self.db.execute(
            select(ApprovalItem.proposed_action)
            .join(AgentDecision, ApprovalItem.decision_id == AgentDecision.id)
            .where(
                ApprovalItem.tenant_id == tenant_id,
                ApprovalItem.status == "PENDING",
                AgentDecision.encounter_id != encounter.id,
            )
        )
        for proposed_action in pending_result.scalars().all():
            if isinstance(proposed_action, dict):
                occupied_staff_ids.update(
                    staff_id for staff_id in (
                        proposed_action.get("assigned_doctor_id"),
                        proposed_action.get("assigned_nurse_id"),
                    ) if staff_id
                )

        doctors = [s for s in all_staff if s.role == "DOCTOR" and s.current_workload < s.max_workload and s.id not in occupied_staff_ids]
        nurses = [s for s in all_staff if s.role in ["NURSE", "CHARGE_NURSE"] and s.current_workload < s.max_workload and s.id not in occupied_staff_ids]

        # Prefer staff in the receiving department, then use the least-loaded
        # available hospital-wide clinician when that unit has no local coverage.
        dept_doctors = [d for d in doctors if d.department_id == dept_id]
        dept_nurses = [n for n in nurses if n.department_id == dept_id]

        # Select least loaded doctor and nurse
        assigned_doc = min(dept_doctors or doctors, key=lambda d: d.current_workload) if doctors else None
        assigned_nurse = min(dept_nurses or nurses, key=lambda n: n.current_workload) if nurses else None

        # Calculate average nurse workload
        receiving_nurses = dept_nurses or nurses
        avg_nurse_load = sum(n.current_workload for n in receiving_nurses) / len(receiving_nurses) if receiving_nurses else 0.0

        # Assess feasibility
        if avg_nurse_load and avg_nurse_load > 0:
            ratio_str = f"Avg Nurse Load: {avg_nurse_load:.1f} pts/nurse."
        else:
            ratio_str = "Active Nurse Load: 0 assigned patients (full capacity available)."

        if assigned_doc and assigned_nurse:
            coverage_scope = "receiving department" if dept_doctors and dept_nurses else "hospital-wide fallback"
            if assigned_nurse.current_workload >= assigned_nurse.max_workload:
                feasibility = "WARNING_OVERLOAD"
                rationale = (
                    f"Staff assignment feasible with load pressure: Doctor {assigned_doc.id} (load {assigned_doc.current_workload}/{assigned_doc.max_workload}), "
                    f"Nurse {assigned_nurse.id} at capacity ({assigned_nurse.current_workload}/{assigned_nurse.max_workload}). "
                    f"{ratio_str}"
                )
            elif not bed_output.get("recommended_bed_id"):
                feasibility = "FEASIBLE"
                rationale = (
                    f"Candidate clinical team identified: Doctor {assigned_doc.id}, Nurse {assigned_nurse.id}. "
                    f"Coverage: {coverage_scope}. "
                    f"Physical bed station is currently unavailable pending bed clearance. {ratio_str}"
                )
            else:
                feasibility = "FEASIBLE"
                rationale = (
                    f"Balanced team assigned: Doctor {assigned_doc.id} (load {assigned_doc.current_workload}/{assigned_doc.max_workload}), "
                    f"Nurse {assigned_nurse.id} (load {assigned_nurse.current_workload}/{assigned_nurse.max_workload}). "
                    f"Coverage: {coverage_scope}. {ratio_str}"
                )
        else:
            feasibility = "CRITICAL_SHORTAGE"
            rationale = "No unassigned on-duty doctor or nurse is available; existing active patient assignments and workload limits are respected. Assign manually when an eligible clinician is free."

        return {
            "agent_id": "staff_scheduler_agent",
            "status": "COMPLETED",
            "assigned_doctor_id": assigned_doc.id if assigned_doc else None,
            "assigned_nurse_id": assigned_nurse.id if assigned_nurse else None,
            "avg_nurse_load": round(avg_nurse_load, 1),
            "feasibility": feasibility,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def propose_rebalanced_workload(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        initial_staff_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Formulates a rebalanced staff allocation when primary clinician workload exceeds capacity.
        """
        query = select(Staff).where(
            and_(
                Staff.tenant_id == tenant_id,
                Staff.status == "AVAILABLE"
            )
        ).order_by(Staff.current_workload.asc())
        res = await self.db.execute(query)
        on_duty_staff = res.scalars().all()

        doctors = [s for s in on_duty_staff if s.role == "DOCTOR"]
        nurses = [s for s in on_duty_staff if s.role in ["NURSE", "CHARGE_NURSE"]]

        rebalanced_doc = doctors[0] if doctors else None
        rebalanced_nurse = nurses[0] if nurses else None

        return {
            "agent_id": "staff_scheduler_agent",
            "message_type": "REVISED_PROPOSAL",
            "assigned_doctor_id": rebalanced_doc.id if rebalanced_doc else None,
            "assigned_nurse_id": rebalanced_nurse.id if rebalanced_nurse else None,
            "feasibility": "REBALANCED" if (rebalanced_doc or rebalanced_nurse) else "CRITICAL_SHORTAGE",
            "rationale": f"Rebalanced staff assignment to Doctor {rebalanced_doc.id if rebalanced_doc else 'None'} and Nurse {rebalanced_nurse.id if rebalanced_nurse else 'None'}.",
            "timestamp": utc_now_iso()
        }


# Alias for backward compatibility
StaffWorkloadAgent = StaffSchedulerAgent
