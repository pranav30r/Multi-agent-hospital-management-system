import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.staff import Staff
from app.auth.dependencies import require_roles
from app.services.clinical_document_service import ClinicalDocumentService
from app.schemas.clinical_document import (
    DocumentCreate, DocumentUpdate, DocumentResponse, DocumentVerifyRequest
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinical-documents", tags=["Clinical Documents & Investigation Reports"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_clinical_document(
    doc_in: DocumentCreate,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "RECEPTIONIST", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Record metadata for a patient's clinical document (lab report, radiology scan, prescription, summary)."""
    service = ClinicalDocumentService(db)
    return await service.create_document(
        patient_id=doc_in.patient_id,
        encounter_id=doc_in.encounter_id,
        document_type=doc_in.document_type,
        title=doc_in.title,
        storage_key=doc_in.storage_key,
        storage_provider=doc_in.storage_provider,
        original_filename=doc_in.original_filename,
        content_type=doc_in.content_type,
        file_size_bytes=doc_in.file_size_bytes,
        checksum=doc_in.checksum,
        metadata_json=doc_in.metadata_json,
        document_date=doc_in.document_date,
        actor_id=current_staff.id
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_clinical_document(
    document_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve metadata and verification status for a clinical document by ID."""
    service = ClinicalDocumentService(db)
    doc = await service.get_document_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")
    return doc


@router.get("/patient/{patient_id}", response_model=List[DocumentResponse])
async def list_patient_documents(
    patient_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """List all clinical documents recorded for a patient."""
    service = ClinicalDocumentService(db)
    return await service.list_patient_documents(patient_id)


@router.get("/encounter/{encounter_id}", response_model=List[DocumentResponse])
async def list_encounter_documents(
    encounter_id: str,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "NURSE", "CHARGE_NURSE", "LAB_TECH", "RADIOLOGIST"])),
    db: AsyncSession = Depends(get_db)
):
    """List all clinical documents associated with a specific encounter."""
    service = ClinicalDocumentService(db)
    return await service.list_encounter_documents(encounter_id)


@router.post("/{document_id}/verify", response_model=DocumentResponse)
async def verify_clinical_document(
    document_id: str,
    verify_in: DocumentVerifyRequest,
    current_staff: Staff = Depends(require_roles(["ADMINISTRATOR", "DOCTOR", "RADIOLOGIST", "LAB_TECH"])),
    db: AsyncSession = Depends(get_db)
):
    """Physician or diagnostic specialist verification of a clinical document."""
    service = ClinicalDocumentService(db)
    return await service.verify_document(
        document_id=document_id,
        verifier_id=current_staff.id,
        notes=verify_in.notes
    )
