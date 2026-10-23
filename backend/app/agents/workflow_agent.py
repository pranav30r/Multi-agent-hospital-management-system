"""
Autonomous Clinical Workflow Recommendation Agent.

Evaluates triage assessments, patient presentation, intake vitals, ESI acuity,
and clinical red flags to deterministically select protocol templates and recommend
structured, prioritized clinical task chains with verification checklists.

CRITICAL SAFETY INVARIANT:
This agent is recommendation-only (status="PENDING"). It never mutates live
database tasks, patient/encounter states, bed statuses, or physical resources.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.patient import Patient, Encounter
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)

# ─── Clinical Protocol Constants ─────────────────────────────────────────────

PROTOCOL_RESUSCITATION = "RESUSCITATION_ESI1_SHOCK_PROTOCOL"
PROTOCOL_CARDIAC = "CARDIAC_ACUTE_CHEST_PAIN_PROTOCOL"
PROTOCOL_RESPIRATORY = "RESPIRATORY_DISTRESS_HYPOXIA_PROTOCOL"
PROTOCOL_SEPSIS = "SUSPECTED_SEPSIS_PROTOCOL"
PROTOCOL_OUTPATIENT = "ROUTINE_OUTPATIENT_LOWER_ACUITY_PROTOCOL"
PROTOCOL_GENERAL = "GENERAL_CLINICAL_EVALUATION_PROTOCOL"


class ClinicalWorkflowAgent(BaseAgent):
    """
    Deterministic, safety-first Clinical Workflow Recommendation Agent.
    
    Subclasses BaseAgent. Ingests triage assessments and patient encounter data,
    evaluates clinical rules across 5 deterministic protocols, and produces
    structured task chains with explicit urgency targets and verification checklists.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            db=db,
            agent_id="clinical_workflow_agent",
            name="Clinical Workflow Recommendation Agent"
        )

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str = "HOSP-DEFAULT",
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Executes deterministic clinical protocol selection and emits structured recommendations.

        Pure evaluation: Never mutates database records, encounter states, beds, or tasks.
        Deterministic: Produces identical recommendations for identical normalized inputs.
        """
        if encounter is None:
            raise ValueError("Encounter object is required for clinical workflow evaluation")
        if patient is None:
            raise ValueError("Patient object is required for clinical workflow evaluation")
        if not isinstance(triage_output, dict):
            raise ValueError("triage_output must be a dictionary")

        # 1. Normalize and extract available clinical data safely
        chief_complaint = (encounter.chief_complaint or "").lower()
        esi_level = encounter.esi_level or triage_output.get("esi_level")
        if esi_level is not None:
            try:
                esi_level = int(esi_level)
            except (ValueError, TypeError):
                esi_level = None

        severity = str(triage_output.get("severity") or "LOW").upper()
        raw_red_flags = triage_output.get("red_flags") or []
        red_flags: List[str] = []
        for rf in raw_red_flags:
            if isinstance(rf, dict):
                desc = rf.get("description") or rf.get("code") or str(rf)
                red_flags.append(str(desc).lower())
            elif isinstance(rf, str):
                red_flags.append(rf.lower())

        hr = encounter.heart_rate
        bp_sys = encounter.bp_systolic
        bp_dia = encounter.bp_diastolic
        spo2 = encounter.spo2
        temp_f = encounter.temperature_f
        rr = encounter.respiratory_rate
        gcs = encounter.gcs_score

        # 2. Safety Audit: Detect missing vital signs and uncertainty
        safety_flags: List[str] = []
        if hr is None:
            safety_flags.append("MISSING_VITAL: Heart rate was not recorded.")
        if bp_sys is None:
            safety_flags.append("MISSING_VITAL: Systolic blood pressure was not recorded.")
        if spo2 is None:
            safety_flags.append("MISSING_VITAL: SpO2 pulse oximetry was not recorded.")
        if temp_f is None:
            safety_flags.append("MISSING_VITAL: Body temperature was not recorded.")
        if rr is None:
            safety_flags.append("MISSING_VITAL: Respiratory rate was not recorded.")
        if gcs is None and esi_level in [1, 2]:
            safety_flags.append("MISSING_ASSESSMENT: Glasgow Coma Scale (GCS) not recorded for high-acuity encounter.")
        if not patient.allergies:
            safety_flags.append("CLINICAL_UNCERTAINTY: Patient allergy record is unverified/empty.")

        for rf in red_flags:
            safety_flags.append(f"HIGH_RISK_FLAG: {rf}")

        # 3. Deterministic Protocol Selection Matching Engine
        selected_protocols: List[str] = []
        reasoning_points: List[str] = []

        # ── Trigger A: Resuscitation / ESI 1 / Shock ──
        is_resuscitation = False
        resus_reasons = []
        if esi_level == 1:
            is_resuscitation = True
            resus_reasons.append("ESI-1 triage acuity")
        if any(term in chief_complaint for term in ["cardiac arrest", "unresponsive", "resuscitation", "profound shock"]):
            is_resuscitation = True
            resus_reasons.append("Chief complaint indicates severe physiological arrest or shock")
        if any("shock" in rf or "arrest" in rf or "code blue" in rf or "unresponsive" in rf for rf in red_flags):
            is_resuscitation = True
            resus_reasons.append("Clinical red flags indicate shock or arrest")
        if gcs is not None and gcs <= 8:
            is_resuscitation = True
            resus_reasons.append(f"Severe coma / neurological compromise (GCS {gcs} <= 8)")
        if bp_sys is not None and bp_sys < 80 and (hr is not None and hr > 120):
            is_resuscitation = True
            resus_reasons.append(f"Decompensated hemodynamic shock (BP {bp_sys} mmHg, HR {hr} bpm)")

        if is_resuscitation:
            selected_protocols.append(PROTOCOL_RESUSCITATION)
            reasoning_points.append(
                f"Triggered Resuscitation Protocol: {'; '.join(resus_reasons)}. "
                "Severe physiological instability / ESI-1 arrest takes precedence over secondary pathways."
            )
        else:
            # ── Trigger B: Cardiac / Acute Chest Pain ──
            is_cardiac = False
            cardiac_reasons = []
            cardiac_keywords = [
                "chest pain", "angina", "myocardial", "crushing chest", "substernal",
                "cardiac pain", "pressure in chest", "radiation to left arm", "radiation to jaw",
                "heart attack", "heart failure", "cardiac arrest", "coronary", "acute coronary"
            ]
            if any(kw in chief_complaint for kw in cardiac_keywords):
                is_cardiac = True
                cardiac_reasons.append("Chief complaint presentation indicates acute chest pain / possible ACS")
            if any("chest" in rf or "cardiac" in rf or "rf-chest-pain" in rf or "troponin" in rf for rf in red_flags):
                is_cardiac = True
                cardiac_reasons.append("Triage red flags identify acute cardiac risk indicators")

            if is_cardiac:
                selected_protocols.append(PROTOCOL_CARDIAC)
                reasoning_points.append(f"Triggered Cardiac Protocol: {'; '.join(cardiac_reasons)}.")

            # ── Trigger C: Respiratory Distress / Hypoxia ──
            is_respiratory = False
            resp_reasons = []
            # Strictly positive measurement check (never infer missing data as positive)
            if spo2 is not None and spo2 < 92:
                is_respiratory = True
                resp_reasons.append(f"Documented arterial hypoxia (SpO2 {spo2}% < 92%)")
            if rr is not None and (rr >= 28 or rr <= 9):
                is_respiratory = True
                resp_reasons.append(f"Critical abnormal respiratory rate ({rr} breaths/min)")
            resp_keywords = [
                "shortness of breath", "respiratory distress", "dyspnea", "asthma attack",
                "hypoxia", "wheezing", "stridor", "air hunger", "choking"
            ]
            if any(kw in chief_complaint for kw in resp_keywords):
                is_respiratory = True
                resp_reasons.append("Chief complaint indicates acute respiratory distress / dyspnea")
            if any("hypoxia" in rf or "respiratory" in rf or "spo2" in rf for rf in red_flags):
                is_respiratory = True
                resp_reasons.append("Triage red flags identify acute respiratory compromise")

            if is_respiratory:
                selected_protocols.append(PROTOCOL_RESPIRATORY)
                reasoning_points.append(f"Triggered Respiratory Protocol: {'; '.join(resp_reasons)}.")

            # ── Trigger D: Suspected Sepsis ──
            is_sepsis = False
            sepsis_reasons = []
            infection_keywords = [
                "fever", "infection", "sepsis", "pneumonia", "chills", "urinary tract",
                "uti", "cellulitis", "bacteremia", "abscess", "pyelonephritis", "purulent"
            ]
            has_infection_presentation = (
                any(kw in chief_complaint for kw in infection_keywords) or
                (temp_f is not None and (temp_f >= 100.4 or temp_f < 96.8)) or
                any("sepsis" in rf or "infection" in rf or "fever" in rf for rf in red_flags)
            )

            if has_infection_presentation:
                associated_findings = 0
                findings_desc = []
                if temp_f is not None and (temp_f >= 100.4 or temp_f < 96.8):
                    associated_findings += 1
                    findings_desc.append(f"Abnormal temperature ({temp_f}°F)")
                if hr is not None and hr > 90:
                    associated_findings += 1
                    findings_desc.append(f"Tachycardia ({hr} bpm)")
                if rr is not None and rr >= 20:
                    associated_findings += 1
                    findings_desc.append(f"Tachypnea ({rr} breaths/min)")
                if bp_sys is not None and bp_sys <= 100:
                    associated_findings += 1
                    findings_desc.append(f"Hypotension (Systolic BP {bp_sys} mmHg)")
                if gcs is not None and gcs < 15:
                    associated_findings += 1
                    findings_desc.append(f"Altered mental status (GCS {gcs})")

                # Require suspected infection PLUS at least 2 objective physiological criteria
                if associated_findings >= 2:
                    is_sepsis = True
                    sepsis_reasons.append(
                        f"Suspected systemic infection with {associated_findings} concerning findings: {', '.join(findings_desc)}"
                    )

            if is_sepsis:
                selected_protocols.append(PROTOCOL_SEPSIS)
                reasoning_points.append(f"Triggered Sepsis Protocol: {'; '.join(sepsis_reasons)}.")

        # ── Trigger E: Routine Outpatient / Lower-Acuity Workflow ──
        # Invariant: Routine outpatient NEVER triggers if acute protocols triggered or red flags exist
        is_outpatient = False
        has_acute_protocols = is_resuscitation or is_cardiac or is_respiratory or is_sepsis
        has_high_risk = len(red_flags) > 0 or severity in ["HIGH", "CRITICAL"]

        if esi_level in [4, 5] and not has_acute_protocols and not has_high_risk:
            is_outpatient = True
            selected_protocols.append(PROTOCOL_OUTPATIENT)
            reasoning_points.append(
                f"Selected Routine Outpatient Protocol: Stable lower-acuity presentation (ESI-{esi_level}) without acute protocol triggers or red flags."
            )
        elif esi_level in [4, 5] and (has_acute_protocols or has_high_risk):
            reasoning_points.append(
                f"ESI-{esi_level} baseline overridden by acute clinical findings / red flags; acute clinical pathway prioritized."
            )

        # Fallback if no specific protocol triggered (e.g. general ESI 3 presentation)
        if not selected_protocols:
            selected_protocols.append(PROTOCOL_GENERAL)
            reasoning_points.append(
                f"Selected General Clinical Evaluation Protocol: Presentation acuity ESI-{esi_level or 3} with severity {severity}."
            )

        # 4. Generate Task Chain based on Selected Protocols
        raw_tasks: List[Dict[str, Any]] = []

        # Order of precedence for templates: Resuscitation -> Cardiac -> Respiratory -> Sepsis -> General -> Outpatient
        if PROTOCOL_RESUSCITATION in selected_protocols:
            raw_tasks.extend(self._build_resuscitation_tasks(encounter, triage_output))

        if PROTOCOL_CARDIAC in selected_protocols:
            raw_tasks.extend(self._build_cardiac_tasks(encounter, triage_output, esi_level))

        if PROTOCOL_RESPIRATORY in selected_protocols:
            raw_tasks.extend(self._build_respiratory_tasks(encounter, triage_output))

        if PROTOCOL_SEPSIS in selected_protocols:
            raw_tasks.extend(self._build_sepsis_tasks(encounter, triage_output))

        if PROTOCOL_GENERAL in selected_protocols:
            raw_tasks.extend(self._build_general_tasks(encounter, triage_output, esi_level))

        if PROTOCOL_OUTPATIENT in selected_protocols:
            raw_tasks.extend(self._build_outpatient_tasks(encounter, triage_output))

        # 5. Deduplicate and order task chain deterministically
        task_chain = self._deduplicate_and_sort_tasks(raw_tasks)

        # Primary protocol identifier
        primary_protocol = selected_protocols[0]

        # Determine human review requirement
        # Human review is required for all acute/consequential protocols or if high-risk flags exist
        requires_human_review = not (is_outpatient and esi_level == 5 and len(safety_flags) == 0)

        reasoning_summary = " ".join(reasoning_points)
        timestamp = utc_now_iso()

        return {
            "status": "PENDING",
            "agent": self.agent_id,
            "agent_id": self.agent_id,
            "protocol": primary_protocol,
            "selected_protocols": selected_protocols,
            "task_chain": task_chain,
            "reasoning_summary": reasoning_summary,
            "safety_flags": safety_flags,
            "requires_human_review": requires_human_review,
            "tenant_id": tenant_id,
            "provenance": {
                "agent_name": self.name,
                "agent_id": self.agent_id,
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "tenant_id": tenant_id,
                "timestamp": timestamp,
                "deterministic": True
            },
            "timestamp": timestamp
        }

    # ─── Protocol Task Builders ──────────────────────────────────────────────

    def _build_resuscitation_tasks(self, encounter: Encounter, triage_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "task_key": "CLINICAL_ASSESSMENT_STAT",
                "title": "Immediate Resuscitation & Emergency Clinician Assessment",
                "task_type": "ASSESSMENT",
                "urgency": "STAT",
                "time_window": "< 5 minutes",
                "suggested_role": "DOCTOR",
                "description": "Immediate bedside emergency physician assessment and resuscitation team leadership.",
                "rationale": "Patient exhibits severe instability, respiratory/cardiac arrest, or profound shock (ESI-1).",
                "verification_checklist": [
                    "Immediate bedside arrival of attending emergency physician",
                    "Conduct rapid primary survey: Airway, Breathing, Circulation, Disability (ABCs)",
                    "Establish resuscitation team leader and assign roles"
                ]
            },
            {
                "task_key": "AIRWAY_EVALUATION_STAT",
                "title": "Airway & Breathing Support Evaluation",
                "task_type": "ASSESSMENT",
                "urgency": "STAT",
                "time_window": "< 5 minutes",
                "suggested_role": "DOCTOR",
                "description": "Assess airway patency, protective reflexes, and indications for rapid sequence intubation (RSI).",
                "rationale": "High risk of aspiration, respiratory failure, or loss of airway protective reflexes.",
                "verification_checklist": [
                    "Assess spontaneous breathing effort and airway patency",
                    "Prepare suction and bag-valve-mask with 100% O2 reservoir",
                    "Verify availability of emergency difficult airway cart and video laryngoscopy"
                ]
            },
            {
                "task_key": "IV_ACCESS_STAT",
                "title": "Establish Large-Bore Vascular Access",
                "task_type": "INTERVENTION",
                "urgency": "STAT",
                "time_window": "< 10 minutes",
                "suggested_role": "NURSE",
                "description": "Establish dual large-bore peripheral IV access (16-18G) or intraosseous (IO) access.",
                "rationale": "Immediate vascular access required for rapid crystalloid boluses and emergency medications.",
                "verification_checklist": [
                    "Place two large-bore IV cannulae (16G or 18G) or IO needle if IV fails",
                    "Flush lines and verify free flow without extravasation",
                    "Draw emergency lab panel (crossmatch, lactate, venous blood gas, CBC)"
                ]
            },
            {
                "task_key": "RESUS_TEAM_ALERT_STAT",
                "title": "Resuscitation / Code Team Bedside Alert Recommendation",
                "task_type": "INTERVENTION",
                "urgency": "STAT",
                "time_window": "< 5 minutes",
                "suggested_role": "NURSE",
                "description": "Recommend activating hospital Rapid Response Team (RRT) or Code Blue paging protocol.",
                "rationale": "ESI-1 physiological decompensation requires coordinated multi-disciplinary resuscitation response.",
                "verification_checklist": [
                    "Verify paging dispatch to designated Code / Rapid Response Team",
                    "Log alert activation timestamp in clinical event log",
                    "Confirm resuscitation team arrival at bedside"
                ]
            },
            {
                "task_key": "CRITICAL_CARE_ESCALATION_STAT",
                "title": "Critical Care Escalation & ICU Resource Review",
                "task_type": "ASSESSMENT",
                "urgency": "STAT",
                "time_window": "< 30 minutes",
                "suggested_role": "DOCTOR",
                "description": "Liaise with ICU intensivist and Bed Management for immediate critical care escalation.",
                "rationale": "Post-resuscitation care requires continuous invasive hemodynamic monitoring in an intensive care setting.",
                "verification_checklist": [
                    "Initiate bedside critical care intensivist consultation",
                    "Review mechanical ventilator and arterial line transducer availability",
                    "Notify Bed Management for priority ICU allocation"
                ]
            }
        ]

    def _build_cardiac_tasks(self, encounter: Encounter, triage_output: Dict[str, Any], esi_level: Optional[int]) -> List[Dict[str, Any]]:
        is_stat = (esi_level is not None and esi_level <= 2) or (encounter.pain_level is not None and encounter.pain_level >= 7)
        assessment_urgency = "STAT" if is_stat else "URGENT"
        assessment_time = "< 10 minutes" if is_stat else "< 15 minutes"

        return [
            {
                "task_key": "CARDIAC_CLINICAL_ASSESSMENT",
                "title": "Urgent Clinician Assessment (Cardiac / Acute Chest Pain)",
                "task_type": "ASSESSMENT",
                "urgency": assessment_urgency,
                "time_window": assessment_time,
                "suggested_role": "DOCTOR",
                "description": "Primary clinician evaluation for acute coronary syndrome, aortic dissection, or pulmonary embolism.",
                "rationale": "Rapid targeted evaluation required to rule out STEMI and life-threatening chest pain etiologies.",
                "verification_checklist": [
                    "Evaluate chest pain onset, character, radiation, and associated symptoms",
                    "Auscultate heart sounds (murmurs, S3/S4) and bilateral breath sounds",
                    "Assess bilateral radial/femoral pulses for asymmetry"
                ]
            },
            {
                "task_key": "ECG_12_LEAD_STAT",
                "title": "12-Lead Electrocardiogram (ECG)",
                "task_type": "DIAGNOSTIC",
                "urgency": "STAT",
                "time_window": "< 10 minutes",
                "suggested_role": "NURSE",
                "description": "Acquire and review a 12-lead ECG with a target of within 10 minutes of arrival.",
                "rationale": "ACC/AHA clinical guideline: 12-lead ECG must be performed and physician-interpreted within 10 minutes for acute chest pain.",
                "verification_checklist": [
                    "Acquire diagnostic 12-lead ECG recording within 10 minutes of presentation",
                    "Hand ECG directly to attending physician for immediate ST-elevation evaluation",
                    "Compare against prior baseline ECG if accessible in electronic record"
                ]
            },
            {
                "task_key": "IV_ACCESS_CARDIAC",
                "title": "Establish Peripheral IV Access & Cardiac Blood Sampling",
                "task_type": "INTERVENTION",
                "urgency": "STAT" if is_stat else "URGENT",
                "time_window": "< 15 minutes",
                "suggested_role": "NURSE",
                "description": "Establish peripheral IV access and collect blood tubes for urgent cardiac biomarkers.",
                "rationale": "Vascular access is mandatory for cardiac medication titration, analgesia, and serial laboratory testing.",
                "verification_checklist": [
                    "Place 18G or 20G peripheral IV line in upper extremity",
                    "Confirm line patency and secure sterile dressing",
                    "Label diagnostic blood collection tubes at bedside"
                ]
            },
            {
                "task_key": "CARDIAC_BIOMARKERS_LAB",
                "title": "High-Sensitivity Troponin & Core Cardiac Laboratory Panel",
                "task_type": "DIAGNOSTIC",
                "urgency": "STAT",
                "time_window": "< 30 minutes",
                "suggested_role": "LAB_TECH",
                "description": "STAT High-Sensitivity Troponin-I / T, Complete Blood Count, Electrolytes, and Coagulation profile.",
                "rationale": "High-sensitivity troponin assays identify myocardial necrosis and guide rapid risk stratification.",
                "verification_checklist": [
                    "Receive and process STAT High-Sensitivity Troponin sample",
                    "Transmit critical laboratory values to attending physician immediately",
                    "Schedule repeat serial troponin measurement in 2-3 hours per protocol"
                ]
            },
            {
                "task_key": "CONTINUOUS_TELEMETRY_MONITORING",
                "title": "Continuous Cardiac Telemetry & Hemodynamic Monitoring",
                "task_type": "MONITORING",
                "urgency": "URGENT",
                "time_window": "< 15 minutes",
                "suggested_role": "NURSE",
                "description": "Initiate continuous 3/5-lead ECG rhythm telemetry, continuous SpO2, and automated NIBP cycling.",
                "rationale": "Detects early malignant ventricular arrhythmias, conduction blocks, or acute hemodynamic decompensation.",
                "verification_checklist": [
                    "Attach telemetry leads with clean electrode prep and verify artifact-free trace",
                    "Configure heart rate alarm limits (bradycardia < 50, tachycardia > 120 bpm)",
                    "Ensure telemetry stream is actively displayed on nursing central monitor"
                ]
            }
        ]

    def _build_respiratory_tasks(self, encounter: Encounter, triage_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        is_stat = encounter.spo2 is not None and encounter.spo2 < 88
        urgency = "STAT" if is_stat else "URGENT"

        return [
            {
                "task_key": "RESPIRATORY_ASSESSMENT",
                "title": "Urgent Respiratory Clinical Assessment",
                "task_type": "ASSESSMENT",
                "urgency": urgency,
                "time_window": "< 10 minutes" if is_stat else "< 15 minutes",
                "suggested_role": "DOCTOR",
                "description": "Evaluate work of breathing, accessory muscle use, lung aeration, and mental acuity.",
                "rationale": "Timely assessment identifies impending respiratory exhaustion or acute ventilatory failure.",
                "verification_checklist": [
                    "Auscultate bilateral breath sounds for wheezing, rales, stridor, or silence",
                    "Assess respiratory rate, effort, retractions, and paradoxical abdominal movement",
                    "Evaluate ability to speak in full sentences vs fragmented phrases"
                ]
            },
            {
                "task_key": "OXYGEN_TITRATION_INTERVENTION",
                "title": "Oxygen Assessment & Titration Protocol Recommendation",
                "task_type": "INTERVENTION",
                "urgency": "STAT" if is_stat else "URGENT",
                "time_window": "< 10 minutes",
                "suggested_role": "NURSE",
                "description": "Recommend oxygen delivery device titration targeting protocol SpO2 range (94-98%, or 88-92% for known COPD).",
                "rationale": "Restores arterial oxygen content while mitigating hypercapnic respiratory depression in chronic lung disease.",
                "verification_checklist": [
                    "Select appropriate oxygen delivery interface (nasal cannula / Venturi / non-rebreather)",
                    "Titrate flow to protocol target: SpO2 94-98% (or 88-92% for verified hypercapnic risk)",
                    "Observe continuous SpO2 waveform for response"
                ]
            },
            {
                "task_key": "BRONCHODILATOR_NEBULIZATION_REVIEW",
                "title": "Bronchodilator Nebulization Review Recommendation",
                "task_type": "INTERVENTION",
                "urgency": "URGENT",
                "time_window": "< 30 minutes",
                "suggested_role": "NURSE",
                "description": "Evaluate clinical indication for inhaled bronchodilator therapy (e.g. salbutamol/ipratropium) per physician order.",
                "rationale": "Relieves acute bronchospasm in asthma, COPD, or reactive airway exacerbations.",
                "verification_checklist": [
                    "Review patient cardiac history and allergy documentation",
                    "Confirm physician medication order before nebulization initiation",
                    "Re-auscultate breath sounds and record post-treatment respiratory rate"
                ]
            },
            {
                "task_key": "ARTERIAL_BLOOD_GAS_DIAGNOSTIC",
                "title": "Arterial Blood Gas (ABG) Investigation Consideration",
                "task_type": "DIAGNOSTIC",
                "urgency": "URGENT",
                "time_window": "< 30 minutes",
                "suggested_role": "DOCTOR",
                "description": "Consider arterial blood gas sampling to evaluate pH, PaCO2, PaO2, and metabolic compensation.",
                "rationale": "Identifies acute respiratory acidosis, alveolar hypoventilation, and exact oxygenation deficit.",
                "verification_checklist": [
                    "Perform Allen's collateral circulation test before radial artery puncture",
                    "Collect heparinized arterial specimen without ambient air exposure",
                    "Deliver immediately on ice to laboratory or run on point-of-care analyzer"
                ]
            },
            {
                "task_key": "PORTABLE_CHEST_XRAY_DIAGNOSTIC",
                "title": "Portable Chest Radiograph (X-Ray) Investigation",
                "task_type": "DIAGNOSTIC",
                "urgency": "URGENT",
                "time_window": "< 45 minutes",
                "suggested_role": "RADIOLOGY_TECH",
                "description": "Order bedside portable AP chest radiograph.",
                "rationale": "Rapidly excludes pneumothorax, pulmonary edema, lobar consolidation, and massive effusion without transporting unstable patient.",
                "verification_checklist": [
                    "Verify portable chest X-ray clinical order and patient pregnancy status",
                    "Position patient in upright AP posture if clinically tolerated",
                    "Notify attending clinician once images are transmitted to PACS"
                ]
            }
        ]

    def _build_sepsis_tasks(self, encounter: Encounter, triage_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        is_stat = encounter.bp_systolic is not None and encounter.bp_systolic < 90

        return [
            {
                "task_key": "SEPSIS_SCREENING_ASSESSMENT",
                "title": "Urgent Sepsis Screening & Clinician Assessment",
                "task_type": "ASSESSMENT",
                "urgency": "STAT" if is_stat else "URGENT",
                "time_window": "< 15 minutes",
                "suggested_role": "DOCTOR",
                "description": "Structured sepsis bundle evaluation, identification of putative infectious focus, and SOFA score calculation.",
                "rationale": "Early recognition and protocolized sepsis bundle initiation directly reduces in-hospital mortality.",
                "verification_checklist": [
                    "Identify suspected infectious focus (pulmonary, urinary, abdominal, skin/soft tissue)",
                    "Calculate bedside qSOFA and sequential organ failure assessment score",
                    "Assess peripheral perfusion, capillary refill time, and mental status"
                ]
            },
            {
                "task_key": "BLOOD_CULTURES_LACTATE_DIAGNOSTIC",
                "title": "Blood Cultures & Serum Lactate Investigation",
                "task_type": "DIAGNOSTIC",
                "urgency": "STAT",
                "time_window": "< 30 minutes",
                "suggested_role": "NURSE",
                "description": "Draw 2 sets of peripheral blood cultures (aerobic and anaerobic) prior to antimicrobials; order STAT serum lactate.",
                "rationale": "Isolates circulating pathogens and quantifies tissue hypoperfusion/anaerobic metabolism.",
                "verification_checklist": [
                    "Collect 2 blood culture sets from separate venipuncture sites under aseptic protocol",
                    "Ensure blood cultures are obtained before antimicrobial administration",
                    "Send STAT blood lactate sample to laboratory on ice"
                ]
            },
            {
                "task_key": "ANTIMICROBIAL_EVALUATION_ASSESSMENT",
                "title": "Timely Antimicrobial Evaluation Recommendation",
                "task_type": "ASSESSMENT",
                "urgency": "STAT",
                "time_window": "< 60 minutes",
                "suggested_role": "DOCTOR",
                "description": "Recommend attending clinician evaluate patient for guideline-directed empiric broad-spectrum antimicrobial therapy.",
                "rationale": "Delay in indicated antimicrobial therapy in septic shock increases mortality. Subject to authorized clinician order.",
                "verification_checklist": [
                    "Verify patient documented drug allergies and baseline renal function",
                    "Consult institutional empiric antibiogram and infectious disease guidelines",
                    "Ensure physician reviews and authorizes all antimicrobial orders"
                ]
            },
            {
                "task_key": "FLUID_RESUSCITATION_REVIEW_ASSESSMENT",
                "title": "Fluid Resuscitation Assessment & Escalation Review",
                "task_type": "ASSESSMENT",
                "urgency": "URGENT",
                "time_window": "< 30 minutes",
                "suggested_role": "DOCTOR",
                "description": "Assess volume status and consider balanced crystalloid challenge (e.g. 30 mL/kg) if hypotensive or lactate >= 4 mmol/L.",
                "rationale": "Restores effective circulating volume; requires strict clinician monitoring for fluid overload.",
                "verification_checklist": [
                    "Evaluate cardiopulmonary status and history of congestive heart failure/ESRD",
                    "Assess dynamic hemodynamic response during fluid administration",
                    "Review indication for early vasopressor initiation if mean arterial pressure < 65 mmHg"
                ]
            }
        ]

    def _build_outpatient_tasks(self, encounter: Encounter, triage_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "task_key": "OUTPATIENT_DOCUMENTATION_ASSESSMENT",
                "title": "Clinical Documentation Review & Non-Urgent History",
                "task_type": "ASSESSMENT",
                "urgency": "ROUTINE",
                "time_window": "< 60 minutes",
                "suggested_role": "DOCTOR",
                "description": "Review presenting low-acuity complaint, medical history, allergies, and record outpatient documentation.",
                "rationale": "Ensures standardized medical record documentation for routine outpatient consultation.",
                "verification_checklist": [
                    "Document chief complaint history and duration of symptoms",
                    "Verify allergy list and current medications with patient",
                    "Formulate diagnosis and outpatient management plan"
                ]
            },
            {
                "task_key": "PRESCRIPTION_RECONCILIATION_ASSESSMENT",
                "title": "Prescription Reconciliation & Medication Verification",
                "task_type": "ASSESSMENT",
                "urgency": "ROUTINE",
                "time_window": "< 90 minutes",
                "suggested_role": "PHARMACIST",
                "description": "Reconcile outpatient prescription orders against existing medications, allergies, and renal adjustments.",
                "rationale": "Prevents adverse drug events and verifies outpatient dosage schedules.",
                "verification_checklist": [
                    "Screen prescription for drug-drug and drug-allergy interactions",
                    "Confirm medication dosage, route, frequency, and treatment duration",
                    "Provide patient medication counseling leaflet"
                ]
            },
            {
                "task_key": "DISCHARGE_INSTRUCTIONS_REVIEW",
                "title": "Follow-Up & Discharge Instructions Review",
                "task_type": "DISCHARGE",
                "urgency": "ROUTINE",
                "time_window": "Prior to discharge",
                "suggested_role": "NURSE",
                "description": "Review discharge care instructions, warning signs for return, and schedule outpatient follow-up.",
                "rationale": "Promotes patient self-care adherence and safe outpatient care continuity.",
                "verification_checklist": [
                    "Deliver written discharge instructions and emergency return precautions",
                    "Confirm patient understanding of prescribed medication schedule",
                    "Schedule outpatient follow-up appointment or specialist referral"
                ]
            }
        ]

    def _build_general_tasks(self, encounter: Encounter, triage_output: Dict[str, Any], esi_level: Optional[int]) -> List[Dict[str, Any]]:
        urgency = "URGENT" if esi_level in [2, 3] else "ROUTINE"
        time_window = "< 30 minutes" if esi_level in [2, 3] else "< 60 minutes"

        return [
            {
                "task_key": "GENERAL_CLINICAL_ASSESSMENT",
                "title": "General Clinical Assessment & Physical Examination",
                "task_type": "ASSESSMENT",
                "urgency": urgency,
                "time_window": time_window,
                "suggested_role": "DOCTOR",
                "description": "Comprehensive primary medical evaluation and targeted physical examination.",
                "rationale": "Establishes baseline clinical diagnosis and directs targeted investigations.",
                "verification_checklist": [
                    "Perform focused history and organ system physical examination",
                    "Formulate differential diagnosis and investigation plan",
                    "Document assessment findings in electronic medical record"
                ]
            },
            {
                "task_key": "NURSING_INTAKE_MONITORING",
                "title": "Nursing Intake & Serial Vital Signs Monitoring",
                "task_type": "MONITORING",
                "urgency": urgency,
                "time_window": time_window,
                "suggested_role": "NURSE",
                "description": "Complete intake nursing assessment, allergy verification, and serial vital sign cycling.",
                "rationale": "Monitors patient stability and detects early physiological deviation.",
                "verification_checklist": [
                    "Obtain complete set of vital signs (HR, BP, SpO2, Temp, RR)",
                    "Assess pain score and implement comfort measures",
                    "Verify allergy band and patient identification"
                ]
            }
        ]

    # ─── Deduplication and Sorting ───────────────────────────────────────────

    def _deduplicate_and_sort_tasks(self, raw_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates overlapping tasks by task_key and sorts them by urgency and clinical sequence.
        Urgency precedence: STAT (0) > URGENT (1) > ROUTINE (2).
        Task type sequence: ASSESSMENT (0) > DIAGNOSTIC (1) > INTERVENTION (2) > MONITORING (3) > DISCHARGE (4).
        """
        seen_keys: set[str] = set()
        unique_tasks: List[Dict[str, Any]] = []

        urgency_priority = {"STAT": 0, "URGENT": 1, "ROUTINE": 2}
        type_priority = {"ASSESSMENT": 0, "DIAGNOSTIC": 1, "INTERVENTION": 2, "MONITORING": 3, "DISCHARGE": 4}

        for task in raw_tasks:
            key = task.get("task_key", task["title"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique_tasks.append(task)
            else:
                # If seen with lower urgency, upgrade if current is higher urgency
                for idx, existing in enumerate(unique_tasks):
                    existing_key = existing.get("task_key", existing["title"])
                    if existing_key == key:
                        curr_urg = urgency_priority.get(task.get("urgency", "ROUTINE"), 2)
                        exist_urg = urgency_priority.get(existing.get("urgency", "ROUTINE"), 2)
                        if curr_urg < exist_urg:
                            unique_tasks[idx] = task
                        break

        # Sort tasks by (urgency, task_type)
        def sort_key(t: Dict[str, Any]) -> tuple:
            urg = urgency_priority.get(t.get("urgency", "ROUTINE"), 2)
            typ = type_priority.get(t.get("task_type", "ASSESSMENT"), 5)
            return (urg, typ)

        sorted_tasks = sorted(unique_tasks, key=sort_key)

        # Clean internal task_key before returning public task schema
        cleaned_tasks: List[Dict[str, Any]] = []
        for t in sorted_tasks:
            t_copy = dict(t)
            t_copy.pop("task_key", None)
            cleaned_tasks.append(t_copy)

        return cleaned_tasks
