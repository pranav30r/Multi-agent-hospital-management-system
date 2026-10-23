"""
Application Service driving the 5-Agent Multi-Agent Hospital Optimization Pipeline.
Acts as a backward-compatible facade re-exporting all specialized operational agents
from the modular app.agents package while orchestrating encounters via LangGraph.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.agent import AgentDecision, ApprovalItem, OptimizationRun
from app.agents.base import BaseAgent
from app.agents.triage_agent import TriageAgent
from app.agents.bed_agent import BedManagerAgent, BedManagementAgent
from app.agents.staff_agent import StaffSchedulerAgent, StaffWorkloadAgent
from app.agents.emergency_agent import EmergencyEscalationAgent
from app.agents.patient_coordinator_agent import PatientCoordinatorAgent
from app.agents.coordinator_agent import CoordinatorAgent
from app.agents.workflow_agent import ClinicalWorkflowAgent

logger = logging.getLogger(__name__)


# ─── MultiAgentOrchestratorService ───────────────────────────────────────────

class MultiAgentOrchestratorService:
    """
    Application Service driving the 5-Agent Multi-Agent Hospital Optimization Pipeline.
    Manages the lifecycle across Triage Agent, Bed Manager Agent, Staff Scheduler Agent,
    Emergency Escalation Agent, Patient Coordinator Agent, and Coordinator Agent
    with strict transactional isolation and idempotency.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.triage_agent = TriageAgent(db)
        self.bed_agent = BedManagerAgent(db)
        self.staff_agent = StaffSchedulerAgent(db)
        self.emergency_agent = EmergencyEscalationAgent(db)
        self.patient_coordinator_agent = PatientCoordinatorAgent(db)
        self.coordinator = CoordinatorAgent(db)
        self.workflow_agent = ClinicalWorkflowAgent(db)


    async def orchestrate_encounter(
        self,
        encounter_id: str,
        tenant_id: str = "HOSP-DEFAULT",
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Executes the full end-to-end 5-agent decision support workflow for an encounter.
        Preserves complete transactional safety and row-level pessimistic locking.
        """
        # 1. Fetch Encounter with row lock
        enc_res = await self.db.execute(
            select(Encounter)
            .join(Patient)
            .where(Encounter.id == encounter_id, Patient.tenant_id == tenant_id)
            .with_for_update()
        )
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Encounter {encounter_id} not found")

        # 2. Fetch Patient
        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient {encounter.patient_id} not found")

        # 3. Idempotency check
        if not force_recalculate:
            existing_dec_res = await self.db.execute(
                select(AgentDecision)
                .where(
                    AgentDecision.encounter_id == encounter_id,
                    AgentDecision.status.in_(["PROPOSED", "PENDING", "APPROVED"])
                )
                .order_by(AgentDecision.created_at.desc())
            )
            existing_decision = existing_dec_res.scalars().first()
            if existing_decision:
                appr_res = await self.db.execute(
                    select(ApprovalItem).where(ApprovalItem.decision_id == existing_decision.id)
                )
                appr_item = appr_res.scalars().first()
                opt_res = await self.db.execute(
                    select(OptimizationRun).where(OptimizationRun.encounter_id == encounter_id).order_by(OptimizationRun.started_at.desc())
                )
                opt_run = opt_res.scalars().first()

                logger.info(f"Returning existing active multi-agent decision {existing_decision.id} for encounter {encounter_id}")
                return {
                    "id": existing_decision.id,
                    "encounter_id": encounter_id,
                    "patient_id": patient.id,
                    "agent_id": existing_decision.agent_id,
                    "action_type": existing_decision.action_type,
                    "risk_level": existing_decision.risk_level,
                    "confidence": existing_decision.confidence,
                    "proposed_action": existing_decision.proposed_action,
                    "reasoning": existing_decision.reasoning,
                    "requires_human_approval": bool(appr_item),
                    "approval_item_id": appr_item.id if appr_item else None,
                    "status": existing_decision.status,
                    "optimization_run_id": opt_run.id if opt_run else None,
                    "selected_plan": opt_run.selected_plan if opt_run else None,
                    "candidate_plans": opt_run.candidates if opt_run else [],
                    "conflicts": [],
                    "agent_messages_count": 6,
                    "created_at": existing_decision.created_at
                }

        # 4. Execute LangGraph Multi-Agent StateGraph
        from app.services.agent_graph import HospitalLangGraphOrchestrator
        graph_orchestrator = HospitalLangGraphOrchestrator(self.db, encounter=encounter, patient=patient)
        graph_state = await graph_orchestrator.run(
            tenant_id=tenant_id,
            trigger_reason=trigger_reason,
            force_recalculate=force_recalculate,
            actor_id=actor_id
        )

        if graph_state.get("status") == "FAILED":
            failed_agent = graph_state.get("failed_agent", "unknown_agent")
            err_msg = graph_state.get("error", "Unknown orchestration error")
            logger.error(f"LangGraph execution failed at {failed_agent}: {err_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Multi-agent graph orchestration failed at {failed_agent}: {err_msg}"
            )

        return graph_state.get("coordinator_output", {})

    async def coordinate_hospital_workflow(
        self,
        encounter_id: str,
        tenant_id: str = "HOSP-DEFAULT",
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM",
        correlation_id: Optional[str] = None
    ):
        """
        Executes the unified 10-step Hospital Workflow Coordinator with typed state.
        """
        from app.services.hospital_workflow_coordinator import HospitalWorkflowCoordinator
        coordinator = HospitalWorkflowCoordinator(self.db)
        return await coordinator.coordinate_workflow(
            encounter_id=encounter_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            force_recalculate=force_recalculate,
            trigger_reason=trigger_reason
        )

    async def recommend_clinical_workflow(
        self,
        encounter_id: str,
        tenant_id: str = "HOSP-DEFAULT",
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Executes deterministic clinical workflow recommendation analysis for an encounter.
        Pure recommendation: non-destructive and transactional safe.
        """
        enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Encounter {encounter_id} not found")

        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient {encounter.patient_id} not found")

        triage_output = await self.triage_agent.evaluate(encounter=encounter, patient=patient, actor_id=actor_id)
        return await self.workflow_agent.evaluate(
            triage_output=triage_output,
            encounter=encounter,
            patient=patient,
            tenant_id=tenant_id,
            actor_id=actor_id
        )


__all__ = [
    "BaseAgent",
    "TriageAgent",
    "BedManagerAgent",
    "BedManagementAgent",
    "StaffSchedulerAgent",
    "StaffWorkloadAgent",
    "EmergencyEscalationAgent",
    "PatientCoordinatorAgent",
    "CoordinatorAgent",
    "ClinicalWorkflowAgent",
    "MultiAgentOrchestratorService",
]
