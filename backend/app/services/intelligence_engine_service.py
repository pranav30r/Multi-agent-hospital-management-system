import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.intake import ClinicalAssessment
from app.models.priority import ClinicalPriorityRecommendation
from app.models.agent import AgentDecision, ApprovalItem, AuditLog, OptimizationRun, AgentMessage
from app.services.clinical_intelligence_service import ClinicalIntelligenceService
from app.services.clinical_priority_service import ClinicalPriorityService
from app.services.agent_orchestrator import MultiAgentOrchestratorService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class IntelligenceEngineService:
    """
    Application Service acting as the clean Intelligence Execution Boundary for Person 1.
    Synthesizes clinical telemetry, assessments, and red flags into structured, explainable decisions
    using a collaborative multi-agent workflow (Triage, Bed, Staff, Coordinator).
    Enforces Human-in-the-Loop approval for consequential actions and strictly prohibits direct
    automated mutation of critical hospital resources.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.intelligence_service = ClinicalIntelligenceService(db)
        self.priority_service = ClinicalPriorityService(db)
        self.orchestrator = MultiAgentOrchestratorService(db)

    async def execute_intelligence(
        self,
        encounter_id: str,
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM",
        tenant_id: str = "HOSP-DEFAULT"
    ) -> Dict[str, Any]:
        """
        Execute cooperative multi-agent intelligence evaluation for an encounter.
        Orchestrates Triage, Bed, and Staff agents under Coordinator synthesis.
        Generates AgentDecision, OptimizationRun, and routes consequential actions to an ApprovalItem (PENDING).
        """
        return await self.orchestrator.orchestrate_encounter(
            encounter_id=encounter_id,
            tenant_id=tenant_id,
            trigger_reason=trigger_reason,
            force_recalculate=force_recalculate,
            actor_id=actor_id
        )

    async def get_messages_for_encounter(
        self,
        encounter_id: str
    ) -> List[AgentMessage]:
        """Fetch all inter-agent messages exchanged during orchestration for an encounter."""
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.encounter_id == encounter_id)
            .order_by(AgentMessage.timestamp.asc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def get_optimization_run(
        self,
        encounter_id: str
    ) -> Optional[OptimizationRun]:
        """Fetch the most recent optimization run generated for an encounter."""
        stmt = (
            select(OptimizationRun)
            .where(OptimizationRun.encounter_id == encounter_id)
            .order_by(OptimizationRun.started_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()
