import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinical_document import ClinicalInvestigation, ClinicalDocument
from app.models.patient import Patient, Encounter
from app.models.agent import AuditLog

logger = logging.getLogger(__name__)

VALID_INVESTIGATION_TYPES = {
    "BLOOD_TEST",
    "URINE_TEST",
    "XRAY",
    "MRI",
    "CT",
    "ULTRASOUND",
    "ECG",
    "OTHER"
}


class InvestigationService:
    """
    Domain service for clinical diagnostic test orders and structured results.
    Enforces cross-entity patient/encounter/document validation, result structuring, abnormal flagging, and physician verification.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_investigation(
        self,
        patient_id: str,
        investigation_type: str,
        test_name: str,
        encounter_id: Optional[str] = None,
        document_id: Optional[str] = None,
        result_summary: Optional[str] = None,
        result_values: Optional[Dict[str, Any]] = None,
        is_abnormal: bool = False,
        abnormal_flags: Optional[List[str]] = None,
        ordered_by: str = "SYSTEM"
    ) -> ClinicalInvestigation:
        """
        Order or record a new clinical investigation with patient, encounter, and document consistency checks.
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

        # 3. Validate source document if provided
        if document_id:
            doc_res = await self.db.execute(select(ClinicalDocument).where(ClinicalDocument.id == document_id))
            doc = doc_res.scalars().first()
            if not doc:
                raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")
            if doc.patient_id != patient_id:
                raise HTTPException(status_code=400, detail=f"Document {document_id} does not belong to patient {patient_id}")

        inv_type_clean = investigation_type.upper().strip()
        if inv_type_clean not in VALID_INVESTIGATION_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid investigation type '{investigation_type}'. Allowed: {sorted(VALID_INVESTIGATION_TYPES)}")

        init_status = "COMPLETED" if (result_summary or result_values) else "ORDERED"

        inv = ClinicalInvestigation(
            patient_id=patient_id,
            encounter_id=encounter_id,
            document_id=document_id,
            investigation_type=inv_type_clean,
            test_name=test_name.strip(),
            status=init_status,
            result_summary=result_summary,
            result_values=result_values or {},
            is_abnormal=is_abnormal,
            abnormal_flags=abnormal_flags or [],
            ordered_at=datetime.utcnow(),
            completed_at=datetime.utcnow() if init_status == "COMPLETED" else None,
            is_verified=False,
            ordered_by=ordered_by,
            created_at=datetime.utcnow()
        )
        self.db.add(inv)
        await self.db.flush()

        audit = AuditLog(
            entity_type="clinical_investigation",
            entity_id=inv.id,
            field_changed="investigation_order",
            old_value=None,
            new_value=init_status,
            changed_by=ordered_by,
            change_reason=f"Investigation ordered: '{test_name}' ({inv_type_clean}) for patient {patient_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(inv)
        logger.info(f"Clinical investigation {inv.id} ({test_name}) created for patient {patient_id} by {ordered_by}")
        return inv

    async def get_investigation_by_id(self, investigation_id: str) -> Optional[ClinicalInvestigation]:
        """Retrieve clinical investigation by primary ID with linked document."""
        stmt = (
            select(ClinicalInvestigation)
            .options(selectinload(ClinicalInvestigation.document))
            .where(ClinicalInvestigation.id == investigation_id)
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def list_patient_investigations(self, patient_id: str) -> List[ClinicalInvestigation]:
        """List all clinical investigations for a patient in chronological order."""
        p_res = await self.db.execute(select(Patient).where(Patient.id == patient_id))
        if not p_res.scalars().first():
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        stmt = (
            select(ClinicalInvestigation)
            .where(ClinicalInvestigation.patient_id == patient_id)
            .order_by(ClinicalInvestigation.ordered_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def list_encounter_investigations(self, encounter_id: str) -> List[ClinicalInvestigation]:
        """List all clinical investigations associated with a specific encounter."""
        enc_res = await self.db.execute(select(Encounter).where(Encounter.id == encounter_id))
        if not enc_res.scalars().first():
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        stmt = (
            select(ClinicalInvestigation)
            .where(ClinicalInvestigation.encounter_id == encounter_id)
            .order_by(ClinicalInvestigation.ordered_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def record_investigation_results(
        self,
        investigation_id: str,
        result_summary: Optional[str] = None,
        result_values: Optional[Dict[str, Any]] = None,
        is_abnormal: Optional[bool] = None,
        abnormal_flags: Optional[List[str]] = None,
        status: str = "COMPLETED",
        actor_id: str = "SYSTEM"
    ) -> ClinicalInvestigation:
        """Record structured clinical results for an investigation."""
        res = await self.db.execute(
            select(ClinicalInvestigation).where(ClinicalInvestigation.id == investigation_id).with_for_update()
        )
        inv = res.scalars().first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

        if inv.is_verified:
            raise HTTPException(status_code=400, detail=f"Cannot alter results of verified investigation {investigation_id}")

        if result_summary is not None:
            inv.result_summary = result_summary
        if result_values is not None:
            inv.result_values = result_values
        if is_abnormal is not None:
            inv.is_abnormal = is_abnormal
        if abnormal_flags is not None:
            inv.abnormal_flags = abnormal_flags

        inv.status = status.upper().strip()
        inv.completed_at = datetime.utcnow()

        audit = AuditLog(
            entity_type="clinical_investigation",
            entity_id=inv.id,
            field_changed="results_recorded",
            old_value="ORDERED",
            new_value=inv.status,
            changed_by=actor_id,
            change_reason=f"Results recorded for {inv.test_name} by {actor_id} (Abnormal: {inv.is_abnormal})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(inv)
        logger.info(f"Results recorded for investigation {investigation_id} by {actor_id}")
        return inv

    async def verify_investigation(
        self,
        investigation_id: str,
        verifier_id: str,
        notes: Optional[str] = None
    ) -> ClinicalInvestigation:
        """Verify an investigation result by an authorized physician."""
        res = await self.db.execute(
            select(ClinicalInvestigation).where(ClinicalInvestigation.id == investigation_id).with_for_update()
        )
        inv = res.scalars().first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

        if inv.status == "CANCELLED":
            raise HTTPException(status_code=400, detail=f"Cannot verify cancelled investigation {investigation_id}")

        inv.is_verified = True
        inv.status = "VERIFIED"
        inv.verified_by = verifier_id
        inv.verified_at = datetime.utcnow()
        if notes:
            inv.result_summary = f"{inv.result_summary or ''}\n[Verified Note by {verifier_id}]: {notes}".strip()

        audit = AuditLog(
            entity_type="clinical_investigation",
            entity_id=inv.id,
            field_changed="verification_status",
            old_value="COMPLETED",
            new_value="VERIFIED",
            changed_by=verifier_id,
            change_reason=f"Investigation verified by {verifier_id}" + (f": {notes}" if notes else "")
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(inv)
        logger.info(f"Clinical investigation {investigation_id} verified by {verifier_id}")
        return inv

    async def link_to_document(
        self,
        investigation_id: str,
        document_id: str,
        actor_id: str = "SYSTEM"
    ) -> ClinicalInvestigation:
        """Link an investigation to a clinical document belonging to the same patient."""
        res_inv = await self.db.execute(
            select(ClinicalInvestigation).where(ClinicalInvestigation.id == investigation_id).with_for_update()
        )
        inv = res_inv.scalars().first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")

        res_doc = await self.db.execute(
            select(ClinicalDocument).where(ClinicalDocument.id == document_id)
        )
        doc = res_doc.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Clinical document {document_id} not found")

        if doc.patient_id != inv.patient_id:
            raise HTTPException(status_code=400, detail=f"Document {document_id} belongs to patient {doc.patient_id}, but investigation belongs to {inv.patient_id}")

        inv.document_id = document_id

        audit = AuditLog(
            entity_type="clinical_investigation",
            entity_id=inv.id,
            field_changed="document_link",
            old_value=None,
            new_value=document_id,
            changed_by=actor_id,
            change_reason=f"Linked to document {document_id}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(inv)
        return inv
