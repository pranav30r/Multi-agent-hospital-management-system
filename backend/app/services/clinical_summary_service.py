import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)


class ClinicalSummaryService:
    """
    Deterministic clinical summary synthesis engine.
    Formats patient intake data, encounter telemetry, detected red flags, and derived severity
    into a structured doctor-facing clinical brief distinguishing Patient-Reported, Observed, and Derived sections.
    """

    def generate_summary(
        self,
        patient_data: Dict[str, Any],
        encounter_data: Dict[str, Any],
        intake_summary: Optional[Dict[str, Any]],
        severity_assessment: Dict[str, Any],
        red_flags: List[Dict[str, Any]],
        prior_encounters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Synthesize a structured clinical pre-consultation summary object for physician review.
        """
        intk = intake_summary or {}
        now_iso = utc_now_iso()

        # ─── 1. Patient-Reported Section ────────────────────────────────────
        patient_reported = {
            "chief_complaint": intk.get("chief_complaint") or encounter_data.get("chief_complaint") or "Not reported",
            "symptoms": intk.get("symptoms") or [],
            "duration": intk.get("duration") or "Unspecified duration",
            "pain": intk.get("pain") or {
                "present": encounter_data.get("vitals", {}).get("pain_level", 0) > 0,
                "score": encounter_data.get("vitals", {}).get("pain_level"),
                "location": "Unspecified"
            },
            "medications": intk.get("medications") or "None reported",
            "allergies": intk.get("allergies") or patient_data.get("allergies") or [],
            "past_medical_history": intk.get("past_medical_history") or patient_data.get("chronic_conditions") or "None recorded"
        }

        # ─── 2. Observed Clinical Telemetry ─────────────────────────────────
        vitals = encounter_data.get("vitals") or {}
        observed = {
            "patient_status": encounter_data.get("patient_status", "ACTIVE"),
            "department_id": encounter_data.get("current_department_id"),
            "bed_id": encounter_data.get("current_bed_id"),
            "esi_level": encounter_data.get("esi_level"),
            "vitals": {
                "heart_rate": vitals.get("heart_rate"),
                "blood_pressure": f"{vitals.get('bp_systolic')}/{vitals.get('bp_diastolic')}" if vitals.get("bp_systolic") is not None else None,
                "bp_systolic": vitals.get("bp_systolic"),
                "bp_diastolic": vitals.get("bp_diastolic"),
                "spo2": vitals.get("spo2"),
                "temperature_f": vitals.get("temperature_f"),
                "respiratory_rate": vitals.get("respiratory_rate"),
                "gcs_score": vitals.get("gcs_score"),
                "pain_level": vitals.get("pain_level")
            },
            "timestamps": {
                "arrival_time": encounter_data.get("arrival_time"),
                "triage_time": encounter_data.get("triage_time"),
                "doctor_assigned_time": encounter_data.get("doctor_assigned_time")
            }
        }

        # ─── 3. Derived Clinical Signals ────────────────────────────────────
        derived = {
            "severity": severity_assessment.get("severity", "LOW"),
            "score": severity_assessment.get("score", 0.0),
            "requires_priority_attention": severity_assessment.get("requires_priority_attention", False),
            "priority_reason": severity_assessment.get("priority_reason"),
            "reasons": severity_assessment.get("reasons", []),
            "red_flags": red_flags,
            "supporting_factors": severity_assessment.get("supporting_factors", []),
            "missing_information": severity_assessment.get("missing_information", [])
        }

        # ─── 4. Longitudinal Prior Visits ───────────────────────────────────
        longitudinal = {
            "total_prior_visits": len(prior_encounters or []),
            "recent_visits": [
                {
                    "encounter_id": pe.get("id"),
                    "arrival_time": pe.get("arrival_time"),
                    "chief_complaint": pe.get("chief_complaint"),
                    "status": pe.get("status")
                }
                for pe in (prior_encounters or [])[:3]
            ]
        }

        # ─── 5. Meta & Audit ────────────────────────────────────────────────
        meta = {
            "generated_at": now_iso,
            "version": "1.0.0",
            "patient_id": patient_data.get("id"),
            "patient_name": patient_data.get("name"),
            "encounter_id": encounter_data.get("id")
        }

        return {
            "meta": meta,
            "patient_reported": patient_reported,
            "observed": observed,
            "derived": derived,
            "longitudinal": longitudinal
        }
