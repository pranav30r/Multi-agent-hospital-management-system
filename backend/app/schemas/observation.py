from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ObservationCreate(BaseModel):
    patient_id: str = Field(..., description="Target patient ID")
    encounter_id: str = Field(..., description="Active encounter ID")
    observation_type: str = Field(..., description="Type of clinical observation (HEART_RATE, BP_SYSTOLIC, BP_DIASTOLIC, SPO2, TEMPERATURE_F, RESPIRATORY_RATE, PAIN_LEVEL, GCS_SCORE, BLOOD_GLUCOSE, WEIGHT_KG, HEIGHT_CM, NOTE, etc.)")
    value_numeric: Optional[float] = Field(None, description="Numeric measurement value")
    value_text: Optional[str] = Field(None, description="Qualitative or textual observation")
    unit: Optional[str] = Field(None, description="Measurement unit (bpm, mmHg, %, °F, mg/dL, kg, cm)")
    observed_at: Optional[datetime] = Field(None, description="Timestamp when measurement was taken (defaults to UTC now)")
    source: str = Field("MANUAL", description="Observation origin (MANUAL, DEVICE, INTAKE, IMPORT)")
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional structured context")


class ObservationBatchCreate(BaseModel):
    patient_id: str = Field(..., description="Target patient ID")
    encounter_id: str = Field(..., description="Active encounter ID")
    source: str = Field("DEVICE", description="Source of observations")
    observations: List[Dict[str, Any]] = Field(..., description="List of observation items with observation_type, value_numeric/text, unit")


class ObservationCorrectionRequest(BaseModel):
    new_value_numeric: Optional[float] = Field(None, description="Corrected numeric value")
    new_value_text: Optional[str] = Field(None, description="Corrected text value")
    new_unit: Optional[str] = Field(None, description="Corrected unit")
    reason: str = Field(..., description="Clinical justification for observation correction")


class ObservationResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: str
    tenant_id: str
    observation_type: str
    value_numeric: Optional[float]
    value_text: Optional[str]
    unit: Optional[str]
    observed_at: datetime
    recorded_at: datetime
    recorded_by: str
    source: str
    status: str
    correction_of: Optional[str]
    correction_reason: Optional[str]
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LatestVitalsResponse(BaseModel):
    patient_id: str
    tenant_id: str
    vitals: Dict[str, Optional[ObservationResponse]]
    last_updated: Optional[datetime]
