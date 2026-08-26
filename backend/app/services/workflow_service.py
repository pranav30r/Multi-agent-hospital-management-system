import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    WorkflowDefinition, WorkflowInstance, WorkflowStep,
    Queue, Task
)
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

class WorkflowService:
    """
    Application Service for Clinical Workflows, Queues, and Operational Tasks.
    Encapsulates workflow template management, instance lifecycle, step sequencing, and concurrency locking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_definitions(self) -> List[WorkflowDefinition]:
        """List all registered clinical workflow definitions."""
        result = await self.db.execute(select(WorkflowDefinition))
        return result.scalars().all()

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
        def_result = await self.db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_definition_id)
        )
        wf_def = def_result.scalars().first()
        if not wf_def:
            raise HTTPException(status_code=404, detail=f"Workflow definition {workflow_definition_id} not found")

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

        def_result = await self.db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == instance.definition_id)
        )
        wf_def = def_result.scalars().first()
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

    async def list_queues(self, department_id: Optional[str] = None) -> List[Queue]:
        """Query live queue depths and estimated wait times per department."""
        query = select(Queue)
        if department_id:
            query = query.where(Queue.department_id == department_id)
        result = await self.db.execute(query)
        return result.scalars().all()

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
            query = query.where(Task.assigned_to_id == assigned_to_id)
        if status:
            query = query.where(Task.status == status.upper())
        result = await self.db.execute(query.order_by(desc(Task.priority), desc(Task.created_at)))
        return result.scalars().all()
