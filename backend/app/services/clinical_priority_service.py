import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.priority import ClinicalPriorityRecommendation
from app.models.agent import AuditLog
from app.services.clinical_intelligence_service import ClinicalIntelligenceService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

VALID_PRIORITY_LEVELS = {"CRITICAL", "HIGH", "MODERATE", "ROUTINE"}
VALID_ROUTES = {
    "EMERGENCY_TRIAGE",
    "IMMEDIATE_DOCTOR_REVIEW",
    "NURSE_TRIAGE",
    "STANDARD_OPD_QUEUE",
    "OBSERVATION",
    "DEPARTMENT_REVIEW"
}

PRIORITY_MAP_TO_ENCOUNTER_NUM = {
    "CRITICAL": 1,
    "HIGH": 2,
    "MODERATE": 3,
    "ROUTINE": 4
}

CRITICAL_FLAG_CODES = {
    "RF_CRITICAL_HYPOXIA",
    "RF_HYPERTENSIVE_CRISIS",
    "RF_HYPOTENSION",
    "RF_SEVERE_BRADYCARDIA",
    "RF_SEVERE_TACHYPNEA",
    "RF_SEVERE_BRADYPNEA",
    "RF_ALTERED_GCS",
    "RF_ACUTE_HEMORRHAGE",
    "RF_ANAPHYLACTIC_SUSPICION",
    "RF_RESPIRATORY_DISTRESS"
}


