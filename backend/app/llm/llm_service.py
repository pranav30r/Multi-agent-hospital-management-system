"""
Unified LLM Service Adapter with Deterministic Clinical Fallback.

Provides a unified interface for:
1. Intake NLP extraction (symptoms, mentioned vitals, candidate acuity cues).
2. SBAR clinical handoff brief synthesis (Situation, Background, Assessment, Recommendation).
3. Discharge summary draft formulation (hospital course, medication reconciliation, precautions).

Features:
- Supports OpenAI-compatible chat-completions APIs (OpenAI, Groq) via httpx.AsyncClient.
- Deterministic provider priority: OPENAI > GROQ > DETERMINISTIC_FALLBACK.
- Strict 5.0-second outbound network timeout with zero unbounded retries.
- 100% offline deterministic fallback engine when API keys are absent or requests fail.
- Pure evaluation: NEVER mutates database records, encounters, tasks, or beds.
- Explicit clinical safety disclaimer and provenance tracking on all responses.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
import httpx

from app.config import settings
from app.utils.datetime_utils import utc_now_iso

logger = logging.getLogger(__name__)

# ─── Constants & Metadata ────────────────────────────────────────────────────

PROVIDER_OPENAI = "OPENAI"
PROVIDER_GROQ = "GROQ"
PROVIDER_FALLBACK = "DETERMINISTIC_FALLBACK"

DISCLAIMER_TEXT = "Draft AI clinical recommendation — Requires physician verification."
TIMEOUT_SECONDS = 5.0

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class LLMServiceError(RuntimeError):
    """Raised when an LLM operation fails and fallback is disabled."""
    pass


class LLMService:
    """
    Unified LLM Service with deterministic fallback for healthcare intelligence.
    
    Safe by design:
    - Never requires API credentials to initialize or use offline.
    - Operates purely in-memory; never writes to database.
    - Transparently falls back to deterministic extraction and drafting on network error.
    """

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        model: Optional[str] = None,
        enable_fallback: Optional[bool] = None,
    ):
        self._injected_client = http_client
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.OPENAI_API_KEY
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.GROQ_API_KEY
        self.model = model if model is not None else settings.LLM_MODEL
        self.enable_fallback = enable_fallback if enable_fallback is not None else settings.ENABLE_LLM_FALLBACK
        self.provider = self._select_provider()

    def _select_provider(self) -> Optional[str]:
        """
        Deterministic provider selection rule:
        1. If OpenAI API key is configured, prioritize OPENAI.
        2. Else if Groq API key is configured, select GROQ.
        3. Else, return None (uses DETERMINISTIC_FALLBACK).
        """
        if self.openai_api_key and str(self.openai_api_key).strip():
            return PROVIDER_OPENAI
        if self.groq_api_key and str(self.groq_api_key).strip():
            return PROVIDER_GROQ
        return None

    def _get_provider_details(self) -> tuple[str, str, str]:
        """Returns (provider_name, endpoint_url, api_key)."""
        if self.provider == PROVIDER_OPENAI:
            return (PROVIDER_OPENAI, OPENAI_ENDPOINT, str(self.openai_api_key).strip())
        elif self.provider == PROVIDER_GROQ:
            return (PROVIDER_GROQ, GROQ_ENDPOINT, str(self.groq_api_key).strip())
        raise LLMServiceError("No external LLM provider configured.")

    # ─── Outbound HTTP Chat Completion ───────────────────────────────────────

    async def _call_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1500
    ) -> Dict[str, Any]:
        """
        Executes outbound chat completion with strict 5-second timeout.
        Parses JSON from response content.
        Raises LLMServiceError on any network, timeout, HTTP, or format error.
        """
        provider_name, url, api_key = self._get_provider_details()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            if self._injected_client is not None:
                response = await self._injected_client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=TIMEOUT_SECONDS
                )
            else:
                async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS)) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMServiceError(f"{provider_name} request timed out after {TIMEOUT_SECONDS}s: {exc}") from exc
        except httpx.RequestError as exc:
            raise LLMServiceError(f"{provider_name} network request failure: {exc}") from exc
        except Exception as exc:
            raise LLMServiceError(f"Unexpected connection error contacting {provider_name}: {exc}") from exc

        if response.status_code != 200:
            raise LLMServiceError(
                f"{provider_name} returned non-200 HTTP status {response.status_code}: {response.text[:200]}"
            )

        try:
            res_data = response.json()
            content = res_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMServiceError(f"Malformed response envelope from {provider_name}: {exc}") from exc

        parsed = self._extract_json_from_content(content)
        if not isinstance(parsed, dict):
            raise LLMServiceError(f"Expected JSON object in {provider_name} output, got {type(parsed).__name__}")
        return parsed

    @staticmethod
    def _extract_json_from_content(content: str) -> Any:
        """Strips markdown formatting or code blocks and parses JSON."""
        content_clean = content.strip()
        if content_clean.startswith("```"):
            lines = content_clean.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content_clean = "\n".join(lines).strip()
        return json.loads(content_clean)

    # ─── 1. Intake NLP Extraction ────────────────────────────────────────────

    async def extract_intake_nlp(self, text: str) -> Dict[str, Any]:
        """
        Extracts presenting symptoms, mentioned vitals, and candidate acuity cues from patient intake text.
        Returns predictable, serializable dictionary with provenance metadata.
        """
        raw_text = text or ""
        if self.provider is not None:
            system_prompt = (
                "You are a clinical NLP intake information extraction assistant. "
                "Extract explicitly stated symptoms, vital signs, and candidate acuity indicators from the text. "
                "CRITICAL: Do NOT invent vital signs, medical diagnoses, or medications not stated in the text. "
                "Output ONLY a raw JSON object with keys: "
                "presenting_complaint (str), symptoms (list of str), "
                "vital_signs (dict with heart_rate, bp_systolic, bp_diastolic, spo2, temperature_f, respiratory_rate), "
                "pain_score (int or null), candidate_acuity_indicators (list of str), candidate_esi (int 1-5 or null), "
                "missing_information (list of str)."
            )
            user_prompt = f"Patient Intake Statement:\n\"\"\"{raw_text}\"\"\""
            try:
                parsed = await self._call_chat_completion(system_prompt, user_prompt)
                return self._format_intake_result(parsed, is_llm=True, provider=self.provider)
            except Exception as exc:
                logger.warning(f"External LLM extraction failed ({exc}); evaluating fallback policy.")
                if not self.enable_fallback:
                    raise exc

        # Deterministic Fallback Extraction
        if not self.enable_fallback and self.provider is None:
            raise LLMServiceError("No LLM provider configured and fallback is disabled.")

        return self._fallback_extract_intake_nlp(raw_text)

    def _fallback_extract_intake_nlp(self, text: str) -> Dict[str, Any]:
        """Transparent, deterministic regular expression and keyword extraction engine."""
        text_lower = text.lower().strip()

        # 1. Symptoms Detection Vocabulary
        symptom_patterns = [
            (r"\b(?:chest pain|angina|substernal pressure|chest tightness)\b", "Chest Pain / Discomfort"),
            (r"\b(?:shortness of breath|difficulty breathing|dyspnea|breathless|wheezing|stridor)\b", "Shortness of Breath"),
            (r"\b(?:fever|high temperature|pyrexia|chills|shivering)\b", "Fever / Chills"),
            (r"\b(?:cough|coughing|sputum|hemoptysis)\b", "Cough"),
            (r"\b(?:headache|migraine|head pain)\b", "Headache"),
            (r"\b(?:abdominal pain|stomach ache|belly pain|nausea|vomiting|diarrhea)\b", "Gastrointestinal Symptoms"),
            (r"\b(?:dizziness|lightheaded|syncope|fainting|passed out|vertigo)\b", "Dizziness / Syncope"),
            (r"\b(?:unresponsive|loss of consciousness|blackout|coma)\b", "Unresponsiveness / Altered Sensorium"),
            (r"\b(?:palpitation|palpitations|racing heart|rapid heartbeat)\b", "Palpitations"),
            (r"\b(?:weakness|fatigue|lethargy|numbness|tingling)\b", "Weakness / Numbness"),
            (r"\b(?:laceration|cut|bleeding|wound|trauma|injury|fracture|burn)\b", "Trauma / Acute Injury"),
            (r"\b(?:rash|hives|pruritus|swelling)\b", "Dermatologic / Allergic Symptoms"),
        ]

        detected_symptoms: List[str] = []
        for pattern, label in symptom_patterns:
            if re.search(pattern, text_lower):
                detected_symptoms.append(label)

        # 2. Vital Signs Extraction via Explicit Numeric Regexes
        vitals: Dict[str, Any] = {
            "heart_rate": None,
            "bp_systolic": None,
            "bp_diastolic": None,
            "spo2": None,
            "temperature_f": None,
            "respiratory_rate": None
        }

        # Heart Rate
        hr_match = re.search(r"\b(?:hr|pulse|heart rate)\s*[:=]?\s*(\d{2,3})\b", text_lower)
        if not hr_match:
            hr_match = re.search(r"\b(\d{2,3})\s*(?:bpm|beats/min)\b", text_lower)
        if hr_match:
            try:
                hr_val = int(hr_match.group(1))
                if 30 <= hr_val <= 250:
                    vitals["heart_rate"] = hr_val
            except (ValueError, TypeError):
                pass

        # Blood Pressure (Systolic / Diastolic)
        bp_match = re.search(r"\b(?:bp|blood pressure)\s*[:=]?\s*(\d{2,3})\s*[/]\s*(\d{2,3})\b", text_lower)
        if not bp_match:
            bp_match = re.search(r"\b(\d{2,3})\s*[/]\s*(\d{2,3})\s*(?:mmhg)?\b", text_lower)
        if bp_match:
            try:
                sys_val = int(bp_match.group(1))
                dia_val = int(bp_match.group(2))
                if 40 <= sys_val <= 300 and 20 <= dia_val <= 200:
                    vitals["bp_systolic"] = sys_val
                    vitals["bp_diastolic"] = dia_val
            except (ValueError, TypeError):
                pass

        # SpO2 Pulse Oximetry
        spo2_match = re.search(r"\b(?:spo2|pulse ox|o2 sat(?:uration)?)\s*[:=]?\s*(\d{1,3})\s*%?\b", text_lower)
        if not spo2_match:
            spo2_match = re.search(r"\b(\d{2,3})\s*%\s*(?:on room air|on ra|o2 sat|spo2)?\b", text_lower)
        if spo2_match:
            try:
                spo2_val = int(spo2_match.group(1))
                if 40 <= spo2_val <= 100:
                    vitals["spo2"] = spo2_val
            except (ValueError, TypeError):
                pass

        # Temperature
        temp_match = re.search(r"\b(?:temp(?:erature)?|fever)\s*(?:of|is|at|[:=])?\s*(\d{2,3}(?:\.\d)?)\s*(?:[°\s]?[FfCc])?\b", text_lower)
        if not temp_match:
            temp_match = re.search(r"\b(\d{2,3}(?:\.\d)?)\s*(?:°\s*[FfCc]|[°\s]?[Ff]\b)\b", text_lower)
        if temp_match:
            try:
                t_val = float(temp_match.group(1))
                # Check Fahrenheit or Celsius
                if 90.0 <= t_val <= 110.0:
                    vitals["temperature_f"] = round(t_val, 1)
                elif 32.0 <= t_val <= 43.0:
                    vitals["temperature_f"] = round((t_val * 9 / 5) + 32, 1)
            except (ValueError, TypeError):
                pass

        # Respiratory Rate
        rr_match = re.search(r"\b(?:rr|respiratory rate|resp rate)\s*[:=]?\s*(\d{1,2})\b", text_lower)
        if not rr_match:
            rr_match = re.search(r"\b(\d{1,2})\s*(?:breaths/min|breaths per min)\b", text_lower)
        if rr_match:
            try:
                rr_val = int(rr_match.group(1))
                if 4 <= rr_val <= 70:
                    vitals["respiratory_rate"] = rr_val
            except (ValueError, TypeError):
                pass

        # 3. Pain Score Extraction
        pain_score: Optional[int] = None
        pain_match = re.search(r"\b(?:pain|pain level|pain score|pain rating)\s*[:=]?\s*(\d{1,2})\s*(?:/\s*10)?\b", text_lower)
        if pain_match:
            try:
                p_val = int(pain_match.group(1))
                if 0 <= p_val <= 10:
                    pain_score = p_val
            except (ValueError, TypeError):
                pass

        # 4. Candidate Acuity Indicators (strictly non-definitive, labeled as candidates)
        candidate_indicators: List[str] = []
        candidate_esi: Optional[int] = None

        if "unresponsive" in text_lower or (vitals["bp_systolic"] and vitals["bp_systolic"] < 80):
            candidate_indicators.append("Candidate High Acuity: Signs of hemodynamic instability or altered responsiveness")
            candidate_esi = 1
        elif "chest pain" in text_lower or (vitals["spo2"] and vitals["spo2"] < 92) or (pain_score and pain_score >= 8):
            candidate_indicators.append("Candidate High Acuity: Acute chest pain or hypoxia or severe pain score")
            candidate_esi = 2
        elif len(detected_symptoms) >= 2 or (vitals["temperature_f"] and vitals["temperature_f"] >= 101.0):
            candidate_indicators.append("Candidate Moderate Acuity: Multiple systemic symptoms or significant fever")
            candidate_esi = 3
        elif detected_symptoms:
            candidate_indicators.append("Candidate Lower Acuity: Localized non-urgent symptoms")
            candidate_esi = 4
        else:
            candidate_esi = 5

        # 5. Missing Vital Signs Audit
        missing_info: List[str] = []
        if vitals["heart_rate"] is None:
            missing_info.append("Heart rate not explicitly stated")
        if vitals["bp_systolic"] is None:
            missing_info.append("Blood pressure not explicitly stated")
        if vitals["spo2"] is None:
            missing_info.append("Pulse oximetry (SpO2) not explicitly stated")
        if vitals["temperature_f"] is None:
            missing_info.append("Body temperature not explicitly stated")
        if vitals["respiratory_rate"] is None:
            missing_info.append("Respiratory rate not explicitly stated")

        # Presenting complaint summary
        presenting_complaint = text.strip() if text.strip() else "No intake statement provided"

        raw_result = {
            "presenting_complaint": presenting_complaint,
            "symptoms": detected_symptoms,
            "vital_signs": vitals,
            "pain_score": pain_score,
            "candidate_acuity_indicators": candidate_indicators,
            "candidate_esi": candidate_esi,
            "missing_information": missing_info
        }
        return self._format_intake_result(raw_result, is_llm=False, provider=PROVIDER_FALLBACK)

    def _format_intake_result(self, data: Dict[str, Any], is_llm: bool, provider: str) -> Dict[str, Any]:
        """Enforces schema consistency and appends required provenance metadata."""
        return {
            "presenting_complaint": data.get("presenting_complaint") or "Not reported",
            "symptoms": data.get("symptoms") or [],
            "vital_signs": data.get("vital_signs") or {
                "heart_rate": None,
                "bp_systolic": None,
                "bp_diastolic": None,
                "spo2": None,
                "temperature_f": None,
                "respiratory_rate": None
            },
            "pain_score": data.get("pain_score"),
            "candidate_acuity_indicators": data.get("candidate_acuity_indicators") or [],
            "candidate_esi": data.get("candidate_esi"),
            "missing_information": data.get("missing_information") or [],
            "is_llm_generated": bool(is_llm),
            "provider": provider,
            "disclaimer": DISCLAIMER_TEXT,
            "timestamp": utc_now_iso()
        }

    # ─── 2. SBAR Clinical Handoff Drafting ───────────────────────────────────

    async def generate_sbar_handoff(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesizes a structured SBAR (Situation, Background, Assessment, Recommendation)
        clinical handoff brief for inter-disciplinary physician/nursing handoffs.
        """
        ctx = context or {}
        if self.provider is not None:
            system_prompt = (
                "You are an expert hospital clinical coordinator assistant. "
                "Synthesize a structured SBAR (Situation, Background, Assessment, Recommendation) handoff brief. "
                "CRITICAL: Use ONLY supplied clinical facts. Mark missing fields as not documented. "
                "Output ONLY a raw JSON object with keys: "
                "situation (str), background (str), assessment (str), recommendation (str), missing_fields (list of str)."
            )
            user_prompt = f"Patient Clinical Handoff Context:\n{json.dumps(ctx, default=str, indent=2)}"
            try:
                parsed = await self._call_chat_completion(system_prompt, user_prompt)
                return self._format_sbar_result(parsed, is_llm=True, provider=self.provider)
            except Exception as exc:
                logger.warning(f"External LLM SBAR generation failed ({exc}); evaluating fallback.")
                if not self.enable_fallback:
                    raise exc

        # Deterministic Fallback Generation
        if not self.enable_fallback and self.provider is None:
            raise LLMServiceError("No LLM provider configured and fallback is disabled.")

        return self._fallback_generate_sbar_handoff(ctx)

    def _fallback_generate_sbar_handoff(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic SBAR synthesis strictly from supplied context without data fabrication."""
        patient_name = context.get("patient_name") or "Unspecified Patient"
        age = context.get("age")
        gender = context.get("gender") or "Unknown"
        age_str = f"{age}y/{gender}" if age is not None else f"Age unspecified/{gender}"
        complaint = context.get("chief_complaint") or context.get("presenting_complaint") or "No chief complaint recorded"
        acuity = context.get("acuity") or (f"ESI-{context.get('esi_level')}" if context.get("esi_level") else "Acuity unassigned")
        location = context.get("current_bed") or context.get("current_department") or "Holding / Triage"

        # Missing Fields Audit
        missing_fields: List[str] = []
        if not context.get("patient_name"):
            missing_fields.append("patient_name")
        if context.get("age") is None:
            missing_fields.append("age")
        if not context.get("chief_complaint"):
            missing_fields.append("chief_complaint")
        if not context.get("allergies"):
            missing_fields.append("allergies")
        if not context.get("vitals") and not context.get("heart_rate"):
            missing_fields.append("vital_signs")

        # ── S: Situation ──
        situation = (
            f"Patient {patient_name} ({age_str}) presenting with '{complaint}'. "
            f"Current clinical tier: {acuity}. Location: {location}."
        )

        # ── B: Background ──
        allergies = context.get("allergies") or ["None documented"]
        allergies_str = ", ".join(allergies) if isinstance(allergies, list) else str(allergies)
        pmh = context.get("chronic_conditions") or context.get("past_medical_history") or ["None documented"]
        pmh_str = ", ".join(pmh) if isinstance(pmh, list) else str(pmh)
        arrival = context.get("arrival_time") or "Time not recorded"
        background = (
            f"Arrival Time: {arrival}. Known Allergies: {allergies_str}. "
            f"Past Medical History / Chronic Conditions: {pmh_str}."
        )

        # ── A: Assessment ──
        vitals_obj = context.get("vitals") or {}
        hr = vitals_obj.get("heart_rate") or context.get("heart_rate") or "N/A"
        bp_s = vitals_obj.get("bp_systolic") or context.get("bp_systolic")
        bp_d = vitals_obj.get("bp_diastolic") or context.get("bp_diastolic")
        bp_str = f"{bp_s}/{bp_d}" if bp_s is not None and bp_d is not None else "N/A"
        spo2 = vitals_obj.get("spo2") or context.get("spo2") or "N/A"
        temp = vitals_obj.get("temperature_f") or context.get("temperature_f") or "N/A"
        rr = vitals_obj.get("respiratory_rate") or context.get("respiratory_rate") or "N/A"
        red_flags = context.get("red_flags") or []
        rf_str = f"Active Red Flags: {len(red_flags)} ({', '.join(str(f) for f in red_flags)})" if red_flags else "No acute red flags flagged"

        assessment = (
            f"Vitals: HR {hr} bpm, BP {bp_str} mmHg, SpO2 {spo2}%, Temp {temp}°F, RR {rr}/min. "
            f"Severity status: {context.get('severity', 'LOW')}. {rf_str}."
        )

        # ── R: Recommendation ──
        recs = context.get("recommendations") or context.get("pending_tasks") or []
        if isinstance(recs, list) and recs:
            rec_items = "; ".join(r.get("title", str(r)) if isinstance(r, dict) else str(r) for r in recs)
            recommendation = (
                f"Proposed clinical plan (Subject to clinician verification): {rec_items}. "
                f"Assigned team: Doctor {context.get('assigned_doctor', 'Pending')}, Nurse {context.get('assigned_nurse', 'Pending')}."
            )
        else:
            recommendation = (
                "Conduct primary clinician examination, verify vital sign stability, and obtain complete nursing intake. "
                "Draft recommendation requires attending physician sign-off."
            )

        raw_result = {
            "situation": situation,
            "background": background,
            "assessment": assessment,
            "recommendation": recommendation,
            "missing_fields": missing_fields
        }
        return self._format_sbar_result(raw_result, is_llm=False, provider=PROVIDER_FALLBACK)

    def _format_sbar_result(self, data: Dict[str, Any], is_llm: bool, provider: str) -> Dict[str, Any]:
        """Enforces schema consistency and appends required provenance metadata."""
        return {
            "situation": data.get("situation") or "Situation not documented",
            "background": data.get("background") or "Background not documented",
            "assessment": data.get("assessment") or "Assessment not documented",
            "recommendation": data.get("recommendation") or "Recommendation pending physician review",
            "missing_fields": data.get("missing_fields") or [],
            "is_llm_generated": bool(is_llm),
            "provider": provider,
            "disclaimer": DISCLAIMER_TEXT,
            "timestamp": utc_now_iso()
        }

    # ─── 3. Discharge Summary Drafting ───────────────────────────────────────

    async def generate_discharge_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formulates a structured discharge summary draft (hospital course, prescriptions, precautions).
        All recommendations are strictly drafts requiring authorized physician signature.
        """
        ctx = context or {}
        if self.provider is not None:
            system_prompt = (
                "You are an assistant for physician discharge summary drafting. "
                "Synthesize a structured clinical discharge summary draft from the supplied stay context. "
                "CRITICAL: Do NOT fabricate diagnoses, medication dosages, or treatments not documented in the input. "
                "Output ONLY a raw JSON object with keys: "
                "encounter_summary (str), documented_diagnoses (list of str), "
                "treatment_and_hospital_course (str), medication_reconciliation (list of str), "
                "follow_up_instructions (str), urgent_warning_signs (list of str), "
                "clinician_completion_checklist (list of str)."
            )
            user_prompt = f"Hospital Stay Discharge Context:\n{json.dumps(ctx, default=str, indent=2)}"
            try:
                parsed = await self._call_chat_completion(system_prompt, user_prompt)
                return self._format_discharge_result(parsed, is_llm=True, provider=self.provider)
            except Exception as exc:
                logger.warning(f"External LLM discharge summary failed ({exc}); evaluating fallback.")
                if not self.enable_fallback:
                    raise exc

        # Deterministic Fallback Generation
        if not self.enable_fallback and self.provider is None:
            raise LLMServiceError("No LLM provider configured and fallback is disabled.")

        return self._fallback_generate_discharge_summary(ctx)

    def _fallback_generate_discharge_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic discharge summary synthesis with zero ungrounded clinical claims."""
        patient_name = context.get("patient_name") or "Patient"
        encounter_id = context.get("encounter_id") or "ENC-UNSPECIFIED"
        dept = context.get("department") or context.get("current_department_id") or "Hospital General Ward"
        complaint = context.get("chief_complaint") or "Not recorded"
        adm_date = context.get("admission_date") or context.get("arrival_time") or "Arrival date unrecorded"
        dis_date = context.get("discharge_date") or utc_now_iso()

        # 1. Encounter Summary
        encounter_summary = (
            f"Discharge summary draft for {patient_name} (Encounter: {encounter_id}). "
            f"Treated in {dept}. Admitted: {adm_date}. Discharge disposition initiated: {dis_date}. "
            f"Primary presenting chief complaint was '{complaint}'."
        )

        # 2. Diagnoses (Strictly documented, never fabricated)
        raw_dx = context.get("diagnoses") or context.get("diagnosed_diseases") or []
        if isinstance(raw_dx, list) and raw_dx:
            documented_diagnoses = [str(d) for d in raw_dx]
        elif isinstance(raw_dx, str) and raw_dx.strip():
            documented_diagnoses = [raw_dx.strip()]
        else:
            documented_diagnoses = ["Primary clinical diagnosis pending attending physician completion"]

        # 3. Treatment and Hospital Course
        treatments = context.get("treatment_summary") or context.get("procedures_performed") or []
        if isinstance(treatments, list) and treatments:
            treatment_course = f"Hospital Course & Interventions: {'; '.join(str(t) for t in treatments)}."
        elif isinstance(treatments, str) and treatments.strip():
            treatment_course = f"Hospital Course & Interventions: {treatments.strip()}."
        else:
            treatment_course = (
                "Hospital course completed in accordance with clinical protocol. "
                "Detailed procedural notes pending attending physician documentation."
            )

        # 4. Medication Reconciliation
        meds = context.get("discharge_medications") or context.get("prescriptions") or []
        if isinstance(meds, list) and meds:
            medication_reconciliation = [
                f"{m.get('name', 'Medication')} - {m.get('dosage', 'Per order')} ({m.get('instructions', 'Take as directed')})"
                if isinstance(m, dict) else str(m)
                for m in meds
            ]
        elif isinstance(meds, str) and meds.strip():
            medication_reconciliation = [meds.strip()]
        else:
            medication_reconciliation = ["No outpatient discharge prescriptions documented; pharmacist reconciliation required."]

        # 5. Follow-Up Instructions
        follow_up = context.get("follow_up_instructions") or (
            "Schedule follow-up outpatient consultation within 7-10 days or contact your primary healthcare provider."
        )

        # 6. Urgent Return Precautions / Warning Signs
        urgent_warning_signs = [
            "Severe or worsening shortness of breath or difficulty breathing",
            "Acute chest pain, pressure, or radiating arm/jaw discomfort",
            "Persistent high fever exceeding 101°F (38.3°C) or severe chills",
            "Sudden numbness, facial droop, slurred speech, or weakness",
            "Uncontrolled bleeding, intractable vomiting, or inability to tolerate oral fluids",
            "Any sudden clinical deterioration requiring immediate emergency department presentation"
        ]

        # 7. Clinician Completion Checklist
        checklist: List[str] = []
        if not context.get("diagnoses") and not context.get("diagnosed_diseases"):
            checklist.append("Record final ICD/clinical diagnosis")
        if not context.get("discharge_medications") and not context.get("prescriptions"):
            checklist.append("Confirm outpatient medication list and allergy reconciliation")
        if not context.get("follow_up_instructions"):
            checklist.append("Specify exact outpatient follow-up appointment date and clinic")
        checklist.append("Attending physician electronic signature and authorization")

        raw_result = {
            "encounter_summary": encounter_summary,
            "documented_diagnoses": documented_diagnoses,
            "treatment_and_hospital_course": treatment_course,
            "medication_reconciliation": medication_reconciliation,
            "follow_up_instructions": follow_up,
            "urgent_warning_signs": urgent_warning_signs,
            "clinician_completion_checklist": checklist
        }
        return self._format_discharge_result(raw_result, is_llm=False, provider=PROVIDER_FALLBACK)

    def _format_discharge_result(self, data: Dict[str, Any], is_llm: bool, provider: str) -> Dict[str, Any]:
        """Enforces schema consistency and appends required provenance metadata."""
        return {
            "encounter_summary": data.get("encounter_summary") or "Encounter summary not documented",
            "documented_diagnoses": data.get("documented_diagnoses") or ["Pending clinician completion"],
            "treatment_and_hospital_course": data.get("treatment_and_hospital_course") or "Hospital course not documented",
            "medication_reconciliation": data.get("medication_reconciliation") or ["Reconciliation pending"],
            "follow_up_instructions": data.get("follow_up_instructions") or "Follow-up instructions pending",
            "urgent_warning_signs": data.get("urgent_warning_signs") or [],
            "clinician_completion_checklist": data.get("clinician_completion_checklist") or ["Attending physician sign-off"],
            "is_llm_generated": bool(is_llm),
            "provider": provider,
            "disclaimer": DISCLAIMER_TEXT,
            "timestamp": utc_now_iso()
        }
