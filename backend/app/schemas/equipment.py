from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class EquipmentResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    department_id: str
    status: str
    slot_duration_mins: int
    current_patient_id: Optional[str] = None
    current_encounter_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class EquipmentBookingCreate(BaseModel):
    equipment_id: str
    encounter_id: str
    patient_id: str
    requested_by: Optional[str] = None
    notes: Optional[str] = None

class EquipmentBookingResponse(BaseModel):
    id: str
    equipment_id: str
    encounter_id: str
    patient_id: str
    requested_by: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
