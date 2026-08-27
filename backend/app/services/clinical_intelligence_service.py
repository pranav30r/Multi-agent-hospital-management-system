import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.intake import ClinicalIntakeSession, ClinicalAssessment
from app.models.agent import AuditLog
from app.services.red_flag_service import RedFlagService
from app.services.clinical_severity_service import ClinicalSeverityService
from app.services.clinical_summary_service import ClinicalSummaryService

logger = logging.getLogger(__name__)


class ClinicalIntelligenceService:
    """
    Coordinating domain service for clinical decision support intelligence.
    Orchestrates RedFlagService, ClinicalSeverityService, and ClinicalSummaryService to generate
    deterministic, explainable clinical intelligence and persist ClinicalAssessment records.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.red_flag_service = RedFlagService()
        self.severity_service = ClinicalSeverityService()
        self.summary_service = ClinicalSummaryService()

    async def analyze_encounter(
        self,
        encounter_id: str,
        actor_id: str = "SYSTEM"
    ) -> ClinicalAssessment:
        """
        Execute deterministic clinical intelligence analysis for an encounter and persist assessment.
        """
        # 1. Fetch encounter with lock
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        # 2. Fetch patient
        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {encounter.patient_id} not found")

        # 3. Fetch linked intake session if available
        intk_res = await self.db.execute(
            select(ClinicalIntakeSession)
            .where(ClinicalIntakeSession.encounter_id == encounter_id)
            .order_by(ClinicalIntakeSession.created_at.desc())
        )
        intake_session = intk_res.scalars().first()
        if not intake_session:
            # Fallback: check most recent completed intake for this patient
            recent_res = await self.db.execute(
                select(ClinicalIntakeSession)
                .where(
                    ClinicalIntakeSession.patient_id == patient.id,
                    ClinicalIntakeSession.status.in_(["COMPLETED", "REVIEWED"])
                )
                .order_by(ClinicalIntakeSession.created_at.desc())
            )
            intake_session = recent_res.scalars().first()

        intake_summary = intake_session.structured_summary if intake_session else {}

        # 4. Assemble vitals dictionary
        vitals_dict = {
            "heart_rate": encounter.heart_rate,
            "bp_systolic": encounter.bp_systolic,
            "bp_diastolic": encounter.bp_diastolic,
            "spo2": encounter.spo2,
            "temperature_f": encounter.temperature_f,
            "pain_level": encounter.pain_level,
            "respiratory_rate": encounter.respiratory_rate,
            "gcs_score": encounter.gcs_score
        }

        # 5. Detect Red Flags
        red_flags = self.red_flag_service.detect_red_flags(
            encounter_vitals=vitals_dict,
            intake_summary=intake_summary,
            chief_complaint=encounter.chief_complaint
        )

        # 6. Compute Severity
        severity_result = self.severity_service.compute_severity(
            encounter_vitals=vitals_dict,
            intake_summary=intake_summary,
            red_flags=red_flags,
            esi_level=encounter.esi_level
        )

        # 7. Fetch prior encounters for longitudinal context
        prior_res = await self.db.execute(
            select(Encounter)
            .where(Encounter.patient_id == patient.id, Encounter.id != encounter_id)
            .order_by(Encounter.arrival_time.desc())
        )
        prior_encounters = [
            {
                "id": pe.id,
                "arrival_time": pe.arrival_time.isoformat() if pe.arrival_time else None,
                "chief_complaint": pe.chief_complaint,
                "status": pe.status
            }
            for pe in prior_res.scalars().all()
        ]

        # 8. Assemble structured summary
        patient_data = {
            "id": patient.id,
            "name": f"{patient.first_name} {patient.last_name}",
            "allergies": patient.allergies or [],
            "chronic_conditions": patient.chronic_conditions or []
        }
        encounter_data = {
            "id": encounter.id,
            "chief_complaint": encounter.chief_complaint,
            "patient_status": encounter.patient_status,
            "current_department_id": encounter.current_department_id,
            "current_bed_id": encounter.current_bed_id,
            "esi_level": encounter.esi_level,
            "vitals": vitals_dict,
            "arrival_time": encounter.arrival_time.isoformat() if encounter.arrival_time else None,
            "triage_time": encounter.triage_time.isoformat() if encounter.triage_time else None,
            "doctor_assigned_time": encounter.doctor_assigned_time.isoformat() if encounter.doctor_assigned_time else None
        }

        generated_summary = self.summary_service.generate_summary(
            patient_data=patient_data,
            encounter_data=encounter_data,
            intake_summary=intake_summary,
            severity_assessment=severity_result,
            red_flags=red_flags,
            prior_encounters=prior_encounters
        )

        # 9. Upsert ClinicalAssessment entity
        asm_res = await self.db.execute(
            select(ClinicalAssessment).where(ClinicalAssessment.encounter_id == encounter_id).with_for_update()
        )
        assessment = asm_res.scalars().first()

        if assessment:
            assessment.severity = severity_result["severity"]
            assessment.score = severity_result["score"]
            assessment.requires_priority_attention = severity_result["requires_priority_attention"]
            assessment.priority_reason = severity_result["priority_reason"]
            assessment.red_flags = red_flags
            assessment.reasons = severity_result["reasons"]
            assessment.supporting_factors = severity_result["supporting_factors"]
            assessment.missing_information = severity_result["missing_information"]
            assessment.generated_summary = generated_summary
            assessment.generated_at = datetime.utcnow()
            assessment.generated_by = actor_id
        else:
            assessment = ClinicalAssessment(
                encounter_id=encounter_id,
                intake_session_id=intake_session.id if intake_session else None,
                patient_id=patient.id,
                severity=severity_result["severity"],
                score=severity_result["score"],
                requires_priority_attention=severity_result["requires_priority_attention"],
                priority_reason=severity_result["priority_reason"],
                red_flags=red_flags,
                reasons=severity_result["reasons"],
                supporting_factors=severity_result["supporting_factors"],
                missing_information=severity_result["missing_information"],
                generated_summary=generated_summary,
                generated_at=datetime.utcnow(),
                generated_by=actor_id,
                version="1.0.0"
            )
            self.db.add(assessment)

        # 10. Audit Log
        audit = AuditLog(
            entity_type="clinical_assessment",
            entity_id=encounter_id,
            field_changed="assessment_computation",
            old_value=None,
            new_value=severity_result["severity"],
            changed_by=actor_id,
            change_reason=f"Clinical intelligence computed: severity {severity_result['severity']} (Score: {severity_result['score']})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(assessment)
        logger.info(f"Clinical assessment generated for encounter {encounter_id}: {assessment.severity} (Priority: {assessment.requires_priority_attention})")
        return assessment

    async def get_assessment(self, encounter_id: str) -> ClinicalAssessment:
        """Fetch existing clinical assessment or generate on demand."""
        res = await self.db.execute(
            select(ClinicalAssessment).where(ClinicalAssessment.encounter_id == encounter_id)
        )
        assessment = res.scalars().first()
        if not assessment:
            assessment = await self.analyze_encounter(encounter_id)
        return assessment

    async def get_severity(self, encounter_id: str) -> Dict[str, Any]:
        """Fetch severity breakdown for an encounter."""
        assessment = await self.get_assessment(encounter_id)
        return {
            "encounter_id": encounter_id,
            "severity": assessment.severity,
            "score": assessment.score,
            "requires_priority_attention": assessment.requires_priority_attention,
            "priority_reason": assessment.priority_reason,
            "reasons": assessment.reasons or [],
            "supporting_factors": assessment.supporting_factors or [],
            "missing_information": assessment.missing_information or [],
            "generated_at": assessment.generated_at
        }

    async def get_red_flags(self, encounter_id: str) -> List[Dict[str, Any]]:
        """Fetch detected red flags for an encounter."""
        assessment = await self.get_assessment(encounter_id)
        return assessment.red_flags or []

    async def get_summary(self, encounter_id: str) -> Dict[str, Any]:
        """Fetch structured doctor-ready clinical summary for an encounter."""
        assessment = await self.get_assessment(encounter_id)
        return assessment.generated_summary or {}
