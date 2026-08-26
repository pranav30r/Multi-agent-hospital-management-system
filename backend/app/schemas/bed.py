from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class BedResponse(BaseModel):
    id: str
    department_id: str
    bed_number: str
    bed_type: str
    status: str
    is_isolation_capable: bool
    current_patient_id: Optional[str]
    current_encounter_id: Optional[str]
    reserved_at: Optional[datetime]
    occupied_at: Optional[datetime]
    last_cleaned_at: Optional[datetime]

    class Config:
        from_attributes = True

class BedManualBookRequest(BaseModel):
    bed_id: str
    encounter_id: str
    patient_id: str
    booked_by: str = "ADM-001"
    reason: str = "Manual bed reservation via command center"

class BedStatusUpdate(BaseModel):
    status: str
    changed_by: str = "STAFF-001"
    reason: str = "Status update"
