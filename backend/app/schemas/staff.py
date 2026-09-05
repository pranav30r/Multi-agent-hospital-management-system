from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class StaffResponse(BaseModel):
    id: str
    tenant_id: str = "HOSP-DEFAULT"
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str] = None
    status: str
    current_workload: int
    max_workload: int
    skills: Optional[list] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class StaffStatusUpdate(BaseModel):
    status: str
    changed_by: Optional[str] = None
    reason: str = "Manual status update"

class StaffShiftResponse(BaseModel):
    id: str
    staff_id: str
    department_id: str
    shift_type: str
    start_time: str
    end_time: str
    status: str

    model_config = ConfigDict(from_attributes=True)
