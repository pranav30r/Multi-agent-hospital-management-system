"""
Autonomous Emergency & Rapid Response Escalation Agent.
Evaluates acute physiological red flags, hemodynamic collapse indicators,
and facility-wide disaster declarations to determine emergency escalation triggers
without mutating hospital state directly.
"""

import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Encounter
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class EmergencyEscalationAgent(BaseAgent):
    """
    Autonomous Emergency & Rapid Response Escalation Agent.
    Evaluates acute physiological red flags, hemodynamic collapse indicators,
    and facility-wide disaster declarations to determine emergency escalation triggers
    without mutating hospital state directly.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db=db, agent_id="emergency_escalation_agent", name="Emergency & Rapid Response Escalation Agent")
        from app.services.emergency_service import EmergencyService
        self.emergency_service = EmergencyService(db)

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Evaluates acute deterioration risk and facility-wide active emergency state.
        """
        red_flags = triage_output.get("red_flags") or []
        severity = triage_output.get("severity", "LOW")
        score = triage_output.get("score", 0.0)
        esi = triage_output.get("esi_level", 5)

        # Check for active facility-wide emergencies
        active_emergencies = await self.emergency_service.list_active_emergencies(tenant_id=tenant_id)
        active_event_types = [e.event_type for e in active_emergencies]

        # Evaluate clinical escalation triggers
        critical_rf_codes = [rf.get("code") for rf in red_flags if rf.get("severity") == "HIGH"]
        is_hemodynamic_collapse = (
            (encounter.bp_systolic is not None and encounter.bp_systolic <= 85) or
            (encounter.spo2 is not None and encounter.spo2 <= 88) or
            (encounter.gcs_score is not None and encounter.gcs_score <= 10)
        )

        escalation_required = False
        emergency_level = "STANDARD_MONITORING"
        urgency = "ROUTINE"
        recommended_actions = []
        reasons = []

        if esi == 1 or is_hemodynamic_collapse or len(critical_rf_codes) >= 2 or severity == "CRITICAL":
            escalation_required = True
            emergency_level = "CRITICAL_CODE_BLUE" if (encounter.gcs_score and encounter.gcs_score <= 8) else "RAPID_RESPONSE_STAT"
            urgency = "IMMEDIATE"
            recommended_actions.append("ACTIVATE_RAPID_RESPONSE_TEAM")
            recommended_actions.append("STAT_ICU_BED_RESERVATION")
            recommended_actions.append("CONTINUOUS_CARDIAC_MONITORING")
            reasons.append(f"Acute physiological decompensation detected (Severity: {severity}, Score: {score:.1f})")
            if is_hemodynamic_collapse:
                reasons.append("Severe hemodynamic collapse criteria met (Critically low BP/SpO2/GCS)")
        elif esi == 2 or len(red_flags) >= 1 or severity == "HIGH":
            escalation_required = True
            emergency_level = "SPECIALIST_URGENT"
            urgency = "URGENT"
            recommended_actions.append("ATTENDING_PHYSICIAN_STAT_REVIEW")
            recommended_actions.append("PRIORITY_EMERGENCY_BAY_PLACEMENT")
            reasons.append(f"High acuity clinical presentation with {len(red_flags)} active red flag(s)")
        elif active_event_types:
            escalation_required = True
            emergency_level = "FACILITY_SURGE_PROTOCOL"
            urgency = "ELEVATED"
            recommended_actions.append("APPLY_DISASTER_TRIAGE_OVERFLOW_PROTOCOL")
            reasons.append(f"Hospital-wide emergency active: {', '.join(active_event_types)}")
        else:
            escalation_required = False
            emergency_level = "STANDARD_MONITORING"
            urgency = "STANDARD"
            recommended_actions.append("ROUTINE_TRIAGE_MONITORING")
            reasons.append("Vital signs and telemetry within stable non-emergency thresholds")

        rationale = (
            f"Emergency Escalation Analysis: Level '{emergency_level}' (Urgency: {urgency}, Escalation: {escalation_required}). "
            f"Reasons: {'; '.join(reasons)}."
        )

        return {
            "agent_id": "emergency_escalation_agent",
            "status": "COMPLETED",
            "escalation_required": escalation_required,
            "emergency_level": emergency_level,
            "urgency": urgency,
            "active_facility_emergencies": active_event_types,
            "critical_red_flags_count": len(critical_rf_codes),
            "recommended_emergency_actions": recommended_actions,
            "reasons": reasons,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def evaluate_counter_proposal(
        self,
        counter_proposal: Dict[str, Any],
        triage_output: Dict[str, Any],
        encounter: Encounter
    ) -> Dict[str, Any]:
        """
        Evaluates a bed counter-proposal against the patient's acute physiological risk.
        Emits ESCALATION if hemodynamic decompensation forbids holding/step-down, or ACCEPT if viable.
        """
        esi = triage_output.get("esi_level", 3)
        bp_sys = encounter.bp_systolic or 120
        spo2 = encounter.spo2 or 98
        gcs = encounter.gcs_score or 15

        # Critical threshold: extreme shock, severe hypoxia, or coma cannot accept holding
        severe_decompensation = (bp_sys < 75 or spo2 < 85 or gcs < 9 or esi == 1)

        if severe_decompensation:
            decision = "ESCALATION"
            rationale = (
                f"Counter-proposal ({counter_proposal.get('proposed_bed_type')}) rejected: Acute physiological instability "
                f"(BP {bp_sys}, SpO2 {spo2}%, GCS {gcs}). Immediate direct ICU transfer or Rapid Response resuscitation required."
            )
            escalation_actions = ["ACTIVATE_RAPID_RESPONSE_TEAM", "STAT_ICU_BED_RESERVATION"]
        else:
            decision = "ACCEPT"
            rationale = (
                f"Counter-proposal ({counter_proposal.get('proposed_bed_type')}) accepted conditionally with "
                f"continuous physiological telemetry and attending physician monitoring."
            )
            escalation_actions = ["MONITOR_CONTINUOUS_TELEMETRY", "ATTENDING_CONSULT_WITHIN_30MIN"]

        return {
            "agent_id": "emergency_escalation_agent",
            "message_type": decision,
            "counter_proposal_decision": decision,
            "rationale": rationale,
            "required_actions": escalation_actions,
            "timestamp": utc_now_iso()
        }
