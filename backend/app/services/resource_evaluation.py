"""
Resource Optimization Evaluation Engine & Deterministic Baseline
=================================================================
Provides a reproducible benchmark harness comparing the Multi-Agent LangGraph
coordination optimizer against a deterministic greedy (first-available) baseline.

Metrics Measured:
1. Allocation Feasibility Rate (% of plans meeting all hard constraints)
2. Resource Conflicts (duplicate bookings, overloaded staff)
3. Constraint Violations (unavailable beds, tenant mismatches, missing telemetry/isolation)
4. Allocation Completion Rate (% finding a plan)
5. Decision Latency (ms per scenario)
6. Human-in-the-Loop Gating Compliance
"""

import time
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.department import Department
from app.models.staff import Staff
from app.services.agent_graph import HospitalLangGraphOrchestrator

logger = logging.getLogger(__name__)


class DeterministicGreedyBaseline:
    """
    Simple Deterministic First-Available (FIFO/Greedy) Resource Allocator.
    - Picks the first available bed in lexicographical order for the encounter's department.
    - Picks the first doctor on duty without workload balancing or overload checks.
    - Does not negotiate counter-proposals or step-downs when department is full.
    - Does not perform multi-factor clinical risk gating.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def allocate(
        self,
        encounter: Encounter,
        patient: Patient,
        tenant_id: str = "HOSP-DEFAULT"
    ) -> Dict[str, Any]:
        start = time.perf_counter()

        # 1. Greedy Bed Search: Find first available bed matching department
        bed_query = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                Department.tenant_id == tenant_id,
                Bed.department_id == encounter.current_department_id,
                Bed.status == "AVAILABLE"
            )
            .order_by(Bed.id.asc())
        )
        res_bed = await self.db.execute(bed_query)
        candidate_bed = res_bed.scalars().first()

        # If not available in department, greedy fallback: first available bed anywhere in tenant
        if not candidate_bed:
            fallback_query = (
                select(Bed)
                .join(Department, Bed.department_id == Department.id)
                .where(
                    Department.tenant_id == tenant_id,
                    Bed.status == "AVAILABLE"
                )
                .order_by(Bed.id.asc())
            )
            res_fb = await self.db.execute(fallback_query)
            candidate_bed = res_fb.scalars().first()

        # 2. Greedy Staff Assignment: Pick first doctor in department
        staff_query = (
            select(Staff)
            .where(
                Staff.tenant_id == tenant_id,
                Staff.role == "DOCTOR",
                Staff.department_id == encounter.current_department_id
            )
            .order_by(Staff.id.asc())
        )
        res_staff = await self.db.execute(staff_query)
        candidate_doctor = res_staff.scalars().first()

        if not candidate_doctor:
            res_any_doc = await self.db.execute(
                select(Staff).where(Staff.tenant_id == tenant_id, Staff.role == "DOCTOR").order_by(Staff.id.asc())
            )
            candidate_doctor = res_any_doc.scalars().first()

        latency_ms = (time.perf_counter() - start) * 1000

        # 3. Evaluate Hard Constraints on Greedy Result
        violations = []
        is_feasible = True

        # Check Bed Requirements
        if not candidate_bed:
            violations.append("NO_BED_AVAILABLE")
            is_feasible = False
        else:
            # Check telemetry / isolation needs
            needs_isolation = "fever" in (encounter.chief_complaint or "").lower() and "rash" in (encounter.chief_complaint or "").lower()
            if needs_isolation and not candidate_bed.is_isolation:
                violations.append("ISOLATION_MISMATCH")
                is_feasible = False

            if encounter.esi_level == 1 and candidate_bed.bed_type not in ["ICU", "CARDIAC_MONITOR"]:
                violations.append("ACUITY_CARE_LEVEL_MISMATCH")
                is_feasible = False

        # Check Staff Overload
        if candidate_doctor and candidate_doctor.current_workload >= candidate_doctor.max_workload:
            violations.append("STAFF_CAPACITY_EXCEEDED")
            is_feasible = False

        return {
            "strategy": "GREEDY_BASELINE",
            "is_feasible": is_feasible,
            "violations": violations,
            "target_bed_id": candidate_bed.id if candidate_bed else None,
            "target_department_id": candidate_bed.department_id if candidate_bed else None,
            "assigned_doctor_id": candidate_doctor.id if candidate_doctor else None,
            "requires_human_approval": False,  # Baseline has no risk-gating
            "latency_ms": round(latency_ms, 2)
        }


class OptimizationEvaluator:
    """
    Evaluator comparing Multi-Agent LangGraph Optimizer against Deterministic Baseline.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.baseline = DeterministicGreedyBaseline(db)

    async def evaluate_scenario(
        self,
        encounter: Encounter,
        patient: Patient,
        tenant_id: str = "HOSP-DEFAULT",
        actor_id: str = "DOC-001"
    ) -> Dict[str, Any]:
        """
        Executes both strategies on the exact same scenario and returns comparative metrics.
        """
        # 1. Evaluate Baseline
        baseline_res = await self.baseline.allocate(encounter, patient, tenant_id=tenant_id)

        # 2. Evaluate Multi-Agent LangGraph Optimizer
        t0 = time.perf_counter()
        orchestrator = HospitalLangGraphOrchestrator(self.db, encounter, patient)
        opt_state = await orchestrator.run(tenant_id=tenant_id, actor_id=actor_id, force_recalculate=True)
        opt_latency_ms = (time.perf_counter() - t0) * 1000

        selected_plan = opt_state.get("selected_plan") or {}
        active_conflicts = opt_state.get("active_conflicts") or []
        violations = []

        target_bed = selected_plan.get("target_bed_id")
        hard_pass = selected_plan.get("hard_constraint_pass", False)

        # Check telemetry / isolation needs
        needs_isolation = "fever" in (encounter.chief_complaint or "").lower() and "rash" in (encounter.chief_complaint or "").lower()
        if target_bed:
            b_obj = await self.db.get(Bed, target_bed)
            if b_obj and needs_isolation and not b_obj.is_isolation:
                violations.append("ISOLATION_MISMATCH")
            if b_obj and encounter.esi_level == 1 and b_obj.bed_type not in ["ICU", "CARDIAC_MONITOR"]:
                violations.append("ACUITY_CARE_LEVEL_MISMATCH")

        optimizer_res = {
            "strategy": "MULTI_AGENT_LANGGRAPH_OPTIMIZER",
            "is_feasible": hard_pass and len(violations) == 0,
            "violations": violations,
            "conflicts_detected": len(active_conflicts),
            "negotiation_status": opt_state.get("negotiation_status", "NONE"),
            "target_bed_id": target_bed,
            "target_department_id": selected_plan.get("target_department_id"),
            "assigned_doctor_id": selected_plan.get("assigned_doctor_id"),
            "assigned_nurse_id": selected_plan.get("assigned_nurse_id"),
            "requires_human_approval": opt_state.get("requires_human_approval", False),
            "risk_level": opt_state.get("risk_level", "LOW"),
            "candidate_plans_count": len(opt_state.get("candidate_plans") or []),
            "latency_ms": round(opt_latency_ms, 2)
        }

        return {
            "encounter_id": encounter.id,
            "patient_id": patient.id,
            "baseline": baseline_res,
            "optimizer": optimizer_res
        }
