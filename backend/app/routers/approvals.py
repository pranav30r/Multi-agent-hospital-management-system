import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ApprovalItem, AgentDecision, AuditLog, Staff
from app.auth.dependencies import require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Human-in-the-Loop Approvals"])

class ApprovalActionRequest(BaseModel):
    action: str = Field(..., example="APPROVE")  # APPROVE, MODIFY, REJECT
    modification: Optional[dict] = Field(None, example={"recommended_bed_id": "BED-ICU-04"})
    rejection_reason: Optional[str] = Field(None, example="Patient requires cardiac monitor bed ICU-04 instead of ICU-07")

class ApprovalItemResponse(BaseModel):
    id: str
    decision_id: str
    agent_id: str
    action_type: str
    risk_level: str
    proposed_action: dict
    reasoning: str
    status: str
    reviewed_by: Optional[str]
    review_action: Optional[str]
    modification: Optional[dict]
    rejection_reason: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]

    class Config:
        from_attributes = True

@router.get("/pending", response_model=List[ApprovalItemResponse])
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """List all pending items in the Human Review Queue requiring staff/clinician approval."""
    res = await db.execute(select(ApprovalItem).where(ApprovalItem.status == "PENDING").order_by(ApprovalItem.created_at.desc()))
    return res.scalars().all()

@router.post("/{approval_id}/review", response_model=ApprovalItemResponse)
async def review_approval_item(
    approval_id: str,
    req: ApprovalActionRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit human decision (APPROVE / MODIFY / REJECT) for a pending AI recommendation with pessimistic locking.
    Enforces that reviewer identity is derived strictly from the authenticated JWT.
    """
    res = await db.execute(
        select(ApprovalItem).where(ApprovalItem.id == approval_id).with_for_update()
    )
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Approval item not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Approval item is already in '{item.status}' state")

    item.status = req.action  # APPROVED, MODIFIED, REJECTED
    item.review_action = req.action
    item.reviewed_by = current_staff.id
    item.reviewed_at = datetime.utcnow()

    if req.action == "MODIFY":
        item.modification = req.modification
    elif req.action == "REJECT":
        item.rejection_reason = req.rejection_reason

    # Update associated AgentDecision
    res_dec = await db.execute(select(AgentDecision).where(AgentDecision.id == item.decision_id))
    decision = res_dec.scalars().first()
    if decision:
        decision.status = req.action
        decision.resolved_at = datetime.utcnow()

    # Log in Audit Trail using authenticated reviewer identity
    audit = AuditLog(
        entity_type="approval",
        entity_id=approval_id,
        field_changed="status",
        old_value="PENDING",
        new_value=req.action,
        changed_by=current_staff.id,
        change_reason=f"Human Review ({current_staff.role}): {req.action}" + (f" (Modified: {req.modification})" if req.modification else f" (Reason: {req.rejection_reason})" if req.rejection_reason else ""),
        approval_id=approval_id,
        decision_id=item.decision_id
    )
    db.add(audit)

    await db.commit()
    await db.refresh(item)
    logger.info(f"APPROVAL RESOLVED: Item {approval_id} -> {req.action} by authenticated staff {current_staff.id}")
    return item
