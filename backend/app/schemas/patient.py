from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class PatientCreate(BaseModel):
    first_name: str = Field(..., example="Rajesh")
    last_name: str = Field(..., example="Kumar")
    age: int = Field(..., ge=0, le=120, example=55)
    gender: str = Field(..., example="M")
    blood_group: str = Field(..., example="O+")
    contact_phone: str = Field(..., example="+919876543210")
    emergency_contact: str = Field(..., example="+919876543211")
    allergies: Optional[List[str]] = Field(default_factory=list)
    chronic_conditions: Optional[List[str]] = Field(default_factory=list)

class PatientResponse(PatientCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class EncounterCreate(BaseModel):
    patient_id: str = Field(..., example="PAT-0001")
    chief_complaint: str = Field(..., example="Severe crushing chest pain radiating to left arm with diaphoresis")
    encounter_type: str = Field(default="EMERGENCY")
    current_department_id: str = Field(default="DEP-ER")
    
    # Optional Intake Vitals
    heart_rate: Optional[int] = Field(None, ge=30, le=250, example=115)
    bp_systolic: Optional[int] = Field(None, ge=50, le=300, example=145)
    bp_diastolic: Optional[int] = Field(None, ge=20, le=200, example=95)
    spo2: Optional[int] = Field(None, ge=50, le=100, example=88)
    temperature_f: Optional[float] = Field(None, ge=90.0, le=110.0, example=99.2)
    pain_level: Optional[int] = Field(None, ge=0, le=10, example=9)
    respiratory_rate: Optional[int] = Field(None, ge=5, le=60, example=24)
    gcs_score: Optional[int] = Field(None, ge=3, le=15, example=14)

class EncounterResponse(BaseModel):
    id: str
    patient_id: str
    encounter_type: str
    status: str
    current_department_id: str
    current_bed_id: Optional[str]
    assigned_doctor_id: Optional[str]
    assigned_nurse_id: Optional[str]
    esi_level: int
    priority: int
    patient_status: str
    chief_complaint: str
    heart_rate: Optional[int]
    bp_systolic: Optional[int]
    bp_diastolic: Optional[int]
    spo2: Optional[int]
    temperature_f: Optional[float]
    pain_level: Optional[int]
    arrival_time: datetime

    class Config:
        from_attributes = True
