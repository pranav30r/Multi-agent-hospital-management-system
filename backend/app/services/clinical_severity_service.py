import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

REQUIRED_VITAL_FIELDS = [
    ("heart_rate", "Heart Rate"),
    ("bp_systolic", "Systolic Blood Pressure"),
    ("bp_diastolic", "Diastolic Blood Pressure"),
    ("spo2", "Oxygen Saturation (SpO2)"),
    ("temperature_f", "Body Temperature"),
    ("pain_level", "Pain Level"),
    ("respiratory_rate", "Respiratory Rate"),
    ("gcs_score", "Glasgow Coma Scale (GCS)")
]


class ClinicalSeverityService:
    """
    Deterministic rule-based clinical severity classification and prioritization engine.
    Derives explainable severity signals (LOW, MEDIUM, HIGH) without AI hallucination or clinical diagnosis.
    """

    def compute_severity(
        self,
        encounter_vitals: Dict[str, Any],
        intake_summary: Optional[Dict[str, Any]] = None,
        red_flags: Optional[List[Dict[str, Any]]] = None,
        esi_level: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Synthesize clinical severity score, level, evidence reasons, supporting factors,
        and missing information from patient intake and encounter data.
        """
        flags = red_flags or []
        reasons: List[str] = []
        supporting_factors: List[str] = []
        missing_info: List[str] = []

        total_score: float = 0.0

        # ─── 1. Missing Information Audit ───────────────────────────────────
        for field_key, field_label in REQUIRED_VITAL_FIELDS:
            val = encounter_vitals.get(field_key)
            if field_key == "pain_level" and val is None and intake_summary and isinstance(intake_summary.get("pain"), dict):
                val = intake_summary["pain"].get("score")
            
            if val is None:
                missing_info.append(f"{field_label} ({field_key})")
            else:
                supporting_factors.append(f"{field_label}: {val}")

        # ─── 2. Evaluate Red Flags ──────────────────────────────────────────
        high_flags = [f for f in flags if f.get("severity") == "HIGH"]
        med_flags = [f for f in flags if f.get("severity") == "MEDIUM"]

        for hf in high_flags:
            total_score += 35.0
            reasons.append(f"[HIGH CRITICAL] {hf.get('reason')}")

        for mf in med_flags:
            total_score += 15.0
            reasons.append(f"[MEDIUM WARNING] {mf.get('reason')}")

        # ─── 3. Evaluate Pain Score ─────────────────────────────────────────
        pain_score = None
        if intake_summary and isinstance(intake_summary.get("pain"), dict):
            pain_score = intake_summary["pain"].get("score")
        if pain_score is None:
            pain_score = encounter_vitals.get("pain_level")

        if pain_score is not None:
            try:
                p_val = int(pain_score)
                if p_val >= 8:
                    total_score += 20.0
                    reasons.append(f"Severe reported pain level ({p_val}/10)")
                elif p_val >= 5:
                    total_score += 10.0
                    reasons.append(f"Moderate reported pain level ({p_val}/10)")
                elif p_val > 0:
                    total_score += 5.0
            except (ValueError, TypeError):
                pass

        # ─── 4. Evaluate ESI Triage Level ────────────────────────────────────
        if esi_level is not None:
            if esi_level == 1:
                total_score += 50.0
                reasons.append("Emergency Severity Index (ESI) Level 1: Immediate resuscitation priority")
            elif esi_level == 2:
                total_score += 30.0
                reasons.append("Emergency Severity Index (ESI) Level 2: Emergent high-risk condition")
            elif esi_level == 3:
                total_score += 10.0

        # ─── 5. Evaluate Chief Complaint & Symptoms ──────────────────────────
        if intake_summary:
            cc = intake_summary.get("chief_complaint")
            if cc:
                supporting_factors.append(f"Patient Reported Chief Complaint: '{cc}'")
            duration = intake_summary.get("duration")
            if duration:
                supporting_factors.append(f"Symptom Duration: {duration}")

        # ─── 6. Derive Severity Tier ────────────────────────────────────────
        # HIGH: Any High-severity red flag OR ESI <= 2 OR total_score >= 40
        if len(high_flags) > 0 or (esi_level and esi_level <= 2) or total_score >= 40.0:
            severity = "HIGH"
            requires_priority = True
            priority_reason = "; ".join([hf["reason"] for hf in high_flags]) if high_flags else f"High clinical acuity score ({total_score:.1f})"
        # MEDIUM: Moderate red flags OR pain >= 5 OR total_score >= 20
        elif len(med_flags) > 0 or (pain_score and int(pain_score or 0) >= 5) or total_score >= 20.0:
            severity = "MEDIUM"
            requires_priority = False
            priority_reason = None
        else:
            severity = "LOW"
            requires_priority = False
            priority_reason = None
            if not reasons:
                reasons.append("Stable physiological indicators and mild presenting complaints")

        return {
            "severity": severity,
            "score": round(total_score, 1),
            "reasons": reasons,
            "supporting_factors": supporting_factors,
            "missing_information": missing_info,
            "requires_priority_attention": requires_priority,
            "priority_reason": priority_reason
        }
