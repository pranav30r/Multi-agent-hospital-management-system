from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class BedResponse(BaseModel):
    id: str
    department_id: str
    bed_type: str
    status: str
    is_isolation: bool = False
    has_ventilator: bool = False
    has_telemetry: bool = False
    current_patient_id: Optional[str] = None
    current_encounter_id: Optional[str] = None
    last_cleaned_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class BedManualBookRequest(BaseModel):
    bed_id: str
    encounter_id: str
    patient_id: str
    booked_by: Optional[str] = None
    reason: str = "Manual bed reservation via command center"

class BedStatusUpdate(BaseModel):
    status: str
    changed_by: Optional[str] = None
    reason: str = "Status update"
