import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.intake import ClinicalAssessment
from app.models.priority import ClinicalPriorityRecommendation
from app.models.agent import AgentDecision, ApprovalItem, AuditLog
from app.services.clinical_intelligence_service import ClinicalIntelligenceService
from app.services.clinical_priority_service import ClinicalPriorityService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class IntelligenceEngineService:
    """
    Application Service acting as the clean Intelligence Execution Boundary for Person 1.
    Synthesizes clinical telemetry, assessments, and red flags into structured, explainable decisions.
    Enforces Human-in-the-Loop approval for consequential actions and strictly prohibits direct
    automated mutation of critical hospital resources.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.intelligence_service = ClinicalIntelligenceService(db)
        self.priority_service = ClinicalPriorityService(db)

    async def execute_intelligence(
        self,
        encounter_id: str,
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Execute deterministic intelligence evaluation for an encounter.
        Generates an AgentDecision and routes consequential actions to an ApprovalItem (PENDING).
        """
        # 1. Validate Encounter existence with lock
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        # Validate Patient
        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {encounter.patient_id} not found")

        # 2. Idempotency Check: Return active unexpired decision if not forcing recalculation
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
                logger.info(f"Returning existing active decision {existing_decision.id} for encounter {encounter_id}")
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
                    "created_at": existing_decision.created_at
                }

        # 3. Load Authoritative Clinical Assessment and Priority Recommendation
        assessment = await self.intelligence_service.get_assessment(encounter_id)
        priority_rec = await self.priority_service.evaluate_priority(encounter_id, actor_id=actor_id)

        severity = assessment.severity or "LOW"
        red_flags = assessment.red_flags or []
        priority_level = priority_rec.priority_level or "ROUTINE"

        # 4. Synthesize Decision Policy, Risk Level, and Review Requirement
        if priority_level == "CRITICAL" or severity in ["HIGH", "CRITICAL"] or len(red_flags) >= 2:
            action_type = "ICU_BED_ALLOCATION_RECOMMENDATION"
            risk_level = "HIGH"
            requires_human_approval = True
            proposed_action = {
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "encounter_id": encounter_id,
                "patient_id": patient.id,
                "priority": "CRITICAL"
            }
            reasoning = (
                f"Critical physiological decompensation detected (Severity: {severity}, "
                f"Priority: {priority_level}, Red Flags: {len(red_flags)}). "
                f"Immediate ICU bed allocation and continuous telemetry monitoring recommended."
            )
            confidence = 0.94

        elif priority_level == "HIGH" or len(red_flags) == 1:
            action_type = "SPECIALIST_CONSULT_RECOMMENDATION"
            risk_level = "MEDIUM"
            requires_human_approval = True
            proposed_action = {
                "action": "ORDER_CONSULT",
                "specialty": "EMERGENCY_MEDICINE",
                "encounter_id": encounter_id,
                "patient_id": patient.id,
                "priority": "HIGH"
            }
            reasoning = (
                f"Elevated clinical acuity identified (Severity: {severity}, Priority: {priority_level}). "
                f"Immediate attending emergency physician consultation recommended."
            )
            confidence = 0.88

        elif priority_level == "MODERATE":
            action_type = "OBSERVATION_ADMISSION_RECOMMENDATION"
            risk_level = "LOW"
            requires_human_approval = True
            proposed_action = {
                "action": "OBSERVE",
                "department_code": "WARD",
                "encounter_id": encounter_id,
                "patient_id": patient.id,
                "priority": "MODERATE"
            }
            reasoning = "Moderate clinical presentation with stable vital signs. Step-down observation ward admission recommended."
            confidence = 0.82

        else:
            action_type = "STANDARD_OPD_ROUTING"
            risk_level = "LOW"
            requires_human_approval = False
            proposed_action = {
                "action": "QUEUE_OPD",
                "encounter_id": encounter_id,
                "patient_id": patient.id,
                "priority": "ROUTINE"
            }
            reasoning = "Normal vital parameters without acute clinical red flags. Routed to standard outpatient consultation queue."
            confidence = 0.90

        # 5. Persist AgentDecision Entity
        decision = AgentDecision(
            agent_id="ClinicalIntelligenceOrchestrator",
            encounter_id=encounter_id,
            action_type=action_type,
            proposed_action=proposed_action,
            reasoning=reasoning,
            confidence=confidence,
            risk_level=risk_level,
            status="PROPOSED"
        )
        self.db.add(decision)
        await self.db.flush()

        # 6. Integrate with Human Review Queue for Consequential Actions
        approval_item_id = None
        if requires_human_approval:
            approval = ApprovalItem(
                decision_id=decision.id,
                agent_id="ClinicalIntelligenceOrchestrator",
                action_type=action_type,
                risk_level=risk_level,
                proposed_action=proposed_action,
                reasoning=reasoning,
                status="PENDING"
            )
            self.db.add(approval)
            await self.db.flush()
            approval_item_id = approval.id

        # 7. Record Immutable Audit Trail
        audit = AuditLog(
            entity_type="intelligence_decision",
            entity_id=decision.id,
            field_changed="decision_generated",
            old_value="NONE",
            new_value=action_type,
            changed_by=actor_id,
            change_reason=f"Clinical intelligence evaluated: {action_type} (Risk: {risk_level})",
            decision_id=decision.id,
            approval_id=approval_item_id
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(decision)

        logger.info(
            f"Intelligence Decision {decision.id} ({action_type}) generated for encounter {encounter_id} "
            f"[Review Required: {requires_human_approval}, ApprovalItem: {approval_item_id}]"
        )

        return {
            "id": decision.id,
            "encounter_id": encounter_id,
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
            "created_at": decision.created_at
        }
