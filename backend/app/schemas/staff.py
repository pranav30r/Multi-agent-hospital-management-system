from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class StaffResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    role: str
    department_id: str
    specialization: Optional[str]
    status: str
    current_workload: int
    max_workload: int
    skills: Optional[list]
    created_at: datetime

    class Config:
        from_attributes = True

class StaffStatusUpdate(BaseModel):
    status: str
    changed_by: str = "ADM-001"
    reason: str = "Manual status update"

class StaffShiftResponse(BaseModel):
    id: str
    staff_id: str
    department_id: str
    shift_type: str
    start_time: str
    end_time: str
    status: str

    class Config:
        from_attributes = True
