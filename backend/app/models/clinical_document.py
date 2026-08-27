from datetime import datetime
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ClinicalDocument(Base):
    """
    Domain entity representing patient clinical documents (lab reports, radiology reports,
    prescriptions, discharge summaries) with storage abstractions and verification status.
    """
    __tablename__ = "clinical_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"DOC-{uuid.uuid4().hex[:6].upper()}")
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("encounters.id"), nullable=True, index=True)

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)  # LAB_REPORT, XRAY_REPORT, MRI_REPORT, CT_REPORT, PRESCRIPTION, DISCHARGE_SUMMARY, OTHER
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="RECORDED", index=True)  # RECORDED, VERIFIED, ARCHIVED

    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(50), default="LOCAL")  # LOCAL, S3, MINIO
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    uploaded_by: Mapped[str] = mapped_column(String, default="SYSTEM")
    document_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    investigations: Mapped[List["ClinicalInvestigation"]] = relationship("ClinicalInvestigation", back_populates="document")


class ClinicalInvestigation(Base):
    """
    Structured domain entity for clinical diagnostic test results (blood, urine, radiology, etc.)
    with structured values, reference ranges, abnormal flags, and source document links.
    """
    __tablename__ = "clinical_investigations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"INV-{uuid.uuid4().hex[:6].upper()}")
    patient_id: Mapped[str] = mapped_column(String, ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("encounters.id"), nullable=True, index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("clinical_documents.id"), nullable=True, index=True)

    investigation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # BLOOD_TEST, URINE_TEST, XRAY, MRI, CT, ULTRASOUND, ECG, OTHER
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ORDERED", index=True)  # ORDERED, IN_PROGRESS, COMPLETED, VERIFIED, CANCELLED

    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_values: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    is_abnormal: Mapped[bool] = mapped_column(Boolean, default=False)
    abnormal_flags: Mapped[Optional[dict]] = mapped_column(JSON, default=list)

    ordered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    ordered_by: Mapped[str] = mapped_column(String, default="SYSTEM")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    document: Mapped[Optional["ClinicalDocument"]] = relationship("ClinicalDocument", back_populates="investigations")
