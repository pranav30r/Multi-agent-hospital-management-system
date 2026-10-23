"""
Autonomous Multi-Agent Workflow Coordinator.
Synthesizes messages from all 5 specialized agents (Triage, Bed, Staff, Emergency Escalation,
and Patient Coordinator), detects operational conflicts, builds multi-objective candidate
operational plans, evaluates clinical safety policies, and routes consequential actions to
the Human-in-the-Loop approval queue.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.agent import (
    AgentDecision, AgentMessage, OptimizationRun,
    ApprovalItem, AuditLog
)
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    Autonomous Multi-Agent Workflow Coordinator.
    Synthesizes messages from all 5 specialized agents (Triage, Bed, Staff, Emergency Escalation,
    and Patient Coordinator), detects operational conflicts, builds multi-objective candidate
    operational plans, evaluates clinical safety policies, and routes consequential actions to
    the Human-in-the-Loop approval queue.
    """

    def __init__(
        self,
        db: AsyncSession,
        risk_engine: Optional[Any] = None,
        constraint_optimizer: Optional[Any] = None
    ):
        super().__init__(db=db, agent_id="coordinator_agent", name="Multi-Agent Workflow Coordinator")
        if risk_engine is None:
            from app.services.risk_engine import RiskEngine
            self.risk_engine = RiskEngine()
        else:
            self.risk_engine = risk_engine

        if constraint_optimizer is None:
            from app.services.constraint_optimizer import ConstraintOptimizer
            self.constraint_optimizer = ConstraintOptimizer()
        else:
            self.constraint_optimizer = constraint_optimizer

    async def coordinate(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        staff_output: Dict[str, Any],
        emergency_output: Dict[str, Any],
        coordinator_output: Dict[str, Any],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str,
        trigger_reason: Optional[str] = None,
        actor_id: str = "SYSTEM",
        negotiation_messages: Optional[List[Dict[str, Any]]] = None,
        active_conflicts: Optional[List[Dict[str, Any]]] = None,
        revised_proposals: Optional[Dict[str, Any]] = None,
        negotiation_status: str = "NONE"
    ) -> Dict[str, Any]:
        """
        Coordinates all 5 agent outputs, integrates negotiation exchanges, builds candidate plans,
        and creates authoritative decision and audit records.
        """
        start_time = time.perf_counter()
        conflicts = list(active_conflicts) if active_conflicts is not None else []

        # 1. Cross-Agent Conflict Detection (if not already precomputed)
        if active_conflicts is None:
            if triage_output["recommended_care_level"] == "ICU" and bed_output["feasibility"] == "UNAVAILABLE":
                conflicts.append({
                    "type": "BED_CAPACITY_CONFLICT",
                    "severity": "CRITICAL",
                    "description": "Triage demands immediate ICU admission, but zero ICU beds are available."
                })

            if staff_output["feasibility"] == "CRITICAL_SHORTAGE":
                conflicts.append({
                    "type": "STAFF_SHORTAGE_CONFLICT",
                    "severity": "HIGH",
                    "description": "Insufficient clinical staff on duty for recommended care tier."
                })

            if emergency_output["escalation_required"] and bed_output["feasibility"] == "CONSTRAINED":
                conflicts.append({
                    "type": "EMERGENCY_RESOURCE_MISMATCH",
                    "severity": "HIGH",
                    "description": "Emergency escalation active but optimal critical care bed is constrained."
                })

        # 2. Formulate Multi-Objective Candidate Plans
        candidates = []

        # Check if revised proposals were negotiated
        revised = revised_proposals or {}
        bed_counter = revised.get("bed_counter_proposal")
        staff_revised = revised.get("staff_revised_proposal")

        req_care_level = triage_output.get("recommended_care_level", "GENERAL")
        default_dept = (
            "DEP-ICU" if req_care_level == "ICU"
            else "DEP-ER" if req_care_level == "EMERGENCY"
            else "DEP-WA" if req_care_level == "GENERAL"
            else "DEP-OPD"
        )
        target_bed_p0 = bed_output.get("recommended_bed_id")
        target_dept_p0 = (
            bed_output.get("recommended_department_id")
            or (coordinator_output.get("target_department") if isinstance(coordinator_output, dict) else None)
            or default_dept
        )
        assigned_doc_p0 = staff_output.get("assigned_doctor_id")
        assigned_nurse_p0 = staff_output.get("assigned_nurse_id")

        if bed_counter and bed_counter.get("proposed_bed_id"):
            target_bed_p0 = bed_counter.get("proposed_bed_id")
            target_dept_p0 = bed_counter.get("proposed_department_id") or target_dept_p0

        if staff_revised and staff_revised.get("assigned_doctor_id"):
            assigned_doc_p0 = staff_revised.get("assigned_doctor_id")
            assigned_nurse_p0 = staff_revised.get("assigned_nurse_id") or assigned_nurse_p0

        stepdown_neg = revised.get("stepdown_negotiation")
        if stepdown_neg:
            coord_eval = stepdown_neg.get("coordinator_evaluation", {})
            bed_resp = stepdown_neg.get("bed_response", {})
            if coord_eval.get("message_type") == "ACCEPT":
                if bed_resp.get("allocated_bed_id") or bed_resp.get("counter_bed_id"):
                    target_bed_p0 = bed_resp.get("allocated_bed_id") or bed_resp.get("counter_bed_id")
                if bed_resp.get("department_id") or bed_resp.get("counter_department_id"):
                    target_dept_p0 = bed_resp.get("department_id") or bed_resp.get("counter_department_id")

        # Plan 0: Primary Optimal / Negotiated Plan
        plan0_desc = (
            f"Direct placement in bed {target_bed_p0} ({target_dept_p0}) with assigned doctor {assigned_doc_p0}."
            if target_bed_p0
            else f"Requested placement in {target_dept_p0} ({req_care_level}) - zero compatible beds currently available."
        )
        candidates.append({
            "plan_index": 0,
            "plan_type": "PRIMARY_RECOMMENDED" if not revised else "NEGOTIATED_OPTIMAL",
            "care_level": triage_output["recommended_care_level"],
            "target_bed_id": target_bed_p0,
            "target_department_id": target_dept_p0,
            "department_occupancy_rate": bed_output.get("occupancy_by_department", {}).get(target_dept_p0),
            "assigned_doctor_id": assigned_doc_p0,
            "assigned_nurse_id": assigned_nurse_p0,
            "emergency_level": emergency_output.get("emergency_level"),
            "objective_score": 0.92 if not conflicts else (0.85 if negotiation_status == "RESOLVED" else 0.70),
            "waiting_time_score": 0.95,
            "resource_util_score": 0.88,
            "staff_balance_score": 0.90 if staff_output["feasibility"] in ["FEASIBLE", "REBALANCED"] else 0.65,
            "hard_constraint_pass": len(conflicts) == 0 or negotiation_status == "RESOLVED",
            "description": plan0_desc
        })

        # Plan 1: Step-Down / Alternative Plan (Only include if a genuine alternative bed exists)
        alt_beds = [b for b in (bed_output.get("alternative_beds") or []) if b and str(b).strip().lower() not in ["none", "null"]]
        if alt_beds:
            alt_bed = alt_beds[0]
            candidates.append({
                "plan_index": 1,
                "plan_type": "ALTERNATIVE_STEP_DOWN",
                "care_level": "EMERGENCY" if triage_output["recommended_care_level"] == "ICU" else "GENERAL",
                "target_bed_id": alt_bed,
                "target_department_id": bed_output.get("recommended_department_id") or target_dept_p0,
                "department_occupancy_rate": bed_output.get("occupancy_by_department", {}).get(bed_output.get("recommended_department_id")),
                "assigned_doctor_id": assigned_doc_p0,
                "assigned_nurse_id": assigned_nurse_p0,
                "emergency_level": emergency_output.get("emergency_level"),
                "objective_score": 0.82,
                "waiting_time_score": 0.85,
                "resource_util_score": 0.80,
                "staff_balance_score": 0.85,
                "hard_constraint_pass": True,
                "description": f"Alternative placement in bed {alt_bed} with continuous telemetry monitoring."
            })

        # Plan 2: Contingency / Surge Stabilization Plan
        candidates.append({
            "plan_index": len(candidates),
            "plan_type": "CONTINGENCY_SURGE",
            "care_level": "EMERGENCY_HOLDING",
            "target_bed_id": None,
            "target_department_id": "DEP-ER",
            "assigned_doctor_id": assigned_doc_p0,
            "assigned_nurse_id": assigned_nurse_p0,
            "emergency_level": emergency_output.get("emergency_level"),
            "objective_score": 0.72,
            "waiting_time_score": 0.70,
            "resource_util_score": 0.75,
            "staff_balance_score": 0.75,
            "hard_constraint_pass": True,
            "description": "Emergency stabilization holding area placement with specialist consult request."
        })

        # Select and Score Best Plan via Dedicated Constraint Optimizer
        optimizer_res = self.constraint_optimizer.optimize(
            candidates=candidates,
            triage_output=triage_output,
            bed_output=bed_output,
            staff_output=staff_output,
            emergency_output=emergency_output,
            negotiation_status=negotiation_status,
            active_conflicts=conflicts,
        )
        candidates = optimizer_res.scored_candidates
        selected_plan = optimizer_res.selected_plan
        selected_plan_idx = optimizer_res.selected_plan_index

        # 3. Determine Action Type, Risk Level, and Human Approval Requirement via Standalone Risk Engine
        risk_result = self.risk_engine.evaluate(
            triage_output=triage_output,
            emergency_output=emergency_output,
            selected_plan=selected_plan,
            encounter=encounter,
            patient=patient,
            negotiation_status=negotiation_status,
            active_conflicts=conflicts,
            bed_output=bed_output,
            staff_output=staff_output,
        )

        action_type = risk_result.action_type
        risk_level = risk_result.risk_level
        requires_human_approval = risk_result.requires_human_approval
        confidence = risk_result.confidence
        reasoning = risk_result.reasoning
        proposed_action = dict(risk_result.proposed_action or {})

        # Any recommendation that reserves an inpatient bed is consequential and
        # must be explicitly reviewed, including routine/low-acuity placements.
        target_bed_id = selected_plan.get("target_bed_id")
        care_level = triage_output.get("recommended_care_level")
        if target_bed_id and care_level != "OUTPATIENT":
            requires_human_approval = True
            if action_type not in ("ICU_BED_ALLOCATION_RECOMMENDATION",):
                action_type = "BED_ALLOCATION_RECOMMENDATION"
            proposed_action.update({
                "action": "ALLOCATE_BED",
                "target_bed_id": target_bed_id,
                "target_department_id": selected_plan.get("target_department_id"),
                "assigned_doctor_id": selected_plan.get("assigned_doctor_id"),
                "assigned_nurse_id": selected_plan.get("assigned_nurse_id"),
                "encounter_id": encounter.id,
                "patient_id": patient.id,
            })
            if not risk_result.requires_human_approval:
                reasoning = f"{reasoning} Inpatient bed allocation requires clinician approval before assignment."

        # 4. Persist Inter-Agent Messages (Full Provenance Traceability)
        messages_to_persist: List[AgentMessage] = [
            AgentMessage(
                sender_agent="triage_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="TRIAGE_ASSESSMENT_COMPLETED",
                payload=triage_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="bed_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="BED_FEASIBILITY_EVALUATED",
                payload=bed_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="staff_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="STAFF_WORKLOAD_EVALUATED",
                payload=staff_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="emergency_escalation_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="EMERGENCY_ESCALATION_EVALUATED",
                payload=emergency_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="patient_coordinator_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="PATIENT_COORDINATION_COMPLETED",
                payload=coordinator_output,
                status="DELIVERED"
            ),
        ]

        # Add structured negotiation messages
        if negotiation_messages:
            for nm in negotiation_messages:
                messages_to_persist.append(
                    AgentMessage(
                        sender_agent=nm.get("sender_agent", "unknown_agent"),
                        receiver_agent=nm.get("receiver_agent", "coordinator_agent"),
                        encounter_id=encounter.id,
                        message_type=nm.get("message_type", "INFORM"),
                        subject=nm.get("subject", "NEGOTIATION_UPDATE"),
                        payload=nm.get("payload", {}),
                        status="DELIVERED"
                    )
                )

        # Append final coordinator response message
        msg_coord = AgentMessage(
            sender_agent="coordinator_agent",
            receiver_agent="clinical_execution_boundary",
            encounter_id=encounter.id,
            message_type="RESPONSE",
            subject="OPERATIONAL_PLAN_SELECTED",
            payload={
                "selected_plan": selected_plan,
                "action_type": action_type,
                "risk_level": risk_level,
                "requires_approval": requires_human_approval,
                "emergency_escalation": emergency_output.get("escalation_required"),
                "discharge_readiness": coordinator_output.get("discharge_readiness"),
                "negotiation_status": negotiation_status,
                "negotiation_messages_count": len(negotiation_messages or [])
            },
            status="DELIVERED"
        )
        messages_to_persist.append(msg_coord)

        self.db.add_all(messages_to_persist)
        await self.db.flush()

        # 5. Persist OptimizationRun Entity
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        opt_run = OptimizationRun(
            trigger_type="MULTI_AGENT_COORDINATION",
            encounter_id=encounter.id,
            agents_involved=[
                "triage_agent",
                "bed_agent",
                "staff_agent",
                "emergency_escalation_agent",
                "patient_coordinator_agent",
                "coordinator_agent"
            ],
            candidates_count=len(candidates),
            candidates=candidates,
            selected_plan_index=selected_plan_idx,
            selected_plan=selected_plan,
            objective_score=selected_plan["objective_score"],
            waiting_time_score=selected_plan["waiting_time_score"],
            resource_util_score=selected_plan["resource_util_score"],
            staff_balance_score=selected_plan["staff_balance_score"],
            constraint_violations=len(conflicts),
            hard_constraint_pass=selected_plan["hard_constraint_pass"],
            status="COMPLETED",
            computation_time_ms=max(1, elapsed_ms)
        )
        self.db.add(opt_run)
        await self.db.flush()

        # 6. Persist AgentDecision Entity
        proposed_action = {
            **proposed_action,
            "decision_context": {
                "triage": triage_output,
                "bed_resources": bed_output,
                "staffing": staff_output,
                "emergency": emergency_output,
                "optimization_run_id": opt_run.id,
            },
        }
        decision = AgentDecision(
            agent_id="MultiAgentCoordinator",
            encounter_id=encounter.id,
            action_type=action_type,
            proposed_action=proposed_action,
            reasoning=reasoning,
            confidence=confidence,
            alternatives=candidates,
            risk_level=risk_level,
            status="PROPOSED"
        )
        self.db.add(decision)
        await self.db.flush()

        # 7. Persist ApprovalItem if Consequential
        approval_item_id = None
        if requires_human_approval:
            approval = ApprovalItem(
                decision_id=decision.id,
                agent_id="MultiAgentCoordinator",
                action_type=action_type,
                risk_level=risk_level,
                proposed_action=proposed_action,
                reasoning=reasoning,
                alternatives=candidates,
                status="PENDING"
            )
            self.db.add(approval)
            await self.db.flush()
            approval_item_id = approval.id

        # 8. Record Immutable Audit Trail
        audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="intelligence_decision",
            entity_id=decision.id,
            field_changed="decision_generated",
            old_value="NONE",
            new_value=action_type,
            changed_by=actor_id,
            change_reason=f"Multi-Agent Workflow Evaluated: {action_type} (Risk: {risk_level})",
            decision_id=decision.id,
            approval_id=approval_item_id
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(decision)

        logger.info(
            f"5-Agent Multi-Agent Workflow Complete for Encounter {encounter.id}: Decision {decision.id} "
            f"({action_type}, Risk: {risk_level}, OptimizationRun: {opt_run.id})"
        )

        # Publish real-time event via Redis Event Bus (PostgreSQL remains authoritative)
        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "AGENT_DECISION_PROPOSED",
            "tenant_id": tenant_id,
            "source": "coordinator_agent",
            "payload": {
                "decision_id": decision.id,
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "action_type": action_type,
                "risk_level": risk_level,
                "requires_human_approval": requires_human_approval,
                "approval_item_id": approval_item_id,
                "status": decision.status
            }
        }, tenant_id=tenant_id)

        return {
            "id": decision.id,
            "encounter_id": encounter.id,
            "patient_id": patient.id,
            "agent_id": decision.agent_id,
            "action_type": decision.action_type,
            "risk_level": decision.risk_level,
            "confidence": decision.confidence,
            "proposed_action": decision.proposed_action,
            "reasoning": decision.reasoning,
            "requires_human_approval": requires_human_approval,
            "approval_item_id": approval_item_id,
            "status": decision.status,
            "optimization_run_id": opt_run.id,
            "selected_plan": selected_plan,
            "candidate_plans": candidates,
            "conflicts": conflicts,
            "negotiation_status": negotiation_status,
            "negotiation_messages_count": len(negotiation_messages or []),
            "agent_messages_count": len(messages_to_persist),
            "emergency_escalation": emergency_output,
            "patient_coordination": coordinator_output,
            "risk_evaluation": risk_result.to_dict(),
            "optimization_result": optimizer_res.to_dict(),
            "created_at": decision.created_at
        }
