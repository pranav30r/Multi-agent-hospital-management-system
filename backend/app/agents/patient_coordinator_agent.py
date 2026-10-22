"""
Autonomous Patient Care Coordinator & Clinical Handoff Agent.
Synthesizes intake context, diagnostic investigation statuses, and discharge readiness
to formulate structured physician handoff briefs and patient continuity recommendations.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.clinical_document import ClinicalDocument
from app.utils.datetime_utils import utc_now_iso
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PatientCoordinatorAgent(BaseAgent):
    """
    Autonomous Patient Care Coordinator & Clinical Handoff Agent.
    Synthesizes intake context, diagnostic investigation statuses, and discharge readiness
    to formulate structured physician handoff briefs and patient continuity recommendations.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db=db, agent_id="patient_coordinator_agent", name="Patient Care Coordinator Agent")
        from app.services.clinical_summary_service import ClinicalSummaryService
        self.summary_service = ClinicalSummaryService()

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        staff_output: Dict[str, Any],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Synthesizes clinical handoff context, missing clinical information, and care continuity instructions.
        """
        # 1. Fetch recent clinical documents if present
        doc_stmt = (
            select(ClinicalDocument)
            .where(ClinicalDocument.patient_id == patient.id)
            .order_by(ClinicalDocument.created_at.desc())
            .limit(3)
        )
        doc_res = await self.db.execute(doc_stmt)
        recent_docs = doc_res.scalars().all()

        # 2. Check for missing vital or clinical intake parameters
        missing_info = []
        if encounter.bp_systolic is None:
            missing_info.append("Blood Pressure Measurement")
        if encounter.spo2 is None:
            missing_info.append("Pulse Oximetry (SpO2)")
        if encounter.temperature_f is None:
            missing_info.append("Body Temperature")
        if not patient.allergies:
            missing_info.append("Patient Drug Allergy Verification")

        # 3. Formulate Clinical Handoff Summary
        care_level = triage_output.get("recommended_care_level", "GENERAL")
        esi = triage_output.get("esi_level", 3)
        doc_id = staff_output.get("assigned_doctor_id")
        nurse_id = staff_output.get("assigned_nurse_id")
        target_bed = bed_output.get("recommended_bed_id")

        handoff_brief = {
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "age_gender": f"{patient.age}y/{patient.gender}",
            "chief_complaint": encounter.chief_complaint,
            "acuity": f"ESI-{esi} ({triage_output.get('priority_level')})",
            "assigned_team": f"Doctor: {doc_id or 'Pending'}, Nurse: {nurse_id or 'Pending'}",
            "allocated_bed": target_bed or "Holding Area",
            "active_allergies": patient.allergies or ["None Documented"],
            "chronic_conditions": patient.chronic_conditions or ["None Documented"],
            "recent_documents_count": len(recent_docs)
        }

        # 4. Discharge / Step-Down Readiness Assessment
        discharge_readiness = (
            care_level == "OUTPATIENT" or
            (esi == 5 and triage_output.get("severity") == "LOW" and len(triage_output.get("red_flags", [])) == 0)
        )

        # Formulate structured discharge or step-down proposal if eligible
        discharge_stepdown_proposal = None
        if discharge_readiness:
            discharge_stepdown_proposal = {
                "transition_type": "OUTPATIENT_DISCHARGE",
                "proposed_destination": "DEP-OPD",
                "clinical_readiness": True,
                "requires_telemetry": False,
                "requires_isolation": False,
                "time_window": "ROUTINE",
                "rationale": "Patient clinically stable for standard outpatient discharge."
            }
        elif care_level in ["GENERAL", "MODERATE"] or (encounter.current_department_id in ["DEP-ICU", "DEP-EMERGENCY"] and triage_output.get("severity") not in ["CRITICAL"]):
            target_dept = "DEP-WA"
            discharge_stepdown_proposal = {
                "transition_type": "STEP_DOWN_TRANSFER",
                "proposed_destination": target_dept,
                "clinical_readiness": True,
                "requires_telemetry": triage_output.get("requires_telemetry", False),
                "requires_isolation": triage_output.get("requires_isolation", False),
                "time_window": "IMMEDIATE" if triage_output.get("priority_level") in ["HIGH", "CRITICAL"] else "ROUTINE",
                "rationale": f"Patient stable for step-down general ward transfer to {target_dept}."
            }

        coordination_recommendations = []
        if discharge_readiness:
            coordination_recommendations.append("Prepare standard outpatient prescription & follow-up instructions")
        else:
            coordination_recommendations.append(f"Execute nursing intake transfer to {bed_output.get('recommended_department_id')}")
            if triage_output.get("requires_telemetry"):
                coordination_recommendations.append("Initiate continuous cardiac & SpO2 telemetry recording")
            if missing_info:
                coordination_recommendations.append(f"Obtain pending clinical inputs: {', '.join(missing_info)}")

        rationale = (
            f"Care Coordination Profile: Handoff prepared for {doc_id or 'attending staff'}. "
            f"Discharge Readiness: {discharge_readiness}. Missing Parameters: {len(missing_info)}."
        )

        return {
            "agent_id": "patient_coordinator_agent",
            "status": "COMPLETED",
            "handoff_brief": handoff_brief,
            "discharge_readiness": discharge_readiness,
            "discharge_stepdown_proposal": discharge_stepdown_proposal,
            "missing_clinical_info": missing_info,
            "coordination_recommendations": coordination_recommendations,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def propose_discharge_or_stepdown(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        staff_output: Dict[str, Any],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Formulates a structured discharge or step-down proposal for Bed Management evaluation.
        """
        care_level = triage_output.get("recommended_care_level", "GENERAL")
        esi = triage_output.get("esi_level", 3)
        severity = triage_output.get("severity", "LOW")

        discharge_readiness = (
            care_level == "OUTPATIENT" or
            (esi == 5 and severity == "LOW" and len(triage_output.get("red_flags", [])) == 0)
        )

        if discharge_readiness:
            trans_type = "OUTPATIENT_DISCHARGE"
            dest = "DEP-OPD"
        else:
            trans_type = "STEP_DOWN_TRANSFER"
            dest = "DEP-WA"

        return {
            "agent_id": "patient_coordinator_agent",
            "message_type": "PROPOSAL",
            "transition_type": trans_type,
            "proposed_destination": dest,
            "clinical_readiness": True,
            "requires_telemetry": triage_output.get("requires_telemetry", False),
            "requires_isolation": triage_output.get("requires_isolation", False),
            "time_window": "IMMEDIATE" if triage_output.get("priority_level") in ["HIGH", "CRITICAL"] else "ROUTINE",
            "rationale": f"Propose {trans_type} to destination department {dest} with continuous care monitoring.",
            "timestamp": utc_now_iso()
        }

    async def evaluate_bed_response(
        self,
        bed_response: Dict[str, Any],
        triage_output: Dict[str, Any],
        encounter: Encounter
    ) -> Dict[str, Any]:
        """
        Evaluates the Bed Manager's response to the discharge/step-down transfer proposal.
        Accepts clinically compatible destinations or counter-proposals; rejects/escalates incompatible alternatives.
        """
        decision = bed_response.get("decision", "REJECT")
        req_telem = triage_output.get("requires_telemetry", False)
        req_iso = triage_output.get("requires_isolation", False)

        if decision == "ACCEPT":
            return {
                "agent_id": "patient_coordinator_agent",
                "message_type": "ACCEPT",
                "negotiated_destination": bed_response.get("allocated_bed_id") or bed_response.get("department_id"),
                "negotiated_department_id": bed_response.get("department_id"),
                "rationale": f"Patient Coordinator accepts bed assignment {bed_response.get('allocated_bed_id')} in {bed_response.get('department_id')}.",
                "timestamp": utc_now_iso()
            }
        elif decision == "COUNTER_PROPOSAL":
            # Check clinical compatibility of counter-proposed bed/department
            counter_telem = bed_response.get("has_telemetry", False)
            counter_iso = bed_response.get("is_isolation", False)

            incompatible_reasons = []
            if req_iso and not counter_iso:
                incompatible_reasons.append("counter-proposed bed lacks required infection isolation barrier")
            if req_telem and not counter_telem and bed_response.get("counter_bed_type") not in ["ICU", "CARDIAC_MONITOR"]:
                incompatible_reasons.append("counter-proposed bed lacks required continuous telemetry monitor")

            if incompatible_reasons:
                return {
                    "agent_id": "patient_coordinator_agent",
                    "message_type": "ESCALATION",
                    "counter_decision": "REJECT",
                    "rationale": f"Patient Coordinator rejects counter-proposal: {'; '.join(incompatible_reasons)}. Escalating to Coordinator.",
                    "timestamp": utc_now_iso()
                }
            else:
                return {
                    "agent_id": "patient_coordinator_agent",
                    "message_type": "ACCEPT",
                    "counter_decision": "ACCEPT",
                    "negotiated_destination": bed_response.get("counter_bed_id"),
                    "negotiated_department_id": bed_response.get("counter_department_id"),
                    "rationale": f"Patient Coordinator accepts clinically compatible alternative bed {bed_response.get('counter_bed_id')} in {bed_response.get('counter_department_id')}.",
                    "timestamp": utc_now_iso()
                }
        else:
            return {
                "agent_id": "patient_coordinator_agent",
                "message_type": "ESCALATION",
                "counter_decision": "REJECT",
                "rationale": f"Patient Coordinator step-down request rejected by Bed Manager ({bed_response.get('rationale')}). Escalating to Coordinator.",
                "timestamp": utc_now_iso()
            }

    async def draft_sbar_handoff(
        self,
        encounter: Encounter,
        patient: Patient,
        triage_output: Optional[Dict[str, Any]] = None,
        llm_service: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Drafts a structured SBAR clinical handoff brief using LLMService.
        Pure recommendation: non-destructive.
        """
        from app.llm import LLMService
        service = llm_service or LLMService()
        t_out = triage_output or {}
        context = {
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "age": patient.age,
            "gender": patient.gender,
            "chief_complaint": encounter.chief_complaint,
            "esi_level": encounter.esi_level or t_out.get("esi_level"),
            "severity": t_out.get("severity", "LOW"),
            "current_department": encounter.current_department_id,
            "current_bed": encounter.current_bed_id,
            "allergies": patient.allergies or [],
            "chronic_conditions": patient.chronic_conditions or [],
            "heart_rate": encounter.heart_rate,
            "bp_systolic": encounter.bp_systolic,
            "bp_diastolic": encounter.bp_diastolic,
            "spo2": encounter.spo2,
            "temperature_f": encounter.temperature_f,
            "respiratory_rate": encounter.respiratory_rate,
            "red_flags": t_out.get("red_flags") or []
        }
        return await service.generate_sbar_handoff(context)
