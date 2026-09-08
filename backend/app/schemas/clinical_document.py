from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    patient_id: str = Field(..., description="ID of the patient who owns this document")
    encounter_id: Optional[str] = Field(None, description="Optional associated clinical encounter ID")
    document_type: str = Field(..., description="Document type (LAB_REPORT, XRAY_REPORT, MRI_REPORT, CT_REPORT, PRESCRIPTION, DISCHARGE_SUMMARY, OTHER)")
    title: str = Field(..., description="Descriptive title of the document")
    storage_key: str = Field(..., description="Storage key / identifier in the storage backend")
    storage_provider: str = Field("LOCAL", description="Storage backend provider (LOCAL, S3, MINIO)")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    content_type: str = Field("application/pdf", description="MIME content type")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    checksum: Optional[str] = Field(None, description="SHA-256 or MD5 checksum")
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom document metadata")
    document_date: Optional[datetime] = Field(None, description="Date on the document")


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentVerifyRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Verification notes")


class DocumentResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: Optional[str]
    document_type: str
    title: str
    status: str
    storage_key: str
    storage_provider: str
    original_filename: Optional[str]
    content_type: str
    file_size_bytes: Optional[int]
    checksum: Optional[str]
    metadata_json: Optional[Dict[str, Any]]
    is_verified: bool
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    uploaded_by: str
    document_date: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvestigationCreate(BaseModel):
    patient_id: str = Field(..., description="ID of the patient")
    encounter_id: Optional[str] = Field(None, description="Optional associated clinical encounter ID")
    document_id: Optional[str] = Field(None, description="Optional source clinical document ID")
    investigation_type: str = Field(..., description="Type of investigation (BLOOD_TEST, URINE_TEST, XRAY, MRI, CT, ULTRASOUND, ECG, OTHER)")
    test_name: str = Field(..., description="Specific test name (e.g. Complete Blood Count, Chest X-Ray)")
    result_summary: Optional[str] = Field(None, description="Summary of clinical findings")
    result_values: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured quantitative/qualitative result dictionary")
    is_abnormal: bool = Field(False, description="Flag indicating if results are clinically abnormal")
    abnormal_flags: Optional[List[str]] = Field(default_factory=list, description="Specific abnormal finding tags")


class InvestigationUpdateResult(BaseModel):
    status: str = Field("COMPLETED", description="Investigation status (IN_PROGRESS, COMPLETED)")
    result_summary: Optional[str] = None
    result_values: Optional[Dict[str, Any]] = None
    is_abnormal: Optional[bool] = None
    abnormal_flags: Optional[List[str]] = None


class InvestigationVerifyRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Verification notes")


class InvestigationResponse(BaseModel):
    id: str
    patient_id: str
    encounter_id: Optional[str]
    document_id: Optional[str]
    investigation_type: str
    test_name: str
    status: str
    result_summary: Optional[str]
    result_values: Optional[Dict[str, Any]]
    is_abnormal: bool
    abnormal_flags: Optional[List[str]]
    ordered_at: datetime
    completed_at: Optional[datetime]
    is_verified: bool
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    ordered_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
