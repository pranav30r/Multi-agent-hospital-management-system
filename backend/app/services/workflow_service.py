import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    WorkflowDefinition, WorkflowInstance, WorkflowStep,
    Queue, Task
)
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class WorkflowService:
    """
    Application Service for Clinical Workflows, Task Orchestration, and Department Queues.
    Encapsulates workflow template management, instance lifecycle, step sequencing, and concurrency locking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 1. Workflow Definition Operations ──────────────────────────────────

    async def list_definitions(self) -> List[WorkflowDefinition]:
        """List all registered clinical workflow definitions."""
        result = await self.db.execute(select(WorkflowDefinition))
        return result.scalars().all()

    async def get_definition(self, definition_id: str) -> Optional[WorkflowDefinition]:
        """Fetch workflow definition by ID."""
        result = await self.db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
        )
        return result.scalars().first()

    async def create_definition(
        self,
        definition_id: str,
        name: str,
        category: str,
        steps_json: List[Dict[str, Any]],
        is_active: bool = True
    ) -> WorkflowDefinition:
        """Create a new clinical workflow definition template."""
        existing = await self.get_definition(definition_id)
        if existing:
            raise HTTPException(status_code=400, detail=f"Workflow definition {definition_id} already exists")

        wf_def = WorkflowDefinition(
            id=definition_id,
            name=name,
            category=category,
            steps_json=steps_json,
            is_active=is_active
        )
        self.db.add(wf_def)
        await self.db.commit()
        await self.db.refresh(wf_def)
        logger.info(f"Created WorkflowDefinition {definition_id}: {name}")
        return wf_def

    async def update_definition(
        self,
        definition_id: str,
        name: Optional[str] = None,
        steps_json: Optional[List[Dict[str, Any]]] = None,
        is_active: Optional[bool] = None
    ) -> WorkflowDefinition:
        """Update an existing workflow definition template."""
        wf_def = await self.get_definition(definition_id)
        if not wf_def:
            raise HTTPException(status_code=404, detail=f"Workflow definition {definition_id} not found")

        if name is not None:
            wf_def.name = name
        if steps_json is not None:
            wf_def.steps_json = steps_json
        if is_active is not None:
            wf_def.is_active = is_active

        await self.db.commit()
        await self.db.refresh(wf_def)
        return wf_def

    async def set_definition_active(self, definition_id: str, is_active: bool) -> WorkflowDefinition:
        """Activate or deactivate a workflow definition."""
        return await self.update_definition(definition_id=definition_id, is_active=is_active)

    # ─── 2. Workflow Instance Operations ────────────────────────────────────

    async def start_workflow(
        self,
        workflow_definition_id: str,
        encounter_id: str,
        patient_id: str,
        actor_id: str
    ) -> Dict[str, Any]:
        """
        Start an active clinical workflow instance for a patient encounter.
        State: -> ACTIVE (Step 1 IN_PROGRESS)
        """
        wf_def = await self.get_definition(workflow_definition_id)
        if not wf_def:
            raise HTTPException(status_code=404, detail=f"Workflow definition {workflow_definition_id} not found")
        if not wf_def.is_active:
            raise HTTPException(status_code=400, detail=f"Workflow definition {workflow_definition_id} is inactive")

        first_step_name = wf_def.steps_json[0].get("name", "Step 1") if wf_def.steps_json else "Initial"

        instance_id = f"WFI-{uuid.uuid4().hex[:6].upper()}"
        instance = WorkflowInstance(
            id=instance_id,
            definition_id=workflow_definition_id,
            encounter_id=encounter_id,
            patient_id=patient_id,
            current_step_number=1,
            status="ACTIVE",
            started_at=datetime.utcnow()
        )
        self.db.add(instance)

        # Record initial step record
        step_record = WorkflowStep(
            workflow_instance_id=instance_id,
            step_number=1,
            name=first_step_name,
            status="IN_PROGRESS",
            started_at=datetime.utcnow()
        )
        self.db.add(step_record)

        audit = AuditLog(
            entity_type="workflow",
            entity_id=instance_id,
            field_changed="status",
            old_value=None,
            new_value="ACTIVE",
            changed_by=actor_id,
            change_reason=f"Started workflow {wf_def.name} for encounter {encounter_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(instance)
        logger.info(f"Workflow instance {instance.id} started for encounter {encounter_id} by {actor_id}")
        return {
            "id": instance.id,
            "workflow_definition_id": instance.definition_id,
            "encounter_id": instance.encounter_id,
            "patient_id": instance.patient_id,
            "current_step_number": instance.current_step_number,
            "current_step_name": first_step_name,
            "status": instance.status,
            "started_at": instance.started_at,
            "completed_at": instance.completed_at
        }

    async def list_instances(
        self,
        encounter_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List clinical workflow instances with optional filtering."""
        query = select(WorkflowInstance)
        if encounter_id:
            query = query.where(WorkflowInstance.encounter_id == encounter_id)
        if status:
            query = query.where(WorkflowInstance.status == status.upper())
        result = await self.db.execute(query.order_by(desc(WorkflowInstance.started_at)))
        instances = result.scalars().all()
        out = []
        for inst in instances:
            out.append({
                "id": inst.id,
                "workflow_definition_id": inst.definition_id,
                "encounter_id": inst.encounter_id,
                "patient_id": inst.patient_id,
                "current_step_number": inst.current_step_number,
                "current_step_name": f"Step {inst.current_step_number}",
                "status": inst.status,
                "started_at": inst.started_at,
                "completed_at": inst.completed_at
            })
        return out

    async def get_instance_details(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details and progress of a specific workflow instance."""
        result = await self.db.execute(select(WorkflowInstance).where(WorkflowInstance.id == instance_id))
        instance = result.scalars().first()
        if not instance:
            raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
        return {
            "id": instance.id,
            "workflow_definition_id": instance.definition_id,
            "encounter_id": instance.encounter_id,
            "patient_id": instance.patient_id,
            "current_step_number": instance.current_step_number,
            "current_step_name": f"Step {instance.current_step_number}",
            "status": instance.status,
            "started_at": instance.started_at,
            "completed_at": instance.completed_at
        }

    async def get_current_step(self, instance_id: str) -> Optional[WorkflowStep]:
        """Fetch the active workflow step for a given instance."""
        res_inst = await self.db.execute(select(WorkflowInstance).where(WorkflowInstance.id == instance_id))
        inst = res_inst.scalars().first()
        if not inst:
            return None
        res_step = await self.db.execute(
            select(WorkflowStep).where(
                WorkflowStep.workflow_instance_id == instance_id,
                WorkflowStep.step_number == inst.current_step_number
            )
        )
        return res_step.scalars().first()

    async def advance_step(
        self,
        instance_id: str,
        notes: Optional[str],
        actor_id: str
    ) -> Dict[str, Any]:
        """
        Advance a clinical workflow to the next step with pessimistic row-level lock.
        State transition: Step N -> Step N+1, or ACTIVE -> COMPLETED (on final step)
        """
        res = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
        )
        instance = res.scalars().first()
        if not instance:
            raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
        if instance.status == "COMPLETED":
            raise HTTPException(status_code=400, detail="Workflow instance already completed")
        if instance.status in ["BLOCKED", "CANCELLED"]:
            raise HTTPException(status_code=400, detail=f"Cannot advance a {instance.status} workflow instance")

        wf_def = await self.get_definition(instance.definition_id)
        total_steps = len(wf_def.steps_json) if wf_def and wf_def.steps_json else 1

        # Complete current step
        step_res = await self.db.execute(
            select(WorkflowStep).where(
                WorkflowStep.workflow_instance_id == instance_id,
                WorkflowStep.step_number == instance.current_step_number
            ).with_for_update()
        )
        current_step = step_res.scalars().first()
        if current_step:
            current_step.status = "COMPLETED"
            current_step.completed_at = datetime.utcnow()
            current_step.assigned_to = actor_id

        step_name_display = f"Step {instance.current_step_number}"
        if instance.current_step_number < total_steps:
            next_step_num = instance.current_step_number + 1
            next_step_name = wf_def.steps_json[next_step_num - 1].get("name", f"Step {next_step_num}")
            step_name_display = next_step_name

            instance.current_step_number = next_step_num

            # Create record for new step
            next_step_record = WorkflowStep(
                workflow_instance_id=instance_id,
                step_number=next_step_num,
                name=next_step_name,
                status="IN_PROGRESS",
                started_at=datetime.utcnow()
            )
            self.db.add(next_step_record)
        else:
            # All steps complete
            instance.status = "COMPLETED"
            instance.completed_at = datetime.utcnow()

        audit = AuditLog(
            entity_type="workflow",
            entity_id=instance_id,
            field_changed="step",
            old_value=str(instance.current_step_number - 1),
            new_value=str(instance.current_step_number),
            changed_by=actor_id,
            change_reason=notes or f"Step {instance.current_step_number} updated"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(instance)
        logger.info(f"Workflow {instance_id} advanced to step {instance.current_step_number} by {actor_id}")
        return {
            "id": instance.id,
            "workflow_definition_id": instance.definition_id,
            "encounter_id": instance.encounter_id,
            "patient_id": instance.patient_id,
            "current_step_number": instance.current_step_number,
            "current_step_name": step_name_display,
            "status": instance.status,
            "started_at": instance.started_at,
            "completed_at": instance.completed_at
        }

    async def block_workflow(
        self,
        instance_id: str,
        actor_id: str,
        blocked_reason: str
    ) -> WorkflowInstance:
        """
        Mark a workflow instance as BLOCKED with pessimistic lock.
        State transition: ACTIVE -> BLOCKED
        """
        res = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
        )
        instance = res.scalars().first()
        if not instance:
            raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
        if instance.status != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Cannot block a workflow in '{instance.status}' state")

        instance.status = "BLOCKED"
        instance.blocked_reason = blocked_reason

        # Also mark current step as BLOCKED
        step = await self.get_current_step(instance_id)
        if step:
            step.status = "BLOCKED"

        audit = AuditLog(
            entity_type="workflow",
            entity_id=instance_id,
            field_changed="status",
            old_value="ACTIVE",
            new_value="BLOCKED",
            changed_by=actor_id,
            change_reason=f"Workflow blocked: {blocked_reason}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def resume_workflow(
        self,
        instance_id: str,
        actor_id: str
    ) -> WorkflowInstance:
        """
        Resume a previously blocked workflow instance with pessimistic lock.
        State transition: BLOCKED -> ACTIVE
        """
        res = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
        )
        instance = res.scalars().first()
        if not instance:
            raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
        if instance.status != "BLOCKED":
            raise HTTPException(status_code=400, detail=f"Cannot resume a workflow in '{instance.status}' state")

        instance.status = "ACTIVE"
        instance.blocked_reason = None

        step = await self.get_current_step(instance_id)
        if step:
            step.status = "IN_PROGRESS"

        audit = AuditLog(
            entity_type="workflow",
            entity_id=instance_id,
            field_changed="status",
            old_value="BLOCKED",
            new_value="ACTIVE",
            changed_by=actor_id,
            change_reason="Workflow resumed"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def cancel_workflow(
        self,
        instance_id: str,
        actor_id: str,
        reason: str
    ) -> WorkflowInstance:
        """
        Cancel a workflow instance with pessimistic lock.
        State transition: ACTIVE / BLOCKED -> CANCELLED
        """
        res = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
        )
        instance = res.scalars().first()
        if not instance:
            raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
        if instance.status == "COMPLETED":
            raise HTTPException(status_code=400, detail="Cannot cancel an already completed workflow")

        old_status = instance.status
        instance.status = "CANCELLED"
        instance.blocked_reason = reason

        audit = AuditLog(
            entity_type="workflow",
            entity_id=instance_id,
            field_changed="status",
            old_value=old_status,
            new_value="CANCELLED",
            changed_by=actor_id,
            change_reason=f"Workflow cancelled: {reason}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    # ─── 3. Workflow Steps Operations ───────────────────────────────────────

    async def skip_step(
        self,
        step_id: str,
        actor_id: str,
        reason: str
    ) -> WorkflowStep:
        """
        Skip a pending workflow step where permitted.
        State transition: PENDING -> SKIPPED
        """
        res = await self.db.execute(
            select(WorkflowStep).where(WorkflowStep.id == step_id).with_for_update()
        )
        step = res.scalars().first()
        if not step:
            raise HTTPException(status_code=404, detail=f"Workflow step {step_id} not found")
        if step.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Cannot skip a step in '{step.status}' state")

        step.status = "SKIPPED"
        step.completed_at = datetime.utcnow()
        step.assigned_to = actor_id

        audit = AuditLog(
            entity_type="workflow_step",
            entity_id=step_id,
            field_changed="status",
            old_value="PENDING",
            new_value="SKIPPED",
            changed_by=actor_id,
            change_reason=f"Step skipped: {reason}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(step)
        return step

    # ─── 4. Queue Integration Operations ────────────────────────────────────

    async def list_queues(self, department_id: Optional[str] = None) -> List[Queue]:
        """Query live queue depths and estimated wait times per department."""
        query = select(Queue)
        if department_id:
            query = query.where(Queue.department_id == department_id)
        result = await self.db.execute(query.order_by(Queue.department_id, Queue.position))
        return result.scalars().all()

    async def get_queue_entry(self, queue_id: str) -> Optional[Queue]:
        """Fetch a specific queue entry by ID."""
        res = await self.db.execute(select(Queue).where(Queue.id == queue_id))
        return res.scalars().first()

    async def add_to_queue(
        self,
        patient_id: str,
        encounter_id: str,
        department_id: str,
        queue_type: str,
        priority: int = 3,
        esi_level: int = 3,
        estimated_wait_mins: int = 15
    ) -> Queue:
        """
        Add a patient to a department queue, calculating next available position.
        State: -> WAITING
        """
        # Calculate current highest position in this queue
        pos_query = select(func.coalesce(func.max(Queue.position), 0)).where(
            Queue.department_id == department_id,
            Queue.queue_type == queue_type,
            Queue.status == "WAITING"
        )
        pos_res = await self.db.execute(pos_query)
        next_pos = (pos_res.scalar() or 0) + 1

        queue_entry = Queue(
            queue_type=queue_type,
            patient_id=patient_id,
            encounter_id=encounter_id,
            department_id=department_id,
            priority=priority,
            esi_level=esi_level,
            position=next_pos,
            status="WAITING",
            estimated_wait_mins=estimated_wait_mins,
            entered_at=datetime.utcnow()
        )
        self.db.add(queue_entry)
        await self.db.commit()
        await self.db.refresh(queue_entry)
        logger.info(f"Added patient {patient_id} to queue {queue_type} (pos: {next_pos})")
        return queue_entry

    async def update_queue_status(
        self,
        queue_id: str,
        status: str
    ) -> Queue:
        """
        Update queue entry lifecycle (WAITING -> CALLED -> COMPLETED / CANCELLED).
        """
        res = await self.db.execute(
            select(Queue).where(Queue.id == queue_id).with_for_update()
        )
        entry = res.scalars().first()
        if not entry:
            raise HTTPException(status_code=404, detail=f"Queue entry {queue_id} not found")

        status_clean = status.upper()
        if status_clean not in ["WAITING", "CALLED", "COMPLETED", "CANCELLED"]:
            raise HTTPException(status_code=400, detail=f"Invalid queue status: {status}")

        entry.status = status_clean
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    # ─── 5. Task Operations ─────────────────────────────────────────────────

    async def list_tasks(
        self,
        encounter_id: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Task]:
        """Query scheduled and active clinical workflow tasks."""
        query = select(Task)
        if encounter_id:
            query = query.where(Task.encounter_id == encounter_id)
        if assigned_to_id:
            query = query.where(Task.assigned_to_staff_id == assigned_to_id)
        if status:
            query = query.where(Task.status == status.upper())
        result = await self.db.execute(query.order_by(desc(Task.priority), desc(Task.created_at)))
        return result.scalars().all()

    async def create_task(
        self,
        encounter_id: str,
        patient_id: str,
        title: str,
        task_type: str,
        priority: int = 3,
        assigned_to_role: Optional[str] = None,
        assigned_to_staff_id: Optional[str] = None,
        description: Optional[str] = None,
        created_by_agent: Optional[str] = None
    ) -> Task:
        """Create a clinical workflow task."""
        task = Task(
            encounter_id=encounter_id,
            patient_id=patient_id,
            title=title,
            description=description,
            task_type=task_type,
            assigned_to_role=assigned_to_role,
            assigned_to_staff_id=assigned_to_staff_id,
            created_by_agent=created_by_agent,
            priority=priority,
            status="PENDING",
            created_at=datetime.utcnow()
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_to_staff_id: Optional[str] = None
    ) -> Task:
        """Update clinical task status (PENDING -> IN_PROGRESS -> COMPLETED)."""
        res = await self.db.execute(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        task = res.scalars().first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        status_clean = status.upper()
        if status_clean not in ["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"]:
            raise HTTPException(status_code=400, detail=f"Invalid task status: {status}")

        task.status = status_clean
        if assigned_to_staff_id:
            task.assigned_to_staff_id = assigned_to_staff_id
        if status_clean == "COMPLETED":
            task.completed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(task)
        return task
