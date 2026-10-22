import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.bed import Bed, BedAssignment
from app.models.patient import Encounter, Patient
from app.models.department import Department
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class ApprovalService:
    """
    Application Service for Human-in-the-Loop Review Queue and AI Approvals.
    Encapsulates decision resolution, state transitions, pessimistic locking, and audit coordination.
    Lifecycle: PROPOSED -> PENDING APPROVAL -> APPROVED / MODIFIED / REJECTED / EXPIRED
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_approval_request(
        self,
        decision_id: str,
        agent_id: str,
        action_type: str,
        proposed_action: Dict[str, Any],
        reasoning: str,
        risk_level: str = "MEDIUM",
        alternatives: Optional[List[Dict[str, Any]]] = None
    ) -> ApprovalItem:
        """
        Create an approval request item from an agent decision.
        Transitions AgentDecision status to PENDING.
        """
        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == decision_id)
        )
        decision = res_dec.scalars().first()
        if not decision:
            raise HTTPException(status_code=404, detail=f"AgentDecision {decision_id} not found")

        effective_tenant = getattr(decision, "tenant_id", "HOSP-DEFAULT") or "HOSP-DEFAULT"
        item = ApprovalItem(
            decision_id=decision_id,
            tenant_id=effective_tenant,
            agent_id=agent_id,
            action_type=action_type,
            risk_level=risk_level,
            proposed_action=proposed_action,
            reasoning=reasoning,
            alternatives=alternatives or [],
            status="PENDING"
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"Created ApprovalItem {item.id} for decision {decision_id} (tenant: {effective_tenant})")

        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "APPROVAL_REQUIRED",
            "tenant_id": effective_tenant,
            "source": "approval_service",
            "payload": {
                "approval_id": item.id,
                "decision_id": decision_id,
                "agent_id": agent_id,
                "action_type": action_type,
                "risk_level": risk_level,
                "proposed_action": proposed_action
            }
        }, tenant_id=effective_tenant)

        return item

    async def list_pending_approvals(
        self,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[ApprovalItem]:
        """List pending items in the Human Review Queue requiring review for a tenant."""
        stmt = select(ApprovalItem).where(ApprovalItem.status == "PENDING")
        if tenant_id:
            stmt = stmt.where(ApprovalItem.tenant_id == tenant_id)
        stmt = stmt.order_by(ApprovalItem.created_at.desc()).offset(skip).limit(limit)
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def get_approval_by_id(self, approval_id: str, tenant_id: Optional[str] = None) -> Optional[ApprovalItem]:
        """Fetch an approval item by its unique ID with optional tenant scope."""
        stmt = select(ApprovalItem).where(ApprovalItem.id == approval_id)
        if tenant_id:
            stmt = stmt.where(ApprovalItem.tenant_id == tenant_id)
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def review_approval(
        self,
        approval_id: str,
        action: str,
        actor_id: str,
        actor_role: str,
        modification: Optional[Dict[str, Any]] = None,
        rejection_reason: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> ApprovalItem:
        """
        Submit human decision (APPROVE / MODIFY / REJECT) for a pending AI recommendation.
        Enforces SELECT ... FOR UPDATE row-level lock for idempotent execution within tenant scope.
        State transition: PENDING -> APPROVE | MODIFY | REJECT
        """
        query = select(ApprovalItem).where(ApprovalItem.id == approval_id)
        if tenant_id:
            query = query.where(ApprovalItem.tenant_id == tenant_id)
        res = await self.db.execute(query.with_for_update())
        item = res.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Approval item not found")
        if item.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Approval item is already in '{item.status}' state")
        effective_tenant = tenant_id or getattr(item, "tenant_id", "HOSP-DEFAULT")

        action_clean = action.upper()
        if action_clean not in ["APPROVE", "MODIFY", "REJECT"]:
            raise HTTPException(status_code=400, detail="Action must be APPROVE, MODIFY, or REJECT")
        reserved_bed = None

        # Mutate approval record
        item.status = action_clean
        item.reviewed_by = actor_id
        item.review_action = action_clean
        item.reviewed_at = utc_now()
        item.modification = modification
        item.rejection_reason = rejection_reason

        # Synchronize linked AgentDecision
        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == item.decision_id)
        )
        decision = res_dec.scalars().first()
        if decision:
            decision.status = action_clean
            decision.resolved_at = utc_now()

        if action_clean in ["APPROVE", "MODIFY"]:
            proposed = dict(item.proposed_action or {})
            if action_clean == "MODIFY":
                if not modification:
                    raise HTTPException(status_code=400, detail="Modification payload is required")
                proposed.update(modification)
            if proposed.get("action") in {"ALLOCATE_BED", "OBSERVE"}:
                bed_id = proposed.get("target_bed_id")
                encounter_id = proposed.get("encounter_id")
                patient_id = proposed.get("patient_id")
                if not bed_id or not encounter_id or not patient_id:
                    raise HTTPException(status_code=400, detail="Recommendation is missing bed, encounter, or patient")
                bed_query = select(Bed).join(Department, Bed.department_id == Department.id).where(
                    Bed.id == bed_id, Department.tenant_id == effective_tenant
                ).with_for_update()
                bed_result = await self.db.execute(bed_query)
                bed = bed_result.scalars().first()
                encounter_result = await self.db.execute(
                    select(Encounter).join(Patient, Encounter.patient_id == Patient.id)
                    .where(Encounter.id == encounter_id,
                           Encounter.patient_id == patient_id,
                           Patient.tenant_id == effective_tenant)
                    .with_for_update()
                )
                encounter = encounter_result.scalars().first()
                if not encounter or not bed:
                    raise HTTPException(status_code=404, detail="Recommended bed or encounter not found for this hospital")
                if bed.status != "AVAILABLE" or encounter.current_bed_id:
                    raise HTTPException(status_code=409, detail="Recommended bed or encounter is no longer available")
                if action_clean == "MODIFY":
                    item.proposed_action = proposed
                bed.status = "RESERVED"
                reserved_bed = bed
                bed.current_patient_id = patient_id
                bed.current_encounter_id = encounter_id
                encounter.current_bed_id = bed_id
                encounter.bed_reserved_time = utc_now()
                encounter.patient_status = "BED_RESERVED"
                self.db.add(BedAssignment(bed_id=bed_id, encounter_id=encounter_id,
                    patient_id=patient_id, assigned_by=actor_id, is_manual_override=False, status="RESERVED"))
                self.db.add(AuditLog(tenant_id=effective_tenant, entity_type="bed", entity_id=bed_id,
                    field_changed="status", old_value="AVAILABLE", new_value="RESERVED", changed_by=actor_id,
                    change_reason=f"Approved agent recommendation {approval_id}", approval_id=approval_id))

        # AuditLog entry within same atomic transaction
        change_reason = f"Human Review ({actor_role}): {action_clean}"
        if modification:
            change_reason += f" (Modified: {modification})"
        if rejection_reason:
            change_reason += f" (Reason: {rejection_reason})"

        audit = AuditLog(
            tenant_id=effective_tenant,
            entity_type="approval",
            entity_id=approval_id,
            field_changed="status",
            old_value="PENDING",
            new_value=action_clean,
            changed_by=actor_id,
            change_reason=change_reason
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"APPROVAL RESOLVED: Item {approval_id} -> {action_clean} by authenticated staff {actor_id}")

        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "APPROVAL_DECIDED",
            "tenant_id": effective_tenant,
            "source": "approval_service",
            "payload": {
                "approval_id": approval_id,
                "decision_id": item.decision_id,
                "action": action_clean,
                "reviewed_by": actor_id,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None
            }
        }, tenant_id=effective_tenant)
        if reserved_bed:
            await event_bus.publish({"event_type": "BED_RESERVED", "tenant_id": effective_tenant,
                "source": "approval_service", "payload": {"bed_id": reserved_bed.id, "patient_id": reserved_bed.current_patient_id,
                "encounter_id": reserved_bed.current_encounter_id, "status": reserved_bed.status, "approval_id": approval_id}},
                tenant_id=effective_tenant)

        return item

    async def approve_action(self, approval_id: str, actor_id: str, actor_role: str, tenant_id: Optional[str] = None) -> ApprovalItem:
        """Convenience method to approve a proposed action."""
        return await self.review_approval(
            approval_id=approval_id,
            action="APPROVE",
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id
        )

    async def modify_action(
        self,
        approval_id: str,
        modification: Dict[str, Any],
        actor_id: str,
        actor_role: str,
        tenant_id: Optional[str] = None
    ) -> ApprovalItem:
        """Convenience method to modify a proposed action before approval."""
        return await self.review_approval(
            approval_id=approval_id,
            action="MODIFY",
            actor_id=actor_id,
            actor_role=actor_role,
            modification=modification,
            tenant_id=tenant_id
        )

    async def reject_action(
        self,
        approval_id: str,
        rejection_reason: str,
        actor_id: str,
        actor_role: str,
        tenant_id: Optional[str] = None
    ) -> ApprovalItem:
        """Convenience method to reject a proposed action."""
        return await self.review_approval(
            approval_id=approval_id,
            action="REJECT",
            actor_id=actor_id,
            actor_role=actor_role,
            rejection_reason=rejection_reason,
            tenant_id=tenant_id
        )

    async def expire_approval(self, approval_id: str, actor_id: Optional[str] = "SYSTEM") -> ApprovalItem:
        """
        Mark a stale approval request as EXPIRED with row-level lock.
        State transition: PENDING -> EXPIRED
        """
        res = await self.db.execute(
            select(ApprovalItem).where(ApprovalItem.id == approval_id).with_for_update()
        )
        item = res.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Approval item not found")
        if item.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Approval item is already in '{item.status}' state")

        item.status = "EXPIRED"
        item.review_action = "EXPIRED"
        item.reviewed_at = utc_now()

        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == item.decision_id)
        )
        decision = res_dec.scalars().first()
        if decision:
            decision.status = "EXPIRED"
            decision.resolved_at = utc_now()

        audit = AuditLog(
            entity_type="approval",
            entity_id=approval_id,
            field_changed="status",
            old_value="PENDING",
            new_value="EXPIRED",
            changed_by=actor_id or "SYSTEM",
            change_reason="Approval request expired due to inactivity timeout",
            approval_id=approval_id,
            decision_id=item.decision_id
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"APPROVAL EXPIRED: Item {approval_id}")
        return item
