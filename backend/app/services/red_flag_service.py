import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)

# Keywords for high-risk clinical symptom pattern matching
CHEST_KEYWORDS = ["chest pain", "chest pressure", "chest tightness", "angina", "cardiac"]
RESPIRATORY_KEYWORDS = ["shortness of breath", "difficulty breathing", "dyspnea", "wheezing", "cannot breathe", "gasping", "breathlessness"]
NEURO_KEYWORDS = ["sudden weakness", "facial drooping", "slurred speech", "numbness", "paralysis", "seizure", "convulsion", "unresponsive", "fainting", "syncope"]
BLEEDING_KEYWORDS = ["severe bleeding", "coughing blood", "hemoptysis", "vomiting blood", "hematemesis", "active hemorrhage", "blood in stool"]
ANAPHYLAXIS_KEYWORDS = ["throat swelling", "swollen tongue", "anaphylaxis", "lip swelling", "cannot swallow"]


class RedFlagService:
    """
    Deterministic clinical red-flag detection engine.
    Inspects structured clinical intake responses and recorded encounter vitals to identify
    critical physiological thresholds and high-risk symptom patterns without clinical hallucination.
    """

    def detect_red_flags(
        self,
        encounter_vitals: Dict[str, Any],
        intake_summary: Optional[Dict[str, Any]] = None,
        chief_complaint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate encounter vitals and patient intake data for red flags.
        Returns a structured list of detected red-flag findings.
        """
        red_flags: List[Dict[str, Any]] = []
        now_iso = utc_now_iso()

        # ─── 1. Vital Signs Red Flags ───────────────────────────────────────
        spo2 = encounter_vitals.get("spo2")
        if spo2 is not None:
            if spo2 <= 90:
                red_flags.append({
                    "code": "RF_CRITICAL_HYPOXIA",
                    "severity": "HIGH",
                    "reason": f"Critical low oxygen saturation: {spo2}% (<= 90%)",
                    "source": "vitals.spo2",
                    "observed_value": spo2,
                    "timestamp": now_iso
                })
            elif spo2 <= 93:
                red_flags.append({
                    "code": "RF_MILD_HYPOXIA",
                    "severity": "MEDIUM",
                    "reason": f"Mild to moderate hypoxemia: {spo2}% (<= 93%)",
                    "source": "vitals.spo2",
                    "observed_value": spo2,
                    "timestamp": now_iso
                })

        hr = encounter_vitals.get("heart_rate")
        if hr is not None:
            if hr >= 130:
                red_flags.append({
                    "code": "RF_SEVERE_TACHYCARDIA",
                    "severity": "HIGH",
                    "reason": f"Severe resting tachycardia: {hr} bpm (>= 130 bpm)",
                    "source": "vitals.heart_rate",
                    "observed_value": hr,
                    "timestamp": now_iso
                })
            elif hr >= 115:
                red_flags.append({
                    "code": "RF_TACHYCARDIA",
                    "severity": "MEDIUM",
                    "reason": f"Elevated resting heart rate: {hr} bpm (>= 115 bpm)",
                    "source": "vitals.heart_rate",
                    "observed_value": hr,
                    "timestamp": now_iso
                })
            elif hr <= 45:
                red_flags.append({
                    "code": "RF_SEVERE_BRADYCARDIA",
                    "severity": "HIGH",
                    "reason": f"Critical resting bradycardia: {hr} bpm (<= 45 bpm)",
                    "source": "vitals.heart_rate",
                    "observed_value": hr,
                    "timestamp": now_iso
                })

        bp_sys = encounter_vitals.get("bp_systolic")
        bp_dia = encounter_vitals.get("bp_diastolic")
        if bp_sys is not None:
            if bp_sys >= 180:
                red_flags.append({
                    "code": "RF_HYPERTENSIVE_CRISIS",
                    "severity": "HIGH",
                    "reason": f"Hypertensive crisis range systolic BP: {bp_sys} mmHg (>= 180 mmHg)",
                    "source": "vitals.bp_systolic",
                    "observed_value": bp_sys,
                    "timestamp": now_iso
                })
            elif bp_sys <= 85:
                red_flags.append({
                    "code": "RF_HYPOTENSION",
                    "severity": "HIGH",
                    "reason": f"Severe hypotension / shock threshold: {bp_sys} mmHg (<= 85 mmHg)",
                    "source": "vitals.bp_systolic",
                    "observed_value": bp_sys,
                    "timestamp": now_iso
                })
            elif bp_sys >= 150 or (bp_dia and bp_dia >= 95):
                red_flags.append({
                    "code": "RF_STAGE2_HYPERTENSION",
                    "severity": "MEDIUM",
                    "reason": f"Stage 2 hypertension: {bp_sys}/{bp_dia or '-'} mmHg",
                    "source": "vitals.bp",
                    "observed_value": f"{bp_sys}/{bp_dia}",
                    "timestamp": now_iso
                })

        rr = encounter_vitals.get("respiratory_rate")
        if rr is not None:
            if rr >= 28:
                red_flags.append({
                    "code": "RF_SEVERE_TACHYPNEA",
                    "severity": "HIGH",
                    "reason": f"Critical tachypnea: {rr} breaths/min (>= 28)",
                    "source": "vitals.respiratory_rate",
                    "observed_value": rr,
                    "timestamp": now_iso
                })
            elif rr <= 8:
                red_flags.append({
                    "code": "RF_SEVERE_BRADYPNEA",
                    "severity": "HIGH",
                    "reason": f"Critical respiratory depression / bradypnea: {rr} breaths/min (<= 8)",
                    "source": "vitals.respiratory_rate",
                    "observed_value": rr,
                    "timestamp": now_iso
                })

        temp_f = encounter_vitals.get("temperature_f")
        if temp_f is not None:
            if temp_f >= 103.5:
                red_flags.append({
                    "code": "RF_HIGH_GRADE_FEVER",
                    "severity": "HIGH",
                    "reason": f"High-grade hyperpyrexia: {temp_f}°F (>= 103.5°F)",
                    "source": "vitals.temperature_f",
                    "observed_value": temp_f,
                    "timestamp": now_iso
                })
            elif temp_f <= 95.0:
                red_flags.append({
                    "code": "RF_HYPOTHERMIA",
                    "severity": "HIGH",
                    "reason": f"Hypothermia alert: {temp_f}°F (<= 95.0°F)",
                    "source": "vitals.temperature_f",
                    "observed_value": temp_f,
                    "timestamp": now_iso
                })

        gcs = encounter_vitals.get("gcs_score")
        if gcs is not None:
            if gcs <= 12:
                red_flags.append({
                    "code": "RF_ALTERED_GCS",
                    "severity": "HIGH",
                    "reason": f"Significantly impaired consciousness / low GCS score: {gcs}/15 (<= 12)",
                    "source": "vitals.gcs_score",
                    "observed_value": gcs,
                    "timestamp": now_iso
                })
            elif gcs <= 14:
                red_flags.append({
                    "code": "RF_MILD_GCS_DECREASE",
                    "severity": "MEDIUM",
                    "reason": f"Mild cognitive or neurological depression: GCS {gcs}/15",
                    "source": "vitals.gcs_score",
                    "observed_value": gcs,
                    "timestamp": now_iso
                })

        # ─── 2. Pain Score Red Flags ────────────────────────────────────────
        # Check from intake summary or encounter vitals
        pain_score = None
        if intake_summary and isinstance(intake_summary.get("pain"), dict):
            pain_score = intake_summary["pain"].get("score")
        if pain_score is None:
            pain_score = encounter_vitals.get("pain_level")

        if pain_score is not None:
            try:
                p_val = int(pain_score)
                if p_val >= 8:
                    loc = intake_summary["pain"].get("location") if (intake_summary and isinstance(intake_summary.get("pain"), dict)) else "Unspecified location"
                    red_flags.append({
                        "code": "RF_SEVERE_PAIN",
                        "severity": "HIGH",
                        "reason": f"Severe reported pain score: {p_val}/10 ({loc or 'Unspecified'})",
                        "source": "intake.pain.score",
                        "observed_value": p_val,
                        "timestamp": now_iso
                    })
                elif p_val >= 6:
                    red_flags.append({
                        "code": "RF_MODERATE_SEVERE_PAIN",
                        "severity": "MEDIUM",
                        "reason": f"Moderate-severe reported pain score: {p_val}/10",
                        "source": "intake.pain.score",
                        "observed_value": p_val,
                        "timestamp": now_iso
                    })
            except (ValueError, TypeError):
                pass

        # ─── 3. Symptom & Chief Complaint Red Flags ─────────────────────────
        text_corpus = []
        if chief_complaint:
            text_corpus.append(chief_complaint.lower())
        if intake_summary:
            if intake_summary.get("chief_complaint"):
                text_corpus.append(str(intake_summary["chief_complaint"]).lower())
            if isinstance(intake_summary.get("symptoms"), list):
                text_corpus.extend([str(s).lower() for s in intake_summary["symptoms"]])

        combined_text = " ".join(text_corpus)

        if any(kw in combined_text for kw in CHEST_KEYWORDS):
            red_flags.append({
                "code": "RF_CHEST_COMPLAINT",
                "severity": "HIGH",
                "reason": "Reported acute chest pain, cardiac discomfort, or tightness",
                "source": "intake.chief_complaint",
                "observed_value": "Chest-related complaint identified",
                "timestamp": now_iso
            })

        if any(kw in combined_text for kw in RESPIRATORY_KEYWORDS):
            red_flags.append({
                "code": "RF_RESPIRATORY_DISTRESS",
                "severity": "HIGH",
                "reason": "Reported acute shortness of breath or severe respiratory difficulty",
                "source": "intake.symptoms",
                "observed_value": "Respiratory distress complaint identified",
                "timestamp": now_iso
            })

        if any(kw in combined_text for kw in NEURO_KEYWORDS):
            red_flags.append({
                "code": "RF_ACUTE_NEUROLOGICAL_DEFICIT",
                "severity": "HIGH",
                "reason": "Reported sudden neurological deficits, seizure, slurred speech, or syncope",
                "source": "intake.symptoms",
                "observed_value": "Acute neurological complaint identified",
                "timestamp": now_iso
            })

        if any(kw in combined_text for kw in BLEEDING_KEYWORDS):
            red_flags.append({
                "code": "RF_ACUTE_HEMORRHAGE",
                "severity": "HIGH",
                "reason": "Reported acute or severe active hemorrhage / vomiting blood / coughing blood",
                "source": "intake.symptoms",
                "observed_value": "Hemorrhage complaint identified",
                "timestamp": now_iso
            })

        if any(kw in combined_text for kw in ANAPHYLAXIS_KEYWORDS):
            red_flags.append({
                "code": "RF_ANAPHYLACTIC_SUSPICION",
                "severity": "HIGH",
                "reason": "Reported rapid airway / throat swelling or acute allergic distress",
                "source": "intake.symptoms",
                "observed_value": "Airway compromise complaint identified",
                "timestamp": now_iso
            })

        return red_flags
