import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinical_document import ClinicalDocument
from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_DOCUMENT_TYPES = {
    "LAB_REPORT",
    "XRAY_REPORT",
    "MRI_REPORT",
    "CT_REPORT",
    "PRESCRIPTION",
    "DISCHARGE_SUMMARY",
    "OTHER"
}


class ClinicalDocumentService:
    """
    Domain service for patient clinical documents (lab reports, radiology scans, prescriptions, summaries).
    Enforces strict patient/encounter ownership verification, immutable source metadata, and physician verification.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(
        self,
        patient_id: str,
        document_type: str,
        title: str,
        storage_key: str,
        encounter_id: Optional[str] = None,
        storage_provider: str = "LOCAL",
        original_filename: Optional[str] = None,
        content_type: str = "application/pdf",
        file_size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        document_date: Optional[datetime] = None,
        actor_id: str = "SYSTEM"
    ) -> ClinicalDocument:
        """
        Record a new clinical document for a patient with strict encounter validation and audit trail.
        """
        # 1. Validate patient
        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        # 2. Validate encounter if provided
        if encounter_id:
            enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
            encounter = enc_res.scalars().first()
            if not encounter:
                raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
            if encounter.patient_id != patient_id:
                raise HTTPException(status_code=400, detail=f"Encounter {encounter_id} does not belong to patient {patient_id}")

        doc_type_clean = document_type.upper().strip()
        if doc_type_clean not in VALID_DOCUMENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid document type '{document_type}'. Allowed: {sorted(VALID_DOCUMENT_TYPES)}")

        doc = ClinicalDocument(
            patient_id=patient_id,
            encounter_id=encounter_id,
            document_type=doc_type_clean,
            title=title.strip(),
            status="RECORDED",
            storage_key=storage_key.strip(),
            storage_provider=storage_provider.upper().strip(),
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            checksum=checksum,
            metadata_json=metadata_json or {},
            is_verified=False,
            uploaded_by=actor_id,
            document_date=document_date or utc_now(),
            created_at=utc_now()
        )
        self.db.add(doc)
        await self.db.flush()

        audit = AuditLog(
            entity_type="clinical_document",
            entity_id=doc.id,
            field_changed="document_creation",
            old_value=None,
            new_value="RECORDED",
            changed_by=actor_id,
            change_reason=f"Clinical document created: '{title}' ({doc_type_clean}) for patient {patient_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(doc)
        logger.info(f"Clinical document {doc.id} recorded for patient {patient_id} by {actor_id}")
        return doc

    async def get_document_by_id(self, document_id: str) -> Optional[ClinicalDocument]:
        """Fetch clinical document by primary ID with linked investigations."""
        stmt = (
            select(ClinicalDocument)
            .options(selectinload(ClinicalDocument.investigations))
            .where(ClinicalDocument.id == document_id)
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def list_patient_documents(self, patient_id: str) -> List[ClinicalDocument]:
        """List all clinical documents recorded for a patient in chronological order."""
        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        if not p_res.scalars().first():
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        stmt = (
            select(ClinicalDocument)
            .where(ClinicalDocument.patient_id == patient_id)
            .order_by(ClinicalDocument.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def list_encounter_documents(self, encounter_id: str) -> List[ClinicalDocument]:
        """List all clinical documents associated with a specific encounter."""
        enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
        if not enc_res.scalars().first():
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        stmt = (
            select(ClinicalDocument)
            .where(ClinicalDocument.encounter_id == encounter_id)
            .order_by(ClinicalDocument.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def verify_document(
        self,
        document_id: str,
        verifier_id: str,
        notes: Optional[str] = None
    ) -> ClinicalDocument:
        """Verify a clinical document by an authorized physician/clinical staff."""
        res = await self.db.execute(
            select(ClinicalDocument).where(ClinicalDocument.id == document_id).with_for_update()
        )
        doc = res.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")

        if doc.status == "ARCHIVED":
            raise HTTPException(status_code=400, detail=f"Cannot verify archived document {document_id}")

        doc.is_verified = True
        doc.status = "VERIFIED"
        doc.verified_by = verifier_id
        doc.verified_at = utc_now()
        if notes:
            doc.metadata_json = {**(doc.metadata_json or {}), "verification_notes": notes}

        audit = AuditLog(
            entity_type="clinical_document",
            entity_id=doc.id,
            field_changed="verification_status",
            old_value="RECORDED",
            new_value="VERIFIED",
            changed_by=verifier_id,
            change_reason=f"Clinical document verified by {verifier_id}" + (f": {notes}" if notes else "")
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(doc)
        logger.info(f"Clinical document {document_id} verified by {verifier_id}")
        return doc

    async def archive_document(
        self,
        document_id: str,
        actor_id: str,
        reason: Optional[str] = None
    ) -> ClinicalDocument:
        """Mark a clinical document as archived."""
        res = await self.db.execute(
            select(ClinicalDocument).where(ClinicalDocument.id == document_id).with_for_update()
        )
        doc = res.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")

        old_status = doc.status
        doc.status = "ARCHIVED"

        audit = AuditLog(
            entity_type="clinical_document",
            entity_id=doc.id,
            field_changed="archive_status",
            old_value=old_status,
            new_value="ARCHIVED",
            changed_by=actor_id,
            change_reason=reason or f"Document archived by {actor_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(doc)
        logger.info(f"Clinical document {document_id} archived by {actor_id}")
        return doc

    async def update_document_metadata(
        self,
        document_id: str,
        title: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        actor_id: str = "SYSTEM"
    ) -> ClinicalDocument:
        """Update clinical document title or metadata."""
        res = await self.db.execute(
            select(ClinicalDocument).where(ClinicalDocument.id == document_id).with_for_update()
        )
        doc = res.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")

        if title:
            doc.title = title.strip()
        if metadata_json is not None:
            doc.metadata_json = {**(doc.metadata_json or {}), **metadata_json}

        audit = AuditLog(
            entity_type="clinical_document",
            entity_id=doc.id,
            field_changed="metadata_update",
            old_value=None,
            new_value=doc.title,
            changed_by=actor_id,
            change_reason=f"Metadata updated by {actor_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(doc)
        return doc
