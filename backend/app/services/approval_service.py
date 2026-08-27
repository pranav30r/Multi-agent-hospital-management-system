import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import ApprovalItem, AgentDecision, AuditLog

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

        item = ApprovalItem(
            decision_id=decision_id,
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
        logger.info(f"Created ApprovalItem {item.id} for decision {decision_id}")
        return item

    async def list_pending_approvals(self) -> List[ApprovalItem]:
        """List all pending items in the Human Review Queue requiring staff/clinician review."""
        res = await self.db.execute(
            select(ApprovalItem).where(ApprovalItem.status == "PENDING").order_by(ApprovalItem.created_at.desc())
        )
        return res.scalars().all()

    async def get_approval_by_id(self, approval_id: str) -> Optional[ApprovalItem]:
        """Fetch an approval item by its unique ID."""
        res = await self.db.execute(select(ApprovalItem).where(ApprovalItem.id == approval_id))
        return res.scalars().first()

    async def review_approval(
        self,
        approval_id: str,
        action: str,
        actor_id: str,
        actor_role: str,
        modification: Optional[Dict[str, Any]] = None,
        rejection_reason: Optional[str] = None
    ) -> ApprovalItem:
        """
        Submit human decision (APPROVE / MODIFY / REJECT) for a pending AI recommendation.
        Enforces SELECT ... FOR UPDATE row-level lock for idempotent execution.
        State transition: PENDING -> APPROVE | MODIFY | REJECT
        """
        res = await self.db.execute(
            select(ApprovalItem).where(ApprovalItem.id == approval_id).with_for_update()
        )
        item = res.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Approval item not found")
        if item.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Approval item is already in '{item.status}' state")

        action_clean = action.upper()
        if action_clean not in ["APPROVE", "APPROVED", "MODIFY", "MODIFIED", "REJECT", "REJECTED"]:
            raise HTTPException(status_code=400, detail=f"Invalid approval action: {action}")

        item.status = action_clean
        item.review_action = action_clean
        item.reviewed_by = actor_id
        item.reviewed_at = datetime.utcnow()

        if action_clean in ["MODIFY", "MODIFIED"]:
            item.modification = modification
        elif action_clean in ["REJECT", "REJECTED"]:
            item.rejection_reason = rejection_reason

        # Synchronize linked AgentDecision
        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == item.decision_id)
        )
        decision = res_dec.scalars().first()
        if decision:
            decision.status = action_clean
            decision.resolved_at = datetime.utcnow()

        # AuditLog entry within same atomic transaction
        change_reason = f"Human Review ({actor_role}): {action_clean}"
        if modification:
            change_reason += f" (Modified: {modification})"
        if rejection_reason:
            change_reason += f" (Reason: {rejection_reason})"

        audit = AuditLog(
            entity_type="approval",
            entity_id=approval_id,
            field_changed="status",
            old_value="PENDING",
            new_value=action_clean,
            changed_by=actor_id,
            change_reason=change_reason,
            approval_id=approval_id,
            decision_id=item.decision_id
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"APPROVAL RESOLVED: Item {approval_id} -> {action_clean} by authenticated staff {actor_id}")
        return item

    async def approve_action(self, approval_id: str, actor_id: str, actor_role: str) -> ApprovalItem:
        """Convenience method to approve a proposed action."""
        return await self.review_approval(
            approval_id=approval_id,
            action="APPROVE",
            actor_id=actor_id,
            actor_role=actor_role
        )

    async def modify_action(
        self,
        approval_id: str,
        modification: Dict[str, Any],
        actor_id: str,
        actor_role: str
    ) -> ApprovalItem:
        """Convenience method to modify a proposed action before approval."""
        return await self.review_approval(
            approval_id=approval_id,
            action="MODIFY",
            actor_id=actor_id,
            actor_role=actor_role,
            modification=modification
        )

    async def reject_action(
        self,
        approval_id: str,
        rejection_reason: str,
        actor_id: str,
        actor_role: str
    ) -> ApprovalItem:
        """Convenience method to reject a proposed action."""
        return await self.review_approval(
            approval_id=approval_id,
            action="REJECT",
            actor_id=actor_id,
            actor_role=actor_role,
            rejection_reason=rejection_reason
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
        item.reviewed_at = datetime.utcnow()

        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == item.decision_id)
        )
        decision = res_dec.scalars().first()
        if decision:
            decision.status = "EXPIRED"
            decision.resolved_at = datetime.utcnow()

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
