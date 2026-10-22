"""
LangGraph Multi-Agent Hospital State Graph with Structured Inter-Agent Negotiation.

Provides a real LangGraph StateGraph implementation coordinating the 5 specialized operational agents:
1. Triage Agent (Acuity, ESI scoring, Red Flags)
2. Bed Manager Agent (Capacity, Telemetry, Isolation, Alternative Counter-Proposals)
3. Staff Scheduler Agent (Doctor/Nurse load balancing, Rebalanced Assignments)
4. Emergency Escalation Agent (Physiological decompensation, Code Blue / RRT, Negotiation Evaluation)
5. Patient Coordinator Agent (Clinical handoff briefs, discharge readiness, missing inputs)
6. Coordinator Agent (Conflict Detection, Bounded Negotiation Synthesis, Risk Gating, HITL Approval)

Reuses existing domain agent classes without duplicating clinical or operational logic.
"""

import logging
from typing import TypedDict, Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph import StateGraph, START, END

from app.models.patient import Patient, Encounter
from app.agents import (
    TriageAgent,
    BedManagerAgent,
    BedManagementAgent,
    StaffSchedulerAgent,
    StaffWorkloadAgent,
    EmergencyEscalationAgent,
    PatientCoordinatorAgent,
    CoordinatorAgent,
)

logger = logging.getLogger(__name__)

MAX_NEGOTIATION_ROUNDS = 2


# ─── 1. LangGraph State Definition ───────────────────────────────────────────

class HospitalAgentState(TypedDict, total=False):
    """
    Typed transient state flowing through the LangGraph Multi-Agent Hospital State Graph.
    Carries clinical telemetry, individual agent assessments, active conflicts,
    negotiation messages, revised proposals, candidate plans, governance risk metrics,
    and orchestration error statuses.
    """
    # Identifiers & Context
    encounter_id: str
    patient_id: str
    tenant_id: str
    actor_id: str
    trigger_reason: Optional[str]
    force_recalculate: bool

    # Specialized Agent Assessments (Initial Proposals)
    triage_output: Optional[Dict[str, Any]]
    bed_output: Optional[Dict[str, Any]]
    staff_output: Optional[Dict[str, Any]]
    emergency_output: Optional[Dict[str, Any]]
    patient_coordinator_output: Optional[Dict[str, Any]]

    # Negotiation Transient State
    active_conflicts: Optional[List[Dict[str, Any]]]
    negotiation_round: int
    negotiation_status: str  # "NONE", "NEGOTIATING", "RESOLVED", "UNRESOLVED_ESCALATED", "BYPASSED"
    negotiation_messages: Optional[List[Dict[str, Any]]]
    revised_proposals: Optional[Dict[str, Any]]

    # Coordinator Synthesis & Candidate Plans
    coordinator_output: Optional[Dict[str, Any]]
    selected_plan: Optional[Dict[str, Any]]
    candidate_plans: Optional[List[Dict[str, Any]]]
    conflicts: Optional[List[Dict[str, Any]]]

    # Authoritative Decision & Governance Gating
    decision_id: Optional[str]
    action_type: Optional[str]
    risk_level: Optional[str]
    requires_human_approval: Optional[bool]
    approval_item_id: Optional[str]
    optimization_run_id: Optional[str]

    # Workflow Telemetry & Error Handling
    status: str  # "INITIALIZED", "RUNNING", "COMPLETED", "FAILED"
    error: Optional[str]
    failed_agent: Optional[str]


# ─── 2. LangGraph Orchestrator Class ──────────────────────────────────────────

