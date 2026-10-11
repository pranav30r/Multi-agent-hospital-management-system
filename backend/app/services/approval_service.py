import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import ApprovalItem, AgentDecision, AuditLog
from app.models.bed import Bed, BedAssignment
from app.models.department import Department
from app.models.patient import Patient, Encounter
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

        action_clean = action.upper()
        if action_clean not in ["APPROVE", "MODIFY", "REJECT"]:
            raise HTTPException(status_code=400, detail="Action must be APPROVE, MODIFY, or REJECT")

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

        # AuditLog entry within same atomic transaction
        change_reason = f"Human Review ({actor_role}): {action_clean}"
        if modification:
            change_reason += f" (Modified: {modification})"
        if rejection_reason:
            change_reason += f" (Reason: {rejection_reason})"

        effective_tenant = tenant_id or getattr(item, "tenant_id", "HOSP-DEFAULT")
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

        # Consequential Resource Execution for APPROVED / MODIFIED actions
        executed_bed_id = None
        if action_clean in ["APPROVE", "MODIFY"]:
            executed_bed_id = await self._execute_approved_action(
                item=item,
                decision=decision,
                action=action_clean,
                modification=modification,
                actor_id=actor_id,
                actor_role=actor_role,
                tenant_id=effective_tenant
            )

        await self.db.commit()
        await self.db.refresh(item)
        logger.info(f"APPROVAL RESOLVED: Item {approval_id} -> {action_clean} by authenticated staff {actor_id}")

        from app.services.events import event_bus
        if executed_bed_id:
            await event_bus.publish({
                "event_type": "BED_RESERVED",
                "tenant_id": effective_tenant,
                "source": "approval_execution_pipeline",
                "payload": {
                    "bed_id": executed_bed_id,
                    "patient_id": item.proposed_action.get("patient_id") if isinstance(item.proposed_action, dict) else None,
                    "encounter_id": item.proposed_action.get("encounter_id") if isinstance(item.proposed_action, dict) else None,
                    "status": "RESERVED",
                    "approved_by": actor_id
                }
            }, tenant_id=effective_tenant)

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

        return item

    async def _execute_approved_action(
        self,
        item: ApprovalItem,
        decision: Optional[AgentDecision],
        action: str,
        modification: Optional[Dict[str, Any]],
        actor_id: str,
        actor_role: str,
        tenant_id: str
    ) -> Optional[str]:
        """
        Executes consequential resource allocation for an approved AI proposal.
        Revalidates tenant boundaries, encounter ownership, bed live status, and compatibility.
        Maintains transactional atomicity: if resource execution fails, raises HTTPException
        before transaction commit so that the approval remains unexecuted.
        """
        base_payload = item.proposed_action or {}
        if not isinstance(base_payload, dict):
            return None

        effective_payload = dict(base_payload)
        if action == "MODIFY" and modification and isinstance(modification, dict):
            effective_payload.update(modification)

        target_bed_id = effective_payload.get("target_bed_id") or effective_payload.get("bed_id")
        enc_id = effective_payload.get("encounter_id") or (getattr(decision, "encounter_id", None) if decision else None)

        # If no bed or encounter specified, no physical bed allocation to perform
        if not target_bed_id or not enc_id:
            return None

        # 1. Revalidate Encounter and tenant ownership
        enc_query = (
            select(Encounter)
            .join(Patient, Encounter.patient_id == Patient.id)
            .where(Encounter.id == enc_id)
        )
        if tenant_id:
            enc_query = enc_query.where(Patient.tenant_id == tenant_id)

        res_enc = await self.db.execute(enc_query)
        encounter = res_enc.scalars().first()
        if not encounter:
            raise HTTPException(
                status_code=404,
                detail=f"Encounter {enc_id} not found or does not belong to tenant '{tenant_id}'"
            )

        pat_id = effective_payload.get("patient_id") or encounter.patient_id
        if encounter.patient_id != pat_id:
            raise HTTPException(
                status_code=400,
                detail=f"Encounter patient mismatch: expected '{encounter.patient_id}', got '{pat_id}'"
            )

        # 2. Revalidate Target Bed existence, tenant ownership, and live status with pessimistic lock
        bed_query = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(Bed.id == target_bed_id)
        )
        if tenant_id:
            bed_query = bed_query.where(Department.tenant_id == tenant_id)

        res_bed = await self.db.execute(bed_query.with_for_update())
        bed = res_bed.scalars().first()
        if not bed:
            raise HTTPException(
                status_code=404,
                detail=f"Bed {target_bed_id} not found in tenant '{tenant_id}'"
            )

        if bed.status != "AVAILABLE":
            raise HTTPException(
                status_code=400,
                detail=f"Bed {target_bed_id} is in '{bed.status}' state and is not available for reservation"
            )

        # 3. Check bed compatibility if specified (e.g. ICU requirement)
        required_bed_type = effective_payload.get("bed_type")
        if required_bed_type and str(required_bed_type).upper() == "ICU" and bed.bed_type not in ["ICU", "CARDIAC_MONITOR"]:
            if action != "MODIFY":
                raise HTTPException(
                    status_code=400,
                    detail=f"Bed {target_bed_id} type '{bed.bed_type}' is incompatible with required ICU level of care"
                )

        # 4. Apply State Mutation on Bed
        old_bed_status = bed.status
        bed.status = "RESERVED"
        bed.current_patient_id = pat_id
        bed.current_encounter_id = enc_id

        # 5. Synchronize Encounter
        encounter.current_bed_id = target_bed_id
        encounter.bed_reserved_time = utc_now()
        encounter.patient_status = "BED_RESERVED"
        if effective_payload.get("assigned_doctor_id"):
            encounter.assigned_doctor_id = effective_payload["assigned_doctor_id"]
        if effective_payload.get("assigned_nurse_id"):
            encounter.assigned_nurse_id = effective_payload["assigned_nurse_id"]

        # 6. Record BedAssignment
        assignment = BedAssignment(
            bed_id=target_bed_id,
            encounter_id=enc_id,
            patient_id=pat_id,
            assigned_by=actor_id,
            is_manual_override=(action == "MODIFY"),
            status="RESERVED"
        )
        self.db.add(assignment)

        # 7. Record Bed AuditLog entry
        bed_audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="bed",
            entity_id=target_bed_id,
            field_changed="status",
            old_value=old_bed_status,
            new_value="RESERVED",
            changed_by=actor_id,
            change_reason=f"Approved AI Recommendation ({item.action_type}) by {actor_role} ({action})"
        )
        self.db.add(bed_audit)

        logger.info(
            f"EXECUTED APPROVED RESOURCE MUTATION: Bed {target_bed_id} RESERVED for Encounter {enc_id} "
            f"via Approval {item.id} ({action}) by {actor_id}"
        )
        return target_bed_id

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
