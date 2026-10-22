"""
Standalone Risk & Governance Evaluation Engine.
Authoritative component for determining operational risk tiers (LOW, MEDIUM, HIGH),
action classifications, confidence scoring, and Human-in-the-Loop (HITL) approval gating.
Decoupled from coordinator orchestration to enable deterministic, policy-driven clinical governance.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RiskTier:
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GovernanceActionType:
    ICU_BED_ALLOCATION = "ICU_BED_ALLOCATION_RECOMMENDATION"
    SPECIALIST_CONSULT = "SPECIALIST_CONSULT_RECOMMENDATION"
    OBSERVATION_ADMISSION = "OBSERVATION_ADMISSION_RECOMMENDATION"
    STANDARD_OPD = "STANDARD_OPD_ROUTING"


@dataclass(frozen=True)
class RiskPolicyConfig:
    """
    Configurable clinical governance policy thresholds and gating rules.
    Preserves existing hospital safety invariants and clinical escalation policies.
    """
    # High Risk (ICU Allocation / STAT Interventions)
    high_risk_priorities: Tuple[str, ...] = ("CRITICAL",)
    high_risk_severities: Tuple[str, ...] = ("CRITICAL", "HIGH")
    high_risk_care_levels: Tuple[str, ...] = ("ICU",)
    high_risk_min_red_flags: int = 2
    high_risk_esi_levels: Tuple[int, ...] = (1,)

    # Medium Risk (Specialist Consult / Urgent Care)
    medium_risk_priorities: Tuple[str, ...] = ("HIGH",)
    medium_risk_severities: Tuple[str, ...] = ("HIGH", "MODERATE")
    medium_risk_care_levels: Tuple[str, ...] = ("EMERGENCY",)
    medium_risk_min_red_flags: int = 1
    medium_risk_esi_levels: Tuple[int, ...] = (2,)

    # Low Risk - Observation Ward (Requires Human Approval)
    low_obs_priorities: Tuple[str, ...] = ("MODERATE",)
    low_obs_care_levels: Tuple[str, ...] = ("GENERAL",)
    low_obs_excluded_priorities: Tuple[str, ...] = ("ROUTINE", "LOW")

    # Hemodynamic collapse thresholds (matching emergency agent)
    hemodynamic_sbp_collapse: float = 85.0
    hemodynamic_spo2_collapse: float = 88.0
    hemodynamic_gcs_collapse: float = 10.0

    # Escalation statuses
    unresolved_escalation_statuses: Tuple[str, ...] = ("UNRESOLVED_ESCALATED", "ESCALATED")

    # Confidence scores
    confidence_high: float = 0.94
    confidence_medium: float = 0.88
    confidence_low_obs: float = 0.82
    confidence_low_opd: float = 0.90


@dataclass
class RiskEvaluationResult:
    """
    Authoritative result of a risk and governance evaluation.
    Provides attribute access, item access, and serialization methods.
    """
    risk_level: str
    action_type: str
    requires_human_approval: bool
    confidence: float
    reasoning: str
    proposed_action: Dict[str, Any]
    risk_score: float
    risk_factors: List[str] = field(default_factory=list)
    policy_tier: str = "DEFAULT"

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "action_type": self.action_type,
            "requires_human_approval": self.requires_human_approval,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "proposed_action": self.proposed_action,
            "risk_score": self.risk_score,
            "risk_factors": list(self.risk_factors),
            "policy_tier": self.policy_tier
        }


class RiskEngine:
    """
    Autonomous Risk & Governance Policy Engine.
    Evaluates multi-agent assessment signals, clinical acuity indicators,
    hemodynamic stability, emergency escalation state, and resource conflict triggers
    to produce deterministic risk tiers and human-in-the-loop approval requirements.
    """

    def __init__(self, policy: Optional[RiskPolicyConfig] = None):
        self.policy = policy or RiskPolicyConfig()

    @staticmethod
    def _extract_val(obj: Any, field_name: str, default: Any = None) -> Any:
        """Helper to extract a field whether obj is a dict, an ORM model, or None."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(field_name, default)
        return getattr(obj, field_name, default)

    def evaluate(
        self,
        triage_output: Optional[Dict[str, Any]] = None,
        emergency_output: Optional[Dict[str, Any]] = None,
        selected_plan: Optional[Dict[str, Any]] = None,
        encounter: Optional[Any] = None,
        patient: Optional[Any] = None,
        negotiation_status: str = "NONE",
        active_conflicts: Optional[List[Dict[str, Any]]] = None,
        bed_output: Optional[Dict[str, Any]] = None,
        staff_output: Optional[Dict[str, Any]] = None,
    ) -> RiskEvaluationResult:
        """
        Evaluates operational and clinical risk from multi-agent inputs.
        Determines risk level (HIGH, MEDIUM, LOW), action recommendation type,
        and whether human review is required before action execution.
        """
        triage = triage_output or {}
        emergency = emergency_output or {}
        plan = selected_plan or {}

        care_level = str(triage.get("recommended_care_level") or "").upper()
        severity = str(triage.get("severity") or "LOW").upper()
        priority_level = str(triage.get("priority_level") or "ROUTINE").upper()
        red_flags_raw = triage.get("red_flags")
        red_flags_count = len(red_flags_raw) if isinstance(red_flags_raw, list) else 0
        esi_level = triage.get("esi_level")

        # Emergency & Escalation signals
        is_escalated = bool(emergency.get("escalation_required")) or (
            negotiation_status in self.policy.unresolved_escalation_statuses
        )
        emergency_level = emergency.get("emergency_level")

        # Hemodynamic collapse indicators from encounter vitals
        bp_sys = self._extract_val(encounter, "bp_systolic")
        spo2 = self._extract_val(encounter, "spo2")
        gcs = self._extract_val(encounter, "gcs_score")
        encounter_id = self._extract_val(encounter, "id")
        patient_id = self._extract_val(patient, "id")

        is_hemodynamic_collapse = False
        collapse_reasons = []
        if bp_sys is not None:
            try:
                if float(bp_sys) <= self.policy.hemodynamic_sbp_collapse:
                    is_hemodynamic_collapse = True
                    collapse_reasons.append(
                        f"Hypotension/Shock (SBP={bp_sys} <= {self.policy.hemodynamic_sbp_collapse})"
                    )
            except (ValueError, TypeError):
                pass

        if spo2 is not None:
            try:
                if float(spo2) <= self.policy.hemodynamic_spo2_collapse:
                    is_hemodynamic_collapse = True
                    collapse_reasons.append(
                        f"Severe Hypoxia (SpO2={spo2}% <= {self.policy.hemodynamic_spo2_collapse}%)"
                    )
            except (ValueError, TypeError):
                pass

        if gcs is not None:
            try:
                if float(gcs) <= self.policy.hemodynamic_gcs_collapse:
                    is_hemodynamic_collapse = True
                    collapse_reasons.append(
                        f"Altered Consciousness/Coma (GCS={gcs} <= {self.policy.hemodynamic_gcs_collapse})"
                    )
            except (ValueError, TypeError):
                pass

        # Track risk factors for provenance
        risk_factors: List[str] = []
        if priority_level in self.policy.high_risk_priorities:
            risk_factors.append(f"Critical priority level: {priority_level}")
        if severity in self.policy.high_risk_severities:
            risk_factors.append(f"Critical/High severity tier: {severity}")
        if red_flags_count >= self.policy.high_risk_min_red_flags:
            risk_factors.append(f"Multiple clinical red flags ({red_flags_count})")
        if care_level in self.policy.high_risk_care_levels:
            risk_factors.append("ICU care tier indicated")
        if is_escalated:
            risk_factors.append(
                f"Emergency escalation active (Level: {emergency_level}, Negotiation: {negotiation_status})"
            )
        if esi_level is not None and esi_level in self.policy.high_risk_esi_levels:
            risk_factors.append("Acuity ESI 1 (Immediate resuscitation)")
        if is_hemodynamic_collapse:
            risk_factors.extend(collapse_reasons)

        # -------------------------------------------------------------
        # TIER 1: HIGH RISK (ICU Bed Allocation / Resuscitation)
        # -------------------------------------------------------------
        is_high_risk = (
            priority_level in self.policy.high_risk_priorities or
            severity in self.policy.high_risk_severities or
            red_flags_count >= self.policy.high_risk_min_red_flags or
            care_level in self.policy.high_risk_care_levels or
            is_escalated or
            (esi_level is not None and esi_level in self.policy.high_risk_esi_levels) or
            is_hemodynamic_collapse
        )

        if is_high_risk:
            action_type = GovernanceActionType.ICU_BED_ALLOCATION
            risk_level = RiskTier.HIGH
            requires_human_approval = True
            confidence = self.policy.confidence_high
            reasoning = (
                f"Critical physiological decompensation detected (Severity: {severity}, "
                f"Priority: {priority_level}, Red Flags: {red_flags_count}, Emergency Level: {emergency_level}, "
                f"Negotiation Status: {negotiation_status}). "
                f"Immediate ICU bed allocation and continuous telemetry monitoring recommended."
            )
            proposed_action = {
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": plan.get("target_bed_id"),
                "target_department_id": plan.get("target_department_id"),
                "assigned_doctor_id": plan.get("assigned_doctor_id"),
                "assigned_nurse_id": plan.get("assigned_nurse_id"),
                "emergency_actions": emergency.get("recommended_emergency_actions", []),
                "encounter_id": encounter_id,
                "patient_id": patient_id,
                "priority": "CRITICAL"
            }
            risk_score = 0.95

            return RiskEvaluationResult(
                risk_level=risk_level,
                action_type=action_type,
                requires_human_approval=requires_human_approval,
                confidence=confidence,
                reasoning=reasoning,
                proposed_action=proposed_action,
                risk_score=risk_score,
                risk_factors=risk_factors,
                policy_tier="HIGH_ACUITY_CRITICAL"
            )

        # -------------------------------------------------------------
        # TIER 2: MEDIUM RISK (Specialist Consult Recommendation)
        # -------------------------------------------------------------
        is_medium_risk = (
            priority_level in self.policy.medium_risk_priorities or
            red_flags_count >= self.policy.medium_risk_min_red_flags or
            care_level in self.policy.medium_risk_care_levels or
            (esi_level is not None and esi_level in self.policy.medium_risk_esi_levels)
        )

        if is_medium_risk:
            action_type = GovernanceActionType.SPECIALIST_CONSULT
            risk_level = RiskTier.MEDIUM
            requires_human_approval = True
            confidence = self.policy.confidence_medium
            reasoning = (
                f"Elevated clinical acuity identified (Severity: {severity}, Priority: {priority_level}, Negotiation: {negotiation_status}). "
                f"Immediate attending emergency physician consultation recommended."
            )
            proposed_action = {
                "action": "ORDER_CONSULT",
                "specialty": "EMERGENCY_MEDICINE",
                "target_bed_id": plan.get("target_bed_id"),
                "encounter_id": encounter_id,
                "patient_id": patient_id,
                "priority": "HIGH"
            }
            if priority_level in self.policy.medium_risk_priorities:
                risk_factors.append(f"Elevated priority level: {priority_level}")
            if red_flags_count == 1:
                risk_factors.append("Single active red flag identified")
            if care_level in self.policy.medium_risk_care_levels:
                risk_factors.append(f"Care level requires emergency department bay: {care_level}")
            if esi_level == 2:
                risk_factors.append("Acuity ESI 2 (Emergent)")
            risk_score = 0.65

            return RiskEvaluationResult(
                risk_level=risk_level,
                action_type=action_type,
                requires_human_approval=requires_human_approval,
                confidence=confidence,
                reasoning=reasoning,
                proposed_action=proposed_action,
                risk_score=risk_score,
                risk_factors=risk_factors,
                policy_tier="MEDIUM_ACUITY_ELEVATED"
            )

        # -------------------------------------------------------------
        # TIER 3A: LOW RISK - OBSERVATION ADMISSION (Requires HITL Approval)
        # -------------------------------------------------------------
        is_low_observation = (
            priority_level in self.policy.low_obs_priorities or
            (care_level in self.policy.low_obs_care_levels and priority_level not in self.policy.low_obs_excluded_priorities)
        )

        if is_low_observation:
            action_type = GovernanceActionType.OBSERVATION_ADMISSION
            risk_level = RiskTier.LOW
            requires_human_approval = True
            confidence = self.policy.confidence_low_obs
            reasoning = "Moderate clinical presentation with stable vital signs. Step-down observation ward admission recommended."
            proposed_action = {
                "action": "OBSERVE",
                "department_code": plan.get("target_department_id") or "DEP-WA",
                "target_bed_id": plan.get("target_bed_id"),
                "encounter_id": encounter_id,
                "patient_id": patient_id,
                "priority": "MODERATE"
            }
            risk_factors.append("Moderate acuity presentation requiring inpatient clinical observation")
            risk_score = 0.35

            return RiskEvaluationResult(
                risk_level=risk_level,
                action_type=action_type,
                requires_human_approval=requires_human_approval,
                confidence=confidence,
                reasoning=reasoning,
                proposed_action=proposed_action,
                risk_score=risk_score,
                risk_factors=risk_factors,
                policy_tier="LOW_ACUITY_OBSERVATION"
            )

        # -------------------------------------------------------------
        # TIER 3B: LOW RISK - STANDARD OPD ROUTING (Autonomous / No HITL Approval)
        # -------------------------------------------------------------
        action_type = GovernanceActionType.STANDARD_OPD
        risk_level = RiskTier.LOW
        requires_human_approval = False
        confidence = self.policy.confidence_low_opd
        reasoning = "Normal vital parameters without acute clinical red flags. Routed to standard outpatient consultation queue."
        proposed_action = {
            "action": "QUEUE_OPD",
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "priority": "ROUTINE"
        }
        risk_factors.append("Benign clinical parameters suitable for outpatient care")
        risk_score = 0.10

        return RiskEvaluationResult(
            risk_level=risk_level,
            action_type=action_type,
            requires_human_approval=requires_human_approval,
            confidence=confidence,
            reasoning=reasoning,
            proposed_action=proposed_action,
            risk_score=risk_score,
            risk_factors=risk_factors,
            policy_tier="LOW_ACUITY_ROUTINE"
        )