class HospitalLangGraphOrchestrator:
    """
    Constructs and executes a compiled LangGraph StateGraph around the 5 existing
    specialized operational agents, conflict detection, negotiation round management,
    and Coordinator synthesis.
    """

    def __init__(
        self,
        db: AsyncSession,
        encounter: Encounter,
        patient: Patient
    ):
        self.db = db
        self.encounter = encounter
        self.patient = patient

        # Bind existing domain agent services (no duplicate algorithms)
        self.triage_agent = TriageAgent(db)
        self.bed_agent = BedManagerAgent(db)
        self.staff_agent = StaffSchedulerAgent(db)
        self.emergency_agent = EmergencyEscalationAgent(db)
        self.patient_coordinator_agent = PatientCoordinatorAgent(db)
        self.coordinator_agent = CoordinatorAgent(db)

    # ─── Graph Node Callables ─────────────────────────────────────────────────

    async def triage_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 1: Executes TriageAgent evaluate method."""
        if state.get("status") == "FAILED":
            return {}
        try:
            actor_id = state.get("actor_id", "SYSTEM")
            output = await self.triage_agent.evaluate(self.encounter, self.patient, actor_id=actor_id)
            return {
                "triage_output": output,
                "status": "RUNNING"
            }
        except Exception as e:
            logger.exception(f"TriageAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "triage_agent"
            }

    async def bed_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 2: Executes BedManagerAgent evaluate method."""
        if state.get("status") == "FAILED" or not state.get("triage_output"):
            return {}
        try:
            tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
            output = await self.bed_agent.evaluate(state["triage_output"], self.encounter, tenant_id=tenant_id)
            return {"bed_output": output}
        except Exception as e:
            logger.exception(f"BedManagerAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "bed_agent"
            }

    async def emergency_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 3: Executes EmergencyEscalationAgent evaluate method."""
        if state.get("status") == "FAILED" or not state.get("triage_output"):
            return {}
        try:
            tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
            output = await self.emergency_agent.evaluate(state["triage_output"], self.encounter, tenant_id=tenant_id)
            return {"emergency_output": output}
        except Exception as e:
            logger.exception(f"EmergencyEscalationAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "emergency_escalation_agent"
            }

    async def staff_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 4: Executes StaffSchedulerAgent evaluate method (depends on triage and bed capacity)."""
        if state.get("status") == "FAILED" or not state.get("triage_output") or not state.get("bed_output"):
            return {}
        try:
            tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
            output = await self.staff_agent.evaluate(
                state["triage_output"],
                state["bed_output"],
                self.encounter,
                tenant_id=tenant_id
            )
            return {"staff_output": output}
        except Exception as e:
            logger.exception(f"StaffSchedulerAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "staff_agent"
            }

    async def patient_coordinator_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 5: Executes PatientCoordinatorAgent evaluate method (clinical handoff brief & discharge readiness)."""
        if state.get("status") == "FAILED":
            return {}
        try:
            tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
            output = await self.patient_coordinator_agent.evaluate(
                triage_output=state.get("triage_output", {}),
                bed_output=state.get("bed_output", {}),
                staff_output=state.get("staff_output", {}),
                encounter=self.encounter,
                patient=self.patient,
                tenant_id=tenant_id
            )
            return {"patient_coordinator_output": output}
        except Exception as e:
            logger.exception(f"PatientCoordinatorAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "patient_coordinator_agent"
            }

    async def conflict_detection_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """
        Node 6: Evaluates multi-agent proposals for operational conflicts and resource mismatches.
        """
        if state.get("status") == "FAILED":
            return {}

        triage_out = state.get("triage_output", {})
        bed_out = state.get("bed_output", {})
        staff_out = state.get("staff_output", {})
        emergency_out = state.get("emergency_output", {})

        conflicts = []

        # 1. ICU / Bed Capacity Conflict
        care_level = triage_out.get("recommended_care_level", "GENERAL")
        bed_feasibility = bed_out.get("feasibility", "FEASIBLE")
        if care_level in ["ICU", "EMERGENCY"] and bed_feasibility in ["UNAVAILABLE", "CONSTRAINED"]:
            conflicts.append({
                "type": "BED_CAPACITY_CONFLICT",
                "severity": "CRITICAL" if care_level == "ICU" else "HIGH",
                "description": f"Target care tier '{care_level}' requested, but bed feasibility is '{bed_feasibility}'."
            })

        # 2. Staff Workload / Shortage Conflict
        staff_feasibility = staff_out.get("feasibility", "FEASIBLE")
        if staff_feasibility in ["CRITICAL_SHORTAGE", "WARNING_OVERLOAD"]:
            conflicts.append({
                "type": "STAFF_SHORTAGE_CONFLICT",
                "severity": "HIGH" if staff_feasibility == "CRITICAL_SHORTAGE" else "MEDIUM",
                "description": f"Clinical staffing constraint detected: {staff_feasibility}."
            })

        # 3. Emergency Resource Mismatch
        if emergency_out.get("escalation_required") and bed_feasibility in ["CONSTRAINED", "UNAVAILABLE"]:
            conflicts.append({
                "type": "EMERGENCY_RESOURCE_MISMATCH",
                "severity": "HIGH",
                "description": "Acute emergency escalation active while primary resuscitation / critical care bed is constrained."
            })

        # 4. Discharge / Step-Down Destination Conflict
        coord_pat_out = state.get("patient_coordinator_output", {})
        stepdown_prop = coord_pat_out.get("discharge_stepdown_proposal")
        if stepdown_prop and stepdown_prop.get("transition_type") == "STEP_DOWN_TRANSFER":
            target_dept = stepdown_prop.get("proposed_destination", "DEP-WA")
            if bed_feasibility in ["CONSTRAINED", "UNAVAILABLE"] or bed_out.get("recommended_department_id") != target_dept:
                conflicts.append({
                    "type": "DISCHARGE_STEPDOWN_CONFLICT",
                    "severity": "MEDIUM",
                    "description": f"Patient Coordinator proposed step-down transfer to '{target_dept}', but ward capacity is constrained or assigned department differs."
                })

        if conflicts:
            return {
                "active_conflicts": conflicts,
                "conflicts": conflicts,
                "negotiation_status": "NEGOTIATING"
            }
        else:
            return {
                "active_conflicts": [],
                "conflicts": [],
                "negotiation_status": "BYPASSED"
            }

    async def negotiation_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """
        Node 7: Structured Inter-Agent Negotiation.
        Executes bounded proposal -> counter-proposal -> evaluation exchange across conflicting agents.
        """
        if state.get("status") == "FAILED":
            return {}

        current_round = state.get("negotiation_round", 0) + 1
        tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
        triage_out = state.get("triage_output", {})
        bed_out = state.get("bed_output", {})
        staff_out = state.get("staff_output", {})
        coord_pat_out = state.get("patient_coordinator_output", {})
        conflicts = state.get("active_conflicts", [])

        messages = list(state.get("negotiation_messages") or [])
        revised = dict(state.get("revised_proposals") or {})

        has_bed_conflict = any(c["type"] in ["BED_CAPACITY_CONFLICT", "EMERGENCY_RESOURCE_MISMATCH"] for c in conflicts)
        has_staff_conflict = any(c["type"] == "STAFF_SHORTAGE_CONFLICT" for c in conflicts)
        has_stepdown_conflict = any(c["type"] == "DISCHARGE_STEPDOWN_CONFLICT" for c in conflicts)

        # 1. Bed Management Agent Counter-Proposal
        if has_bed_conflict:
            counter_prop = await self.bed_agent.propose_counter_proposal(
                triage_output=triage_out,
                initial_bed_output=bed_out,
                encounter=self.encounter,
                tenant_id=tenant_id
            )
            messages.append({
                "sender_agent": "bed_agent",
                "receiver_agent": "emergency_escalation_agent",
                "message_type": "COUNTER_PROPOSAL",
                "subject": "BED_COUNTER_PROPOSAL",
                "payload": counter_prop
            })
            revised["bed_counter_proposal"] = counter_prop

            # 2. Emergency Escalation Agent Evaluates Counter-Proposal
            eval_res = await self.emergency_agent.evaluate_counter_proposal(
                counter_proposal=counter_prop,
                triage_output=triage_out,
                encounter=self.encounter
            )
            messages.append({
                "sender_agent": "emergency_escalation_agent",
                "receiver_agent": "coordinator_agent",
                "message_type": eval_res.get("message_type", "ESCALATION"),
                "subject": "EMERGENCY_NEGOTIATION_RESPONSE",
                "payload": eval_res
            })
            revised["emergency_response"] = eval_res

        # 3. Staff Workload Agent Rebalanced Allocation
        if has_staff_conflict:
            rebalanced_staff = await self.staff_agent.propose_rebalanced_workload(
                triage_output=triage_out,
                bed_output=bed_out,
                initial_staff_output=staff_out,
                encounter=self.encounter,
                tenant_id=tenant_id
            )
            messages.append({
                "sender_agent": "staff_agent",
                "receiver_agent": "coordinator_agent",
                "message_type": "REVISED_PROPOSAL",
                "subject": "STAFF_WORKLOAD_REBALANCED",
                "payload": rebalanced_staff
            })
            revised["staff_revised_proposal"] = rebalanced_staff

        # 4. Bidirectional Patient Care Coordinator Discharge / Step-Down Negotiation
        stepdown_prop = coord_pat_out.get("discharge_stepdown_proposal")
        if has_stepdown_conflict or (stepdown_prop and stepdown_prop.get("transition_type") == "STEP_DOWN_TRANSFER" and bed_out.get("feasibility") in ["CONSTRAINED", "UNAVAILABLE"]):
            if not stepdown_prop:
                stepdown_prop = await self.patient_coordinator_agent.propose_discharge_or_stepdown(
                    triage_out, bed_out, staff_out, self.encounter, self.patient, tenant_id
                )

            # Step 1: Patient Coordinator proposes transition to Bed Agent
            messages.append({
                "sender_agent": "patient_coordinator_agent",
                "receiver_agent": "bed_agent",
                "message_type": "PROPOSAL",
                "subject": "STEPDOWN_TRANSFER_PROPOSAL",
                "payload": stepdown_prop
            })

            # Step 2: Bed Management Agent evaluates against live inventory
            bed_stepdown_eval = await self.bed_agent.evaluate_discharge_stepdown_proposal(stepdown_prop, tenant_id=tenant_id)
            messages.append({
                "sender_agent": "bed_agent",
                "receiver_agent": "patient_coordinator_agent",
                "message_type": bed_stepdown_eval.get("decision", "COUNTER_PROPOSAL"),
                "subject": "STEPDOWN_BED_EVALUATION",
                "payload": bed_stepdown_eval
            })

            # Step 3: Patient Coordinator evaluates Bed Agent's decision / counter-proposal
            coord_stepdown_eval = await self.patient_coordinator_agent.evaluate_bed_response(
                bed_stepdown_eval, triage_out, self.encounter
            )
            messages.append({
                "sender_agent": "patient_coordinator_agent",
                "receiver_agent": "coordinator_agent",
                "message_type": coord_stepdown_eval.get("message_type", "ACCEPT"),
                "subject": "STEPDOWN_NEGOTIATION_RESPONSE",
                "payload": coord_stepdown_eval
            })

            revised["stepdown_negotiation"] = {
                "proposal": stepdown_prop,
                "bed_response": bed_stepdown_eval,
                "coordinator_evaluation": coord_stepdown_eval
            }
        else:
            # Standard Patient Coordinator Continuity Brief Update
            messages.append({
                "sender_agent": "patient_coordinator_agent",
                "receiver_agent": "coordinator_agent",
                "message_type": "REVISED_PROPOSAL",
                "subject": "COORDINATION_REVISED_FOR_NEGOTIATED_PLAN",
                "payload": {
                    "negotiated_bed_target": revised.get("bed_counter_proposal", {}).get("proposed_bed_id") or "SURGE_HOLDING",
                    "negotiated_rationale": "Updated patient journey handoff brief with negotiated contingency resources."
                }
            })

        # Determine Negotiation Resolution Status
        emergency_decision = revised.get("emergency_response", {}).get("message_type")
        stepdown_decision = revised.get("stepdown_negotiation", {}).get("coordinator_evaluation", {}).get("message_type")
        if emergency_decision == "ESCALATION" or stepdown_decision in ["ESCALATION", "REJECT"]:
            status = "UNRESOLVED_ESCALATED"
        else:
            status = "RESOLVED"

        return {
            "negotiation_round": current_round,
            "negotiation_messages": messages,
            "revised_proposals": revised,
            "negotiation_status": status
        }

    async def coordinator_node(self, state: HospitalAgentState) -> Dict[str, Any]:
        """Node 8: Executes CoordinatorAgent coordinate method (multi-objective synthesis, HITL gating, audit)."""
        if state.get("status") == "FAILED":
            return {}
        try:
            tenant_id = state.get("tenant_id", "HOSP-DEFAULT")
            trigger_reason = state.get("trigger_reason")
            actor_id = state.get("actor_id", "SYSTEM")
            negotiation_messages = state.get("negotiation_messages") or []
            active_conflicts = state.get("active_conflicts")
            revised_proposals = state.get("revised_proposals")
            negotiation_status = state.get("negotiation_status", "NONE")

            res = await self.coordinator_agent.coordinate(
                triage_output=state.get("triage_output", {}),
                bed_output=state.get("bed_output", {}),
                staff_output=state.get("staff_output", {}),
                emergency_output=state.get("emergency_output", {}),
                coordinator_output=state.get("patient_coordinator_output", {}),
                encounter=self.encounter,
                patient=self.patient,
                tenant_id=tenant_id,
                trigger_reason=trigger_reason,
                actor_id=actor_id,
                negotiation_messages=negotiation_messages,
                active_conflicts=active_conflicts,
                revised_proposals=revised_proposals,
                negotiation_status=negotiation_status
            )
            return {
                "coordinator_output": res,
                "decision_id": res["id"],
                "action_type": res["action_type"],
                "risk_level": res["risk_level"],
                "requires_human_approval": res["requires_human_approval"],
                "approval_item_id": res["approval_item_id"],
                "optimization_run_id": res["optimization_run_id"],
                "selected_plan": res["selected_plan"],
                "candidate_plans": res["candidate_plans"],
                "conflicts": res["conflicts"],
                "status": "COMPLETED"
            }
        except Exception as e:
            logger.exception(f"CoordinatorAgent node failed for encounter {self.encounter.id}: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "failed_agent": "coordinator_agent"
            }

    # ─── Graph Construction & Execution ───────────────────────────────────────

    def build_graph(self):
        """
        Constructs and compiles the LangGraph StateGraph topology with conditional negotiation routing.
        """
        workflow = StateGraph(HospitalAgentState)

        # Register all agent and negotiation nodes
        workflow.add_node("triage", self.triage_node)
        workflow.add_node("bed", self.bed_node)
        workflow.add_node("emergency", self.emergency_node)
        workflow.add_node("staff", self.staff_node)
        workflow.add_node("patient_coordinator", self.patient_coordinator_node)
        workflow.add_node("conflict_detector", self.conflict_detection_node)
        workflow.add_node("negotiator", self.negotiation_node)
        workflow.add_node("coordinator", self.coordinator_node)

        # Build initial proposal flow graph edges sequentially to guarantee AsyncSession safety
        workflow.add_edge(START, "triage")
        workflow.add_edge("triage", "bed")
        workflow.add_edge("bed", "emergency")
        workflow.add_edge("emergency", "staff")
        workflow.add_edge("staff", "patient_coordinator")
        workflow.add_edge("patient_coordinator", "conflict_detector")

        # Conditional routing from conflict_detector
        def should_negotiate(state: HospitalAgentState) -> str:
            if state.get("status") == "FAILED":
                return "coordinator"
            if state.get("active_conflicts") and state.get("negotiation_round", 0) < MAX_NEGOTIATION_ROUNDS:
                return "negotiator"
            return "coordinator"

        workflow.add_conditional_edges(
            "conflict_detector",
            should_negotiate,
            {
                "negotiator": "negotiator",
                "coordinator": "coordinator"
            }
        )

        workflow.add_edge("negotiator", "coordinator")
        workflow.add_edge("coordinator", END)

        return workflow.compile()

    async def run(
        self,
        tenant_id: str = "HOSP-DEFAULT",
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM"
    ) -> HospitalAgentState:
        """
        Asynchronously executes the compiled LangGraph StateGraph.
        """
        initial_state: HospitalAgentState = {
            "encounter_id": self.encounter.id,
            "patient_id": self.patient.id,
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "trigger_reason": trigger_reason,
            "force_recalculate": force_recalculate,
            "triage_output": None,
            "bed_output": None,
            "staff_output": None,
            "emergency_output": None,
            "patient_coordinator_output": None,
            "active_conflicts": [],
            "negotiation_round": 0,
            "negotiation_status": "NONE",
            "negotiation_messages": [],
            "revised_proposals": {},
            "coordinator_output": None,
            "selected_plan": None,
            "candidate_plans": None,
            "conflicts": None,
            "decision_id": None,
            "action_type": None,
            "risk_level": None,
            "requires_human_approval": None,
            "approval_item_id": None,
            "optimization_run_id": None,
            "status": "INITIALIZED",
            "error": None,
            "failed_agent": None,
        }

        compiled_graph = self.build_graph()
        final_state = await compiled_graph.ainvoke(initial_state)
        return final_state


def create_hospital_state_graph():
    """
    Utility factory function returning a compiled LangGraph StateGraph schema structure
    for inspection, topological analysis, and visualization.
    """
    workflow = StateGraph(HospitalAgentState)

    async def _dummy_node(state: HospitalAgentState) -> Dict[str, Any]:
        return {}

    workflow.add_node("triage", _dummy_node)
    workflow.add_node("bed", _dummy_node)
    workflow.add_node("emergency", _dummy_node)
    workflow.add_node("staff", _dummy_node)
    workflow.add_node("patient_coordinator", _dummy_node)
    workflow.add_node("conflict_detector", _dummy_node)
    workflow.add_node("negotiator", _dummy_node)
    workflow.add_node("coordinator", _dummy_node)

    workflow.add_edge(START, "triage")
    workflow.add_edge("triage", "bed")
    workflow.add_edge("bed", "emergency")
    workflow.add_edge("emergency", "staff")
    workflow.add_edge("staff", "patient_coordinator")
    workflow.add_edge("patient_coordinator", "conflict_detector")

    def _dummy_condition(state: HospitalAgentState) -> str:
        return "coordinator"

    workflow.add_conditional_edges(
        "conflict_detector",
        _dummy_condition,
        {
            "negotiator": "negotiator",
            "coordinator": "coordinator"
        }
    )

    workflow.add_edge("negotiator", "coordinator")
    workflow.add_edge("coordinator", END)

    return workflow.compile()
