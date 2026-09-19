import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles, get_current_staff
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Clinical Workflows & Operations"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class WorkflowDefinitionResponse(BaseModel):
    id: str
    name: str
    category: str
    steps_json: List[Dict[str, Any]]
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class WorkflowInstanceCreate(BaseModel):
    workflow_definition_id: str = Field(..., examples=["WFD-EMERGENCY-ADMISSION"])
    encounter_id: str = Field(..., examples=["ENC-0001"])
    patient_id: str = Field(..., examples=["PAT-0001"])


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

    model_config = ConfigDict(from_attributes=True)


class StepAdvanceRequest(BaseModel):
    notes: Optional[str] = Field(None, examples=["ESI triage completed, vital signs stable"])


class QueueResponse(BaseModel):
    id: str
    queue_type: str
    department_id: str
    current_depth: int
    estimated_wait_mins: float

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: str
    encounter_id: str
    patient_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: str
    assigned_to_role: Optional[str] = None
    assigned_to_staff_id: Optional[str] = None
    priority: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    encounter_id: str
    patient_id: str
    title: str
    task_type: str = Field(default="TRIAGE", examples=["TRIAGE"])
    priority: int = Field(default=3, ge=1, le=5)
    assigned_to_role: Optional[str] = None
    assigned_to_staff_id: Optional[str] = None
    description: Optional[str] = None


class TaskUpdate(BaseModel):
    status: str = Field(..., examples=["IN_PROGRESS"])
    assigned_to_staff_id: Optional[str] = None


# ─── Workflow Definition Endpoints ──────────────────────────────────────────

@router.get("/definitions", response_model=List[WorkflowDefinitionResponse])
async def list_workflow_definitions(
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List all registered clinical workflow templates (e.g., Emergency Admission, OPD Visit, Transfer)."""
    service = WorkflowService(db)
    return await service.list_definitions()


# ─── Workflow Instance Endpoints ────────────────────────────────────────────

@router.post("/instances", response_model=WorkflowInstanceResponse, status_code=201)
async def start_workflow_instance(
    req: WorkflowInstanceCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Start an active clinical workflow instance for a patient encounter."""
    service = WorkflowService(db)
    return await service.start_workflow(
        workflow_definition_id=req.workflow_definition_id,
        encounter_id=req.encounter_id,
        patient_id=req.patient_id,
        actor_id=current_staff.id
    )


@router.get("/instances", response_model=List[WorkflowInstanceResponse])
async def list_workflow_instances(
    encounter_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="ACTIVE, COMPLETED, CANCELLED"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max number of records to return"),
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """List clinical workflow instances with optional filtering and pagination."""
    service = WorkflowService(db)
    return await service.list_instances(
        encounter_id=encounter_id,
        status=status,
        skip=skip,
        limit=limit
    )


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceResponse)
async def get_workflow_instance(
    instance_id: str,
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve details and progress of a specific workflow instance."""
    service = WorkflowService(db)
    return await service.get_instance_details(instance_id)


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
    service = WorkflowService(db)
    return await service.advance_step(
        instance_id=instance_id,
        notes=req.notes,
        actor_id=current_staff.id
    )


# ─── Queues and Tasks Endpoints ─────────────────────────────────────────────

@router.get("/queues", response_model=List[QueueResponse])
async def list_department_queues(
    department_id: Optional[str] = Query(None),
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Query live queue depths and estimated wait times per department."""
    service = WorkflowService(db)
    return await service.list_queues(department_id=department_id)


@router.get("/tasks", response_model=List[TaskResponse])
async def list_clinical_tasks(
    encounter_id: Optional[str] = Query(None),
    assigned_to_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="PENDING, IN_PROGRESS, COMPLETED"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max number of records to return"),
    current_staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db)
):
    """Query scheduled and active clinical workflow tasks with pagination."""
    service = WorkflowService(db)
    return await service.list_tasks(
        encounter_id=encounter_id,
        assigned_to_id=assigned_to_id,
        status=status,
        skip=skip,
        limit=limit
    )


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_clinical_task(
    req: TaskCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Create a new clinical workflow task for an encounter."""
    service = WorkflowService(db)
    return await service.create_task(
        encounter_id=req.encounter_id,
        patient_id=req.patient_id,
        title=req.title,
        task_type=req.task_type,
        priority=req.priority,
        assigned_to_role=req.assigned_to_role,
        assigned_to_staff_id=req.assigned_to_staff_id,
        description=req.description,
        created_by_agent=None
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_clinical_task(
    task_id: str,
    req: TaskUpdate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE"])),
    db: AsyncSession = Depends(get_db)
):
    """Update clinical workflow task status (PENDING -> IN_PROGRESS -> COMPLETED)."""
    service = WorkflowService(db)
    return await service.update_task_status(
        task_id=task_id,
        status=req.status,
        assigned_to_staff_id=req.assigned_to_staff_id
    )
