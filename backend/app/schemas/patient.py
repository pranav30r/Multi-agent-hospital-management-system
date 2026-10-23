from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

class PatientCreate(BaseModel):
    first_name: str = Field(..., description="Patient first name")
    last_name: str = Field(..., description="Patient last name")
    age: int = Field(..., ge=0, le=120, description="Patient age")
    gender: str = Field(..., description="Gender (M, F, OTHER)")
    blood_group: str = Field(..., description="Blood Group (A+, B+, O+, AB+, etc.)")
    contact_phone: str = Field(..., description="Contact phone number")
    emergency_contact: str = Field(..., description="Emergency contact phone")
    allergies: Optional[List[str]] = Field(default_factory=list)
    chronic_conditions: Optional[List[str]] = Field(default_factory=list)

class PatientResponse(PatientCreate):
    id: str
    tenant_id: str = "HOSP-DEFAULT"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class EncounterCreate(BaseModel):
    patient_id: str = Field(..., description="Patient ID")
    chief_complaint: str = Field(..., description="Primary clinical presentation / complaint")
    encounter_type: str = Field(default="EMERGENCY")
    current_department_id: Optional[str] = None
    
    # Optional Intake Vitals
    heart_rate: Optional[int] = Field(None, ge=30, le=250)
    bp_systolic: Optional[int] = Field(None, ge=50, le=300)
    bp_diastolic: Optional[int] = Field(None, ge=20, le=200)
    spo2: Optional[int] = Field(None, ge=50, le=100)
    temperature_f: Optional[float] = Field(None, ge=90.0, le=110.0)
    pain_level: Optional[int] = Field(None, ge=0, le=10)
    respiratory_rate: Optional[int] = Field(None, ge=5, le=60)
    gcs_score: Optional[int] = Field(None, ge=3, le=15)

class EncounterStaffAssignment(BaseModel):
    doctor_id: Optional[str] = None
    nurse_id: Optional[str] = None

class EncounterResponse(BaseModel):
    id: str
    patient_id: str
    patient_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    encounter_type: str
    status: str
    current_department_id: str
    current_bed_id: Optional[str] = None
    assigned_doctor_id: Optional[str] = None
    assigned_nurse_id: Optional[str] = None
    esi_level: int
    priority: int
    patient_status: str
    chief_complaint: str
    heart_rate: Optional[int] = None
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    spo2: Optional[int] = None
    temperature_f: Optional[float] = None
    pain_level: Optional[int] = None
    respiratory_rate: Optional[int] = None
    gcs_score: Optional[int] = None
    arrival_time: datetime

    model_config = ConfigDict(from_attributes=True)
