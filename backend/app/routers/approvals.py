import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.approval_service import ApprovalService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Human-in-the-Loop Approvals"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class ApprovalActionRequest(BaseModel):
    action: str = Field(..., description="APPROVE, MODIFY, REJECT")
    modification: Optional[dict] = Field(None, description="Modified action payload")
    rejection_reason: Optional[str] = Field(None, description="Rejection reason")


class ApprovalItemResponse(BaseModel):
    id: str
    tenant_id: str = "HOSP-DEFAULT"
    decision_id: str
    agent_id: str
    action_type: str
    risk_level: str
    proposed_action: dict
    reasoning: str
    status: str
    reviewed_by: Optional[str] = None
    review_action: Optional[str] = None
    modification: Optional[dict] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/pending", response_model=List[ApprovalItemResponse])
async def list_pending_approvals(
    skip: int = 0,
    limit: int = 50,
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List pending items in the Human Review Queue requiring staff/clinician approval for the authenticated tenant."""
    service = ApprovalService(db)
    return await service.list_pending_approvals(tenant_id=current_staff.tenant_id, skip=skip, limit=limit)


@router.post("/{approval_id}/review", response_model=ApprovalItemResponse)
async def review_approval_item(
    approval_id: str,
    req: ApprovalActionRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit human decision (APPROVE / MODIFY / REJECT) for a pending AI recommendation with pessimistic locking.
    Enforces that reviewer identity and tenant are derived strictly from the authenticated JWT.
    """
    service = ApprovalService(db)
    return await service.review_approval(
        approval_id=approval_id,
        action=req.action,
        modification=req.modification,
        rejection_reason=req.rejection_reason,
        actor_id=current_staff.id,
        actor_role=current_staff.role,
        tenant_id=current_staff.tenant_id
    )
