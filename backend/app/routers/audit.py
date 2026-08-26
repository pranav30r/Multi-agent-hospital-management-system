import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["Audit Trail & Security"])


class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    entity_type: str
    entity_id: str
    field_changed: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: str
    change_reason: str
    decision_id: Optional[str]
    approval_id: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    entity_type: Optional[str] = Query(None, description="Filter: patient, bed, staff, equipment, emergency, approval"),
    entity_id: Optional[str] = Query(None, description="Filter by specific entity ID (e.g., BED-ICU-07)"),
    changed_by: Optional[str] = Query(None, description="Filter by actor ID (staff or agent)"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """
    Query the immutable audit trail.
    Every state change in the hospital system is logged here for compliance and traceability.
    """
    query = select(AuditLog)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if changed_by:
        query = query.where(AuditLog.changed_by == changed_by)
    query = query.order_by(desc(AuditLog.timestamp)).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/entity/{entity_type}/{entity_id}", response_model=List[AuditLogResponse])
async def get_entity_history(
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the complete change history for a specific entity (e.g., all changes to BED-ICU-07)."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(desc(AuditLog.timestamp))
    )
    return result.scalars().all()


@router.get("/stats")
async def audit_stats(db: AsyncSession = Depends(get_db)):
    """Get audit trail summary statistics."""
    result = await db.execute(select(AuditLog))
    logs = result.scalars().all()

    by_type = {}
    by_actor = {}
    for log in logs:
        by_type[log.entity_type] = by_type.get(log.entity_type, 0) + 1
        by_actor[log.changed_by] = by_actor.get(log.changed_by, 0) + 1

    return {
        "total_entries": len(logs),
        "by_entity_type": by_type,
        "by_actor": by_actor
    }
