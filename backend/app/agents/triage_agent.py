"""
Autonomous Triage Decision Support Agent.
Evaluates patient symptoms, vitals, intake session, red flags, severity score,
and ESI priority tier to recommend clinical acuity and target care level.
"""

import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class TriageAgent(BaseAgent):
    """
    Autonomous Triage Decision Support Agent.
    Evaluates patient symptoms, vitals, intake session, red flags, severity score,
    and ESI priority tier to recommend clinical acuity and target care level.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db=db, agent_id="triage_agent", name="Triage Decision Support Agent")
        from app.services.clinical_intelligence_service import ClinicalIntelligenceService
        from app.services.clinical_priority_service import ClinicalPriorityService
        self.intelligence_service = ClinicalIntelligenceService(db)
        self.priority_service = ClinicalPriorityService(db)

    async def evaluate(
        self,
        encounter: Encounter,
        patient: Patient,
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Executes deterministic clinical triage analysis and emits structured assessment.
        """
        assessment = await self.intelligence_service.get_assessment(encounter.id)
        priority_rec = await self.priority_service.evaluate_priority(encounter.id, actor_id=actor_id)

        severity = assessment.severity or "LOW"
        score = float(assessment.score or 0.0)
        red_flags = assessment.red_flags or []
        priority_level = priority_rec.priority_level or "ROUTINE"

        # Derive ESI level from encounter or priority_level
        if encounter.esi_level:
            esi_level = encounter.esi_level
        elif priority_level == "CRITICAL":
            esi_level = 1
        elif priority_level == "HIGH":
            esi_level = 2
        elif priority_level == "MODERATE":
            esi_level = 3
        else:
            esi_level = 5

        # Determine target care tier based on clinical rules
        if esi_level == 1 or severity in ["CRITICAL", "HIGH"] or len(red_flags) >= 2:
            recommended_care_level = "ICU"
            clinical_urgency = "IMMEDIATE"
        elif esi_level == 2 or len(red_flags) == 1:
            recommended_care_level = "EMERGENCY"
            clinical_urgency = "URGENT"
        elif esi_level in [3, 4] or severity == "MODERATE":
            recommended_care_level = "GENERAL"
            clinical_urgency = "STANDARD"
        else:
            recommended_care_level = "OUTPATIENT"
            clinical_urgency = "ROUTINE"

        # Check for specialized equipment or telemetry requirements
        requires_telemetry = any(rf.get("source") in ["vitals.heart_rate", "vitals.spo2"] for rf in red_flags) or severity in ["CRITICAL", "HIGH"]
        requires_isolation = any("fever" in (encounter.chief_complaint or "").lower() and "rash" in (encounter.chief_complaint or "").lower() for _ in [1])
        requires_ventilator = esi_level == 1 and (
            (encounter.spo2 is not None and encounter.spo2 < 85)
            or (encounter.gcs_score is not None and encounter.gcs_score <= 8)
        )

        rationale = (
            f"Triage Assessment: ESI Level {esi_level} ({priority_level}), Severity: {severity} (Score: {score:.1f}), "
            f"Red Flags Detected: {len(red_flags)}. Care Level Target: {recommended_care_level}."
        )

        return {
            "agent_id": "triage_agent",
            "esi_level": esi_level,
            "priority_level": priority_level,
            "severity": severity,
            "score": score,
            "red_flags": red_flags,
            "recommended_care_level": recommended_care_level,
            "clinical_urgency": clinical_urgency,
            "requires_telemetry": requires_telemetry,
            "requires_isolation": requires_isolation,
            "requires_ventilator": requires_ventilator,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }
