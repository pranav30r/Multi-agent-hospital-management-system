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
    """

    def __init__(self, db: AsyncSession):
        self.db = db

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
        State transition: PENDING -> APPROVED | MODIFIED | REJECTED
        """
        # 1. Acquire pessimistic lock on ApprovalItem
        res = await self.db.execute(
            select(ApprovalItem).where(ApprovalItem.id == approval_id).with_for_update()
        )
        item = res.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Approval item not found")
        if item.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Approval item is already in '{item.status}' state")

        # 2. Mutate ApprovalItem state
        item.status = action.upper()  # APPROVED, MODIFIED, REJECTED
        item.review_action = action.upper()
        item.reviewed_by = actor_id
        item.reviewed_at = datetime.utcnow()

        if action.upper() == "MODIFY":
            item.modification = modification
        elif action.upper() == "REJECT":
            item.rejection_reason = rejection_reason

        # 3. Synchronize linked AgentDecision record
        res_dec = await self.db.execute(
            select(AgentDecision).where(AgentDecision.id == item.decision_id)
        )
        decision = res_dec.scalars().first()
        if decision:
            decision.status = action.upper()
            decision.resolved_at = datetime.utcnow()

        # 4. Record AuditLog entry within the same atomic transaction
        change_reason = f"Human Review ({actor_role}): {action.upper()}"
        if modification:
            change_reason += f" (Modified: {modification})"
        if rejection_reason:
            change_reason += f" (Reason: {rejection_reason})"

        audit = AuditLog(
            entity_type="approval",
            entity_id=approval_id,
            field_changed="status",
            old_value="PENDING",
            new_value=action.upper(),
            changed_by=actor_id,
            change_reason=change_reason,
            approval_id=approval_id,
            decision_id=item.decision_id
        )
        self.db.add(audit)

        # 5. Commit atomic unit of work
        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"APPROVAL RESOLVED: Item {approval_id} -> {action.upper()} by authenticated staff {actor_id}")
        return item
