import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.workflow import (
    WorkflowDefinition, WorkflowInstance, WorkflowStep,
    Queue, Task, Admission, Transfer, Discharge
)
from app.models.agent import AuditLog
from app.models.staff import Staff
from app.auth.dependencies import require_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Clinical Workflows & Operations"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class WorkflowDefinitionResponse(BaseModel):
    id: str
    name: str
    category: str
    steps_json: List[Dict[str, Any]]
    is_active: bool = True

    class Config:
        from_attributes = True


class WorkflowInstanceCreate(BaseModel):
    workflow_definition_id: str = Field(..., example="WFD-EMERGENCY-ADMISSION")
    encounter_id: str = Field(..., example="ENC-0001")
    patient_id: str = Field(..., example="PAT-0001")


class WorkflowInstanceResponse(BaseModel):
    id: str
    workflow_definition_id: str
    encounter_id: str
    patient_id: str
    current_step_number: int
    current_step_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class StepAdvanceRequest(BaseModel):
    notes: Optional[str] = Field(None, example="ESI triage completed, vital signs stable")


class QueueResponse(BaseModel):
    id: str
    queue_type: str
    department_id: str
    current_depth: int
    estimated_wait_mins: float

    class Config:
        from_attributes = True


class TaskResponse(BaseModel):
    id: str
    encounter_id: str
    task_type: str
    priority: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Workflow Definition Endpoints ──────────────────────────────────────────

@router.get("/definitions", response_model=List[WorkflowDefinitionResponse])
async def list_workflow_definitions(db: AsyncSession = Depends(get_db)):
    """List all registered clinical workflow templates (e.g., Emergency Admission, OPD Visit, Transfer)."""
    result = await db.execute(select(WorkflowDefinition))
    return result.scalars().all()


# ─── Workflow Instance Endpoints ────────────────────────────────────────────

@router.post("/instances", response_model=WorkflowInstanceResponse, status_code=201)
async def start_workflow_instance(
    req: WorkflowInstanceCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Start an active clinical workflow instance for a patient encounter."""
    def_result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == req.workflow_definition_id)
    )
    wf_def = def_result.scalars().first()
    if not wf_def:
        raise HTTPException(status_code=404, detail=f"Workflow definition {req.workflow_definition_id} not found")

    first_step_name = wf_def.steps_json[0].get("name", "Step 1") if wf_def.steps_json else "Initial"

    instance_id = f"WFI-{uuid.uuid4().hex[:6].upper()}"
    instance = WorkflowInstance(
        id=instance_id,
        definition_id=req.workflow_definition_id,
        encounter_id=req.encounter_id,
        patient_id=req.patient_id,
        current_step_number=1,
        status="ACTIVE",
        started_at=datetime.utcnow()
    )
    db.add(instance)

    # Record initial step record
    step_record = WorkflowStep(
        workflow_instance_id=instance_id,
        step_number=1,
        name=first_step_name,
        status="IN_PROGRESS",
        started_at=datetime.utcnow()
    )
    db.add(step_record)

    audit = AuditLog(
        entity_type="workflow",
        entity_id=instance_id,
        field_changed="status",
        old_value=None,
        new_value="ACTIVE",
        changed_by=current_staff.id,
        change_reason=f"Started workflow {wf_def.name} for encounter {req.encounter_id}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(instance)
    logger.info(f"Workflow instance {instance.id} started for encounter {req.encounter_id} by {current_staff.id}")
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


@router.get("/instances", response_model=List[WorkflowInstanceResponse])
async def list_workflow_instances(
    encounter_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="ACTIVE, COMPLETED, CANCELLED"),
    db: AsyncSession = Depends(get_db)
):
    """List clinical workflow instances with optional filtering."""
    query = select(WorkflowInstance)
    if encounter_id:
        query = query.where(WorkflowInstance.encounter_id == encounter_id)
    if status:
        query = query.where(WorkflowInstance.status == status.upper())
    result = await db.execute(query.order_by(desc(WorkflowInstance.started_at)))
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


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceResponse)
async def get_workflow_instance(instance_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve details and progress of a specific workflow instance."""
    result = await db.execute(select(WorkflowInstance).where(WorkflowInstance.id == instance_id))
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


@router.post("/instances/{instance_id}/advance", response_model=WorkflowInstanceResponse)
async def advance_workflow_step(
    instance_id: str,
    req: StepAdvanceRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Advance a clinical workflow to the next step with row-level locking.
    Updates historical step completion and concludes the workflow when last step finishes.
    """
    res = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
    )
    instance = res.scalars().first()
    if not instance:
        raise HTTPException(status_code=404, detail=f"Workflow instance {instance_id} not found")
    if instance.status == "COMPLETED":
        raise HTTPException(status_code=400, detail="Workflow instance already completed")

    def_result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == instance.definition_id)
    )
    wf_def = def_result.scalars().first()
    total_steps = len(wf_def.steps_json) if wf_def and wf_def.steps_json else 1

    # Complete current step
    step_res = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.workflow_instance_id == instance_id,
            WorkflowStep.step_number == instance.current_step_number
        ).with_for_update()
    )
    current_step = step_res.scalars().first()
    if current_step:
        current_step.status = "COMPLETED"
        current_step.completed_at = datetime.utcnow()
        current_step.assigned_to = current_staff.id

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
        db.add(next_step_record)
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
        changed_by=current_staff.id,
        change_reason=req.notes or f"Step {instance.current_step_number} updated"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(instance)
    logger.info(f"Workflow {instance_id} advanced to step {instance.current_step_number} by {current_staff.id}")
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


# ─── Queues and Tasks Endpoints ─────────────────────────────────────────────

@router.get("/queues", response_model=List[QueueResponse])
async def list_department_queues(
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Query live queue depths and estimated wait times per department."""
    query = select(Queue)
    if department_id:
        query = query.where(Queue.department_id == department_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tasks", response_model=List[TaskResponse])
async def list_clinical_tasks(
    encounter_id: Optional[str] = Query(None),
    assigned_to_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="PENDING, IN_PROGRESS, COMPLETED"),
    db: AsyncSession = Depends(get_db)
):
    """Query scheduled and active clinical workflow tasks."""
    query = select(Task)
    if encounter_id:
        query = query.where(Task.encounter_id == encounter_id)
    if assigned_to_id:
        query = query.where(Task.assigned_to_id == assigned_to_id)
    if status:
        query = query.where(Task.status == status.upper())
    result = await db.execute(query.order_by(desc(Task.priority), desc(Task.created_at)))
    return result.scalars().all()