class ClinicalPriorityService:
    """
    Domain service for deterministic clinical priority classification and operational routing recommendations.
    Synthesizes clinical assessments, red-flag telemetry, and hospital operational constraints with
    physician acknowledgement and override controls.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.intelligence_service = ClinicalIntelligenceService(db)

    async def evaluate_priority(
        self,
        encounter_id: str,
        actor_id: str = "SYSTEM"
    ) -> ClinicalPriorityRecommendation:
        """
        Evaluate and persist deterministic clinical priority and routing recommendation for an encounter.
        """
        # 1. Fetch encounter with lock
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

        # 2. Obtain Clinical Assessment
        assessment = await self.intelligence_service.get_assessment(encounter_id)
        red_flags = assessment.red_flags or []
        severity = assessment.severity
        score = assessment.score
        requires_priority = assessment.requires_priority_attention

        reasons: List[str] = []
        supporting_factors: List[str] = list(assessment.supporting_factors or [])

        # ─── 3. Deterministic Priority & Routing Classification ─────────────
        has_critical_flags = any(rf.get("code") in CRITICAL_FLAG_CODES for rf in red_flags)
        is_chest_severe = any(rf.get("code") == "RF_CHEST_COMPLAINT" for rf in red_flags) and (encounter.pain_level or 0) >= 8

        if has_critical_flags or is_chest_severe or encounter.esi_level == 1:
            priority_level = "CRITICAL"
            route = "EMERGENCY_TRIAGE"
            if has_critical_flags:
                crit_names = [rf["reason"] for rf in red_flags if rf.get("code") in CRITICAL_FLAG_CODES]
                reasons.append(f"Critical physiological indicator detected: {'; '.join(crit_names)}")
            if is_chest_severe:
                reasons.append("Acute chest pain with severe pain intensity (>= 8/10)")
            if encounter.esi_level == 1:
                reasons.append("Emergency Severity Index (ESI) Level 1 status")
        elif severity == "HIGH" or requires_priority or encounter.esi_level == 2 or (encounter.pain_level or 0) >= 8 or len(red_flags) >= 2:
            priority_level = "HIGH"
            route = "IMMEDIATE_DOCTOR_REVIEW"
            if severity == "HIGH":
                reasons.append(f"HIGH clinical assessment severity (Acuity score: {score})")
            if requires_priority:
                reasons.append(f"Priority attention flag: {assessment.priority_reason or 'Clinical urgency'}")
            if encounter.esi_level == 2:
                reasons.append("Emergency Severity Index (ESI) Level 2 emergent status")
            if (encounter.pain_level or 0) >= 8:
                reasons.append(f"Severe reported pain ({encounter.pain_level}/10)")
        elif severity == "MEDIUM" or (encounter.pain_level or 0) >= 5 or len(red_flags) == 1:
            priority_level = "MODERATE"
            route = "NURSE_TRIAGE" if not encounter.triage_time else "DEPARTMENT_REVIEW"
            reasons.append(f"MODERATE clinical severity (Acuity score: {score})")
            if (encounter.pain_level or 0) >= 5:
                reasons.append(f"Moderate reported pain ({encounter.pain_level}/10)")
        else:
            priority_level = "ROUTINE"
            route = "STANDARD_OPD_QUEUE"
            reasons.append("Stable physiological vitals and mild presenting complaints")

        # 4. Upsert ClinicalPriorityRecommendation
        rec_res = await self.db.execute(
            select(ClinicalPriorityRecommendation)
            .where(ClinicalPriorityRecommendation.encounter_id == encounter_id)
            .with_for_update()
        )
        rec = rec_res.scalars().first()

        if rec:
            rec.assessment_id = assessment.id
            rec.priority_level = priority_level
            rec.route = route
            rec.score = score
            rec.requires_priority_attention = requires_priority or (priority_level in ["CRITICAL", "HIGH"])
            rec.reasons = reasons
            rec.supporting_factors = supporting_factors
            rec.red_flags = red_flags
            rec.missing_information = assessment.missing_information or []
            rec.status = "GENERATED"
            rec.generated_by = actor_id
            rec.updated_at = utc_now()
        else:
            rec = ClinicalPriorityRecommendation(
                encounter_id=encounter_id,
                patient_id=encounter.patient_id,
                assessment_id=assessment.id,
                priority_level=priority_level,
                route=route,
                score=score,
                requires_priority_attention=requires_priority or (priority_level in ["CRITICAL", "HIGH"]),
                reasons=reasons,
                supporting_factors=supporting_factors,
                red_flags=red_flags,
                missing_information=assessment.missing_information or [],
                status="GENERATED",
                generated_by=actor_id,
                created_at=utc_now(),
                updated_at=utc_now(),
                version="1.0.0"
            )
            self.db.add(rec)

        # 5. Synchronize Encounter Priority Field
        encounter.priority = PRIORITY_MAP_TO_ENCOUNTER_NUM.get(priority_level, 3)

        # 6. Audit Log
        audit = AuditLog(
            entity_type="clinical_priority",
            entity_id=encounter_id,
            field_changed="priority_recommendation_generated",
            old_value=None,
            new_value=f"{priority_level} -> {route}",
            changed_by=actor_id,
            change_reason=f"Priority recommendation generated: {priority_level} via {route} (Score: {score})"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(rec)
        logger.info(f"Clinical priority recommendation generated for encounter {encounter_id}: {priority_level} -> {route}")
        return rec

    async def get_recommendation(self, encounter_id: str) -> ClinicalPriorityRecommendation:
        """Fetch existing priority recommendation or generate on demand."""
        res = await self.db.execute(
            select(ClinicalPriorityRecommendation).where(ClinicalPriorityRecommendation.encounter_id == encounter_id)
        )
        rec = res.scalars().first()
        if not rec:
            rec = await self.evaluate_priority(encounter_id)
        return rec

    async def acknowledge_recommendation(
        self,
        encounter_id: str,
        actor_id: str,
        notes: Optional[str] = None
    ) -> ClinicalPriorityRecommendation:
        """Acknowledge a priority routing recommendation by attending staff."""
        res = await self.db.execute(
            select(ClinicalPriorityRecommendation)
            .where(ClinicalPriorityRecommendation.encounter_id == encounter_id)
            .with_for_update()
        )
        rec = res.scalars().first()
        if not rec:
            raise HTTPException(status_code=404, detail=f"Priority recommendation for encounter {encounter_id} not found")

        if rec.status == "OVERRIDDEN":
            raise HTTPException(status_code=400, detail=f"Cannot acknowledge an already OVERRIDDEN recommendation")

        rec.status = "ACKNOWLEDGED"
        rec.acknowledged_by = actor_id
        rec.acknowledged_at = utc_now()
        rec.acknowledgement_notes = notes
        rec.updated_at = utc_now()

        audit = AuditLog(
            entity_type="clinical_priority",
            entity_id=encounter_id,
            field_changed="priority_recommendation_acknowledged",
            old_value="GENERATED",
            new_value="ACKNOWLEDGED",
            changed_by=actor_id,
            change_reason=f"Priority recommendation acknowledged by {actor_id}" + (f": {notes}" if notes else "")
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(rec)
        logger.info(f"Priority recommendation {rec.id} acknowledged by {actor_id}")
        return rec

    async def override_recommendation(
        self,
        encounter_id: str,
        actor_id: str,
        override_priority: str,
        override_route: str,
        override_reason: str
    ) -> ClinicalPriorityRecommendation:
        """Physician manual override of priority level and routing with mandatory clinical rationale."""
        res = await self.db.execute(
            select(ClinicalPriorityRecommendation)
            .where(ClinicalPriorityRecommendation.encounter_id == encounter_id)
            .with_for_update()
        )
        rec = res.scalars().first()
        if not rec:
            raise HTTPException(status_code=404, detail=f"Priority recommendation for encounter {encounter_id} not found")

        p_clean = override_priority.upper().strip()
        if p_clean not in VALID_PRIORITY_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid priority level '{override_priority}'. Allowed: {sorted(VALID_PRIORITY_LEVELS)}")

        r_clean = override_route.upper().strip()
        if r_clean not in VALID_ROUTES:
            raise HTTPException(status_code=400, detail=f"Invalid routing destination '{override_route}'. Allowed: {sorted(VALID_ROUTES)}")

        if not override_reason or len(override_reason.strip()) < 3:
            raise HTTPException(status_code=400, detail="Override reason must be provided with at least 3 characters")

        old_desc = f"{rec.priority_level} -> {rec.route}"

        rec.status = "OVERRIDDEN"
        rec.overridden_by = actor_id
        rec.overridden_at = utc_now()
        rec.override_priority_level = p_clean
        rec.override_route = r_clean
        rec.override_reason = override_reason.strip()
        rec.updated_at = utc_now()

        # Update encounter priority to match override
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        enc = enc_res.scalars().first()
        if enc:
            enc.priority = PRIORITY_MAP_TO_ENCOUNTER_NUM.get(p_clean, 3)

        audit = AuditLog(
            entity_type="clinical_priority",
            entity_id=encounter_id,
            field_changed="priority_recommendation_overridden",
            old_value=old_desc,
            new_value=f"{p_clean} -> {r_clean}",
            changed_by=actor_id,
            change_reason=f"Priority overridden by {actor_id}: {override_reason.strip()}"
        )
        self.db.add(audit)

        await self.db.commit()
        await self.db.refresh(rec)
        logger.info(f"Priority recommendation {rec.id} overridden by {actor_id}: {p_clean} -> {r_clean}")
        return rec
