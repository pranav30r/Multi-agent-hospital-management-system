"""
Central Hospital Multi-Agent Workflow Coordinator.

Coordinates the 5 specialized hospital operational agents in a defined order:
1. Intake & Triage (TriageAgent -> TriageResult)
2. Patient Flow (PatientCoordinatorAgent & ClinicalWorkflowAgent -> PatientFlowResult)
3. Bed & Resource Matching (BedManagerAgent -> ResourceMatchResult)
4. Workforce & Staffing (StaffSchedulerAgent -> WorkforceAssessment)
5. Escalation & Safety (EmergencyEscalationAgent & RiskEngine -> EscalationResult)

Produces a unified, typed ConsolidatedRecommendation and HospitalWorkflowState,
enforces strict Human-in-the-Loop approval barriers, prevents unauthorized resource
mutations, handles conditional routing, and integrates with the backend audit and event bus.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.department import Department
from app.models.staff import Staff
from app.models.emergency import EmergencyEvent
from app.models.agent import AgentDecision, ApprovalItem, OptimizationRun
from app.utils.datetime_utils import utc_now_iso

from app.agents.triage_agent import TriageAgent
from app.agents.bed_agent import BedManagerAgent
from app.agents.staff_agent import StaffSchedulerAgent
from app.agents.emergency_agent import EmergencyEscalationAgent
from app.agents.patient_coordinator_agent import PatientCoordinatorAgent
from app.agents.workflow_agent import ClinicalWorkflowAgent
from app.agents.coordinator_agent import CoordinatorAgent
from app.services.risk_engine import RiskEngine
from app.services.events import event_bus

from app.schemas.hospital_workflow import (
    TriageResult,
    PatientFlowResult,
    ResourceMatchResult,
    WorkforceAssessment,
    EscalationResult,
    ConsolidatedRecommendation,
    HospitalWorkflowState,
)

logger = logging.getLogger(__name__)


class HospitalWorkflowCoordinator:
    """
    Central workflow coordinator orchestrating all hospital AI agents
    with typed state, strict conditional routing, and human approval safeguards.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.triage_agent = TriageAgent(db)
        self.flow_agent = PatientCoordinatorAgent(db)
        self.clinical_workflow_agent = ClinicalWorkflowAgent(db)
        self.bed_agent = BedManagerAgent(db)
        self.staff_agent = StaffSchedulerAgent(db)
        self.emergency_agent = EmergencyEscalationAgent(db)
        self.coordinator_agent = CoordinatorAgent(db)
        self.risk_engine = RiskEngine()

    async def coordinate_workflow(
        self,
        encounter_id: str,
        tenant_id: str = "HOSP-DEFAULT",
        actor_id: str = "SYSTEM",
        correlation_id: Optional[str] = None,
        force_recalculate: bool = False,
        trigger_reason: Optional[str] = None
    ) -> HospitalWorkflowState:
        """
        Executes the end-to-end 10-step multi-agent hospital management workflow.
        """
        workflow_id = str(uuid.uuid4())
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        now_iso = utc_now_iso()

        warnings: List[str] = []
        missing_info: List[str] = []
        agent_errors: List[Dict[str, Any]] = []

        # ─── STEP 1: Load & Validate Encounter and Hospital State Snapshot ───
        enc_stmt = select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        enc_res = await self.db.execute(enc_stmt)
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Encounter '{encounter_id}' not found."
            )

        # Fetch Patient
        pat_stmt = select(Patient).where(Patient.id == encounter.patient_id)
        pat_res = await self.db.execute(pat_stmt)
        patient = pat_res.scalars().first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient '{encounter.patient_id}' not found for encounter '{encounter_id}'."
            )

        # Enforce Tenant Boundary
        enc_tenant = getattr(patient, "tenant_id", None) or "HOSP-DEFAULT"
        if enc_tenant != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tenant mismatch: Encounter belongs to '{enc_tenant}', requested by '{tenant_id}'."
            )

        # Idempotency: Return existing active decision if not forcing recalculation
        if not force_recalculate:
            existing_dec_res = await self.db.execute(
                select(AgentDecision)
                .where(
                    AgentDecision.encounter_id == encounter_id,
                    AgentDecision.status.in_(["PROPOSED", "PENDING", "APPROVED"])
                )
                .order_by(AgentDecision.created_at.desc())
            )
            existing_dec = existing_dec_res.scalars().first()
            if existing_dec:
                appr_res = await self.db.execute(
                    select(ApprovalItem).where(ApprovalItem.decision_id == existing_dec.id)
                )
                appr_item = appr_res.scalars().first()

                logger.info(f"Idempotent: Returning existing workflow decision {existing_dec.id} for encounter {encounter_id}")
                return await self._build_state_from_existing_decision(
                    existing_dec=existing_dec,
                    appr_item=appr_item,
                    encounter=encounter,
                    patient=patient,
                    tenant_id=tenant_id,
                    correlation_id=corr_id
                )

        # Capture Point-in-Time Encounter Snapshot
        encounter_snapshot = {
            "id": encounter.id,
            "patient_id": patient.id,
            "tenant_id": enc_tenant,
            "chief_complaint": encounter.chief_complaint,
            "esi_level": encounter.esi_level,
            "patient_status": encounter.patient_status,
            "current_bed_id": encounter.current_bed_id,
            "vitals": {
                "heart_rate": encounter.heart_rate,
                "bp_systolic": encounter.bp_systolic,
                "bp_diastolic": encounter.bp_diastolic,
                "spo2": encounter.spo2,
                "temperature_f": encounter.temperature_f,
                "respiratory_rate": encounter.respiratory_rate,
                "gcs_score": encounter.gcs_score,
            },
            "created_at": str(getattr(encounter, "arrival_time", None) or getattr(encounter, "created_at", None) or now_iso)
        }

        # Capture Point-in-Time Hospital Capacity Snapshot (tenant isolated)
        bed_base = select(Bed).join(Department, Bed.department_id == Department.id).where(Department.tenant_id == enc_tenant)
        total_beds = (await self.db.execute(select(func.count()).select_from(bed_base.subquery()))).scalar() or 0
        avail_beds = (await self.db.execute(select(func.count()).select_from(bed_base.where(Bed.status == "AVAILABLE").subquery()))).scalar() or 0
        occupied_beds = (await self.db.execute(select(func.count()).select_from(bed_base.where(Bed.status == "OCCUPIED").subquery()))).scalar() or 0
        active_staff = (await self.db.execute(
            select(func.count(Staff.id)).where(and_(Staff.tenant_id == enc_tenant, Staff.status.in_(["AVAILABLE", "BUSY"])))
        )).scalar() or 0
        active_emergencies = (await self.db.execute(
            select(func.count(EmergencyEvent.id)).where(and_(EmergencyEvent.tenant_id == enc_tenant, EmergencyEvent.status == "ACTIVE"))
        )).scalar() or 0

        hospital_state_snapshot = {
            "timestamp": now_iso,
            "total_beds": total_beds,
            "available_beds": avail_beds,
            "occupied_beds": occupied_beds,
            "active_staff_count": active_staff,
            "active_emergencies_count": active_emergencies
        }

        # ─── STEP 2: Run Agent A (Intake & Triage) ───────────────────────────
        triage_result: Optional[TriageResult] = None
        triage_raw: Dict[str, Any] = {}
        try:
            triage_raw = await self.triage_agent.evaluate(encounter, patient, actor_id=actor_id)
            
            # Check for missing clinical intake parameters
            triage_missing = list(triage_raw.get("missing_information") or [])
            if not encounter.chief_complaint:
                triage_missing.append("Chief Complaint")
            if encounter.heart_rate is None and encounter.bp_systolic is None and encounter.spo2 is None:
                triage_missing.append("Initial Baseline Vitals")
            if not patient.allergies:
                triage_missing.append("Patient Allergies Record")

            triage_result = TriageResult(
                agent_id="triage_agent",
                esi_level=int(triage_raw.get("esi_level") or encounter.esi_level or 3),
                priority_level=str(triage_raw.get("priority_level") or "MODERATE"),
                severity=str(triage_raw.get("severity") or "LOW"),
                score=float(triage_raw.get("score") or 0.0),
                red_flags=list(triage_raw.get("red_flags") or []),
                recommended_care_level=str(triage_raw.get("recommended_care_level") or "GENERAL"),
                clinical_urgency=str(triage_raw.get("clinical_urgency") or "STANDARD"),
                requires_telemetry=bool(triage_raw.get("requires_telemetry")),
                requires_isolation=bool(triage_raw.get("requires_isolation")),
                missing_information=triage_missing,
                rationale=str(triage_raw.get("rationale") or "Deterministic triage assessment"),
                timestamp=str(triage_raw.get("timestamp") or now_iso)
            )
            missing_info.extend(triage_missing)
        except Exception as e:
            logger.exception(f"TriageAgent failed for encounter {encounter_id}: {e}")
            agent_errors.append({"agent": "triage_agent", "error": str(e)})
            warnings.append(f"Triage assessment failed: {e}")
            triage_result = TriageResult(
                agent_id="triage_agent",
                esi_level=int(encounter.esi_level or 3),
                priority_level="ROUTINE",
                severity="LOW",
                score=0.0,
                recommended_care_level="GENERAL",
                clinical_urgency="STANDARD",
                rationale="Fallback triage due to agent exception",
                timestamp=now_iso
            )
            triage_raw = triage_result.model_dump()

        # ─── STEP 3: Validate Triage Result & Conditional Branching ──────────
        is_critical_decompensation = (
            triage_result.esi_level == 1 or
            triage_result.severity in ["CRITICAL", "HIGH"] or
            (encounter.bp_systolic is not None and encounter.bp_systolic <= 85) or
            (encounter.spo2 is not None and encounter.spo2 <= 88)
        )
        if is_critical_decompensation:
            warnings.append("Critical physiological risk identified: immediate resuscitation required.")

        has_severe_missing_data = "Chief Complaint" in missing_info and "Initial Baseline Vitals" in missing_info
        if has_severe_missing_data:
            warnings.append("Critical intake data missing: patient has neither chief complaint nor vitals.")

        # ─── STEP 4: Run Agent B (Patient Flow) ──────────────────────────────
        patient_flow_result: Optional[PatientFlowResult] = None
        patient_flow_raw: Dict[str, Any] = {}
        try:
            flow_eval = await self.flow_agent.evaluate(
                triage_output=triage_raw,
                bed_output={},
                staff_output={},
                encounter=encounter,
                patient=patient,
                tenant_id=tenant_id
            )
            patient_flow_raw = flow_eval

            # Map protocol from ClinicalWorkflowAgent if available
            protocol_name = None
            try:
                wf_eval = await self.clinical_workflow_agent.evaluate(
                    triage_output=triage_raw,
                    encounter=encounter,
                    patient=patient,
                    tenant_id=tenant_id,
                    actor_id=actor_id
                )
                protocol_name = wf_eval.get("protocol_name")
            except Exception as wf_err:
                logger.debug(f"Workflow agent optional protocol mapping skipped: {wf_err}")

            target_dept = "DEP-ICU" if triage_result.recommended_care_level == "ICU" else "DEP-ER" if triage_result.recommended_care_level == "EMERGENCY" else "DEP-GEN"
            next_steps = [
                f"Admit patient to {target_dept}",
                "Initiate continuous vitals monitoring",
                "Assign primary attending physician and bedside nurse"
            ]
            if is_critical_decompensation:
                next_steps.insert(0, "Prepare resuscitation bay & rapid response team")

            patient_flow_result = PatientFlowResult(
                agent_id="patient_coordinator_agent",
                current_stage=encounter.patient_status or "TRIAGE",
                target_department=target_dept,
                recommended_protocol=protocol_name,
                next_operational_steps=next_steps,
                missing_prerequisites=flow_eval.get("missing_information", []),
                transfer_requirements=["Continuous telemetry escort"] if triage_result.requires_telemetry else ["Wheelchair or standard transport"],
                flow_bottlenecks=flow_eval.get("flow_bottlenecks", []),
                handoff_brief=flow_eval.get("clinical_handoff_brief", {}),
                rationale=f"Routing patient to {target_dept} based on ESI-{triage_result.esi_level} urgency.",
                timestamp=now_iso
            )
        except Exception as e:
            logger.exception(f"PatientCoordinatorAgent failed for encounter {encounter_id}: {e}")
            agent_errors.append({"agent": "patient_coordinator_agent", "error": str(e)})
            patient_flow_result = PatientFlowResult(
                agent_id="patient_coordinator_agent",
                target_department="DEP-ER",
                next_operational_steps=["Manual clinical intake assessment"],
                rationale=f"Fallback routing: {e}",
                timestamp=now_iso
            )

        # ─── STEP 5: Run Agent C (Bed & Resource Matching) ───────────────────
        resource_match_result: Optional[ResourceMatchResult] = None
        bed_raw: Dict[str, Any] = {}
        try:
            bed_raw = await self.bed_agent.evaluate(
                triage_output=triage_raw,
                encounter=encounter,
                tenant_id=tenant_id
            )
            candidate_list = bed_raw.get("candidate_beds") or []
            cand_ids = [b.get("id") if isinstance(b, dict) else str(b) for b in candidate_list]
            alt_list = [str(a) for a in (bed_raw.get("alternative_beds") or [])]

            feasibility = str(bed_raw.get("feasibility") or "FEASIBLE")
            if feasibility == "UNAVAILABLE":
                warnings.append("Primary matching bed is unavailable in the requested care department.")

            resource_match_result = ResourceMatchResult(
                agent_id="bed_manager_agent",
                recommended_bed_id=bed_raw.get("recommended_bed_id"),
                recommended_department_id=bed_raw.get("recommended_department_id") or patient_flow_result.target_department,
                bed_type=bed_raw.get("bed_type"),
                feasibility=feasibility,
                candidate_beds=cand_ids,
                alternative_beds=alt_list,
                rejected_constraints=bed_raw.get("rejected_constraints", []),
                confidence=float(bed_raw.get("confidence") or 0.88),
                rationale=str(bed_raw.get("rationale") or f"Matched bed {bed_raw.get('recommended_bed_id')} based on clinical tier"),
                timestamp=now_iso
            )
        except Exception as e:
            logger.exception(f"BedManagerAgent failed for encounter {encounter_id}: {e}")
            agent_errors.append({"agent": "bed_manager_agent", "error": str(e)})
            warnings.append(f"Bed resource matching failed: {e}")
            resource_match_result = ResourceMatchResult(
                agent_id="bed_manager_agent",
                feasibility="UNAVAILABLE",
                rationale=f"Bed evaluation error: {e}",
                timestamp=now_iso
            )
            bed_raw = resource_match_result.model_dump()

        # ─── STEP 6: Run Agent D (Workforce & Staffing) ──────────────────────
        workforce_assessment: Optional[WorkforceAssessment] = None
        staff_raw: Dict[str, Any] = {}
        try:
            staff_raw = await self.staff_agent.evaluate(
                triage_output=triage_raw,
                bed_output=bed_raw,
                encounter=encounter,
                tenant_id=tenant_id
            )
            is_data_available = bool(active_staff > 0)
            feasibility = str(staff_raw.get("feasibility") or "FEASIBLE") if is_data_available else "DATA_UNAVAILABLE"

            if not is_data_available:
                warnings.append("Hospital workforce roster data is currently unavailable.")

            workforce_assessment = WorkforceAssessment(
                agent_id="staff_scheduler_agent",
                assigned_doctor_id=staff_raw.get("assigned_doctor_id"),
                assigned_nurse_id=staff_raw.get("assigned_nurse_id"),
                feasibility=feasibility,
                shortages_detected=staff_raw.get("shortages", []),
                coverage_constraints=staff_raw.get("constraints", []),
                alternative_staff=staff_raw.get("alternative_staff", []),
                workforce_data_available=is_data_available,
                rationale=str(staff_raw.get("rationale") or "Clinical workforce workload evaluated"),
                timestamp=now_iso
            )
        except Exception as e:
            logger.exception(f"StaffSchedulerAgent failed for encounter {encounter_id}: {e}")
            agent_errors.append({"agent": "staff_scheduler_agent", "error": str(e)})
            workforce_assessment = WorkforceAssessment(
                agent_id="staff_scheduler_agent",
                feasibility="DATA_UNAVAILABLE",
                workforce_data_available=False,
                rationale=f"Staff assessment unavailable: {e}",
                timestamp=now_iso
            )
            staff_raw = workforce_assessment.model_dump()

        # ─── STEP 7: Run Agent E (Escalation & Safety) ────────────────────────
        escalation_result: Optional[EscalationResult] = None
        emergency_raw: Dict[str, Any] = {}
        try:
            emergency_raw = await self.emergency_agent.evaluate(
                triage_output=triage_raw,
                encounter=encounter,
                tenant_id=tenant_id
            )
            
            # Cross-agent conflict detection
            conflicts: List[Dict[str, Any]] = []
            if triage_result.recommended_care_level == "ICU" and resource_match_result.feasibility == "UNAVAILABLE":
                conflicts.append({
                    "type": "BED_CAPACITY_CONFLICT",
                    "severity": "CRITICAL",
                    "description": "Patient requires ICU admission, but zero ICU beds are available."
                })
            if workforce_assessment.feasibility == "CRITICAL_SHORTAGE":
                conflicts.append({
                    "type": "STAFF_SHORTAGE_CONFLICT",
                    "severity": "HIGH",
                    "description": "Critical staffing deficit in target clinical department."
                })
            if emergency_raw.get("escalation_required") and resource_match_result.feasibility in ["CONSTRAINED", "UNAVAILABLE"]:
                conflicts.append({
                    "type": "EMERGENCY_RESOURCE_MISMATCH",
                    "severity": "HIGH",
                    "description": "Acute emergency active while primary bed resource is constrained."
                })

            # Standalone Risk Engine Safety Assessment
            proposed_action_dict = {
                "action": "ALLOCATE_BED",
                "bed_id": resource_match_result.recommended_bed_id,
                "target_department": resource_match_result.recommended_department_id,
                "care_level": triage_result.recommended_care_level,
                "patient_id": patient.id,
                "encounter_id": encounter.id
            }
            risk_eval = self.risk_engine.evaluate(
                triage_output=triage_raw,
                emergency_output=emergency_raw,
                encounter=encounter,
                patient=patient,
                bed_output=bed_raw,
                staff_output=staff_raw
            )

            req_approval = bool(
                risk_eval.requires_human_approval or
                is_critical_decompensation or
                triage_result.esi_level <= 2 or
                len(conflicts) > 0 or
                resource_match_result.feasibility == "UNAVAILABLE"
            )

            req_human_actions = []
            if req_approval:
                req_human_actions.append("Attending physician clinical sign-off required before bed commitment.")
            if len(conflicts) > 0:
                req_human_actions.append("Charge nurse operational review for resource conflict resolution.")

            escalation_result = EscalationResult(
                agent_id="emergency_escalation_agent",
                escalation_required=bool(emergency_raw.get("escalation_required") or len(conflicts) > 0 or is_critical_decompensation),
                emergency_level=emergency_raw.get("emergency_level") or ("RAPID_RESPONSE" if is_critical_decompensation else "STANDARD_MONITORING"),
                urgency="IMMEDIATE" if is_critical_decompensation else "ROUTINE",
                escalation_reasons=emergency_raw.get("escalation_reasons", []) + [c["description"] for c in conflicts],
                policy_violations=[],
                conflicts_detected=conflicts,
                required_human_actions=req_human_actions,
                requires_human_approval=req_approval,
                rationale=emergency_raw.get("rationale") or "Comprehensive safety evaluation complete.",
                timestamp=now_iso
            )
        except Exception as e:
            logger.exception(f"EmergencyEscalationAgent failed for encounter {encounter_id}: {e}")
            agent_errors.append({"agent": "emergency_escalation_agent", "error": str(e)})
            escalation_result = EscalationResult(
                agent_id="emergency_escalation_agent",
                escalation_required=True,
                requires_human_approval=True,
                required_human_actions=["Mandatory physician review due to safety evaluator exception."],
                rationale=f"Escalated due to evaluation failure: {e}",
                timestamp=now_iso
            )
            emergency_raw = escalation_result.model_dump()

        # ─── STEP 8: Consolidate Workflow Recommendation ─────────────────────
        # Determine consolidated workflow status
        if has_severe_missing_data:
            workflow_status = "ESCALATED"
            approval_status = "PENDING"
        elif len(agent_errors) >= 3:
            workflow_status = "FAILED"
            approval_status = "REJECTED"
        elif escalation_result.requires_human_approval:
            workflow_status = "APPROVAL_PENDING"
            approval_status = "PENDING"
        else:
            workflow_status = "RECOMMENDATION_READY"
            approval_status = "NOT_REQUIRED"

        # Formulate candidate alternatives
        cand_alternatives = []
        if resource_match_result.alternative_beds:
            for alt_id in resource_match_result.alternative_beds[:3]:
                cand_alternatives.append({
                    "alternative_type": "SECONDARY_BED_OPTION",
                    "bed_id": alt_id,
                    "department_id": resource_match_result.recommended_department_id,
                    "note": "Pre-qualified alternative available bed"
                })
        if resource_match_result.feasibility == "UNAVAILABLE":
            cand_alternatives.append({
                "alternative_type": "SURGE_HOLDING",
                "department_id": "DEP-ER",
                "note": "Temporary ED holding bay with vital monitoring until unit clearance"
            })

        consolidated_rec = ConsolidatedRecommendation(
            encounter_id=encounter.id,
            patient_id=patient.id,
            tenant_id=enc_tenant,
            triage_priority=f"ESI-{triage_result.esi_level} ({triage_result.priority_level})",
            triage_rationale=triage_result.rationale,
            recommended_department=patient_flow_result.target_department,
            patient_flow_action=f"Route to {patient_flow_result.target_department} ({patient_flow_result.recommended_protocol or 'Standard Admission'})",
            recommended_bed_id=resource_match_result.recommended_bed_id,
            required_resources=["Telemetry Monitor"] if triage_result.requires_telemetry else [],
            workforce_constraints=workforce_assessment.shortages_detected or ([] if workforce_assessment.workforce_data_available else ["Roster data unavailable"]),
            escalation_level=escalation_result.emergency_level,
            escalation_reason="; ".join(escalation_result.escalation_reasons) if escalation_result.escalation_reasons else None,
            missing_information=missing_info,
            warnings=warnings,
            candidate_alternatives=cand_alternatives,
            human_approval_required=escalation_result.requires_human_approval,
            workflow_status=workflow_status,
            recommendation_timestamp=now_iso,
            state_version=1
        )

        # ─── STEP 9: Persist / Publish via Existing Services ─────────────────
        decision_id = None
        approval_item_id = None
        try:
            coord_res = await self.coordinator_agent.coordinate(
                triage_output=triage_raw,
                bed_output=bed_raw,
                staff_output=staff_raw,
                emergency_output=emergency_raw,
                coordinator_output=patient_flow_raw,
                encounter=encounter,
                patient=patient,
                tenant_id=enc_tenant,
                trigger_reason=trigger_reason or "COORDINATED_WORKFLOW_EXECUTION",
                actor_id=actor_id
            )
            decision_id = coord_res.get("decision_id") or coord_res.get("id")
            approval_item_id = coord_res.get("approval_item_id")
            consolidated_rec.decision_id = decision_id
            consolidated_rec.approval_item_id = approval_item_id
        except Exception as e:
            logger.warning(f"CoordinatorAgent persistence fallback: {e}")

        # Post-commit Event Bus Broadcast
        event_name = "APPROVAL_REQUIRED" if escalation_result.requires_human_approval else "RECOMMENDATION_GENERATED"
        try:
            await event_bus.publish({
                "event_type": event_name,
                "tenant_id": enc_tenant,
                "source": "hospital_workflow_coordinator",
                "payload": {
                    "encounter_id": encounter.id,
                    "patient_id": patient.id,
                    "workflow_id": workflow_id,
                    "correlation_id": corr_id,
                    "workflow_status": workflow_status,
                    "recommended_bed_id": resource_match_result.recommended_bed_id,
                    "target_department": patient_flow_result.target_department,
                    "approval_item_id": approval_item_id,
                    "requires_human_approval": escalation_result.requires_human_approval
                }
            }, tenant_id=enc_tenant)
        except Exception as ev_err:
            logger.debug(f"Event bus broadcast note: {ev_err}")

        # ─── STEP 10: Return Consolidated Typed Workflow State ───────────────
        workflow_state = HospitalWorkflowState(
            workflow_id=workflow_id,
            tenant_id=enc_tenant,
            patient_id=patient.id,
            encounter_id=encounter.id,
            correlation_id=corr_id,
            workflow_status=workflow_status,
            encounter_snapshot=encounter_snapshot,
            hospital_state_snapshot=hospital_state_snapshot,
            triage_result=triage_result,
            patient_flow_result=patient_flow_result,
            resource_match_result=resource_match_result,
            workforce_assessment=workforce_assessment,
            escalation_result=escalation_result,
            warnings=warnings,
            missing_information=missing_info,
            agent_errors=agent_errors,
            recommendation=consolidated_rec,
            approval_status=approval_status,
            state_version=1,
            created_at=now_iso,
            updated_at=now_iso
        )

        logger.info(
            f"Hospital workflow {workflow_id} completed for encounter {encounter_id}: "
            f"status={workflow_status}, approval_required={escalation_result.requires_human_approval}"
        )
        return workflow_state

    async def _build_state_from_existing_decision(
        self,
        existing_dec: AgentDecision,
        appr_item: Optional[ApprovalItem],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str,
        correlation_id: str
    ) -> HospitalWorkflowState:
        """Constructs a serializable workflow state from an existing cached decision."""
        now_iso = utc_now_iso()
        proposed = existing_dec.proposed_action or {}
        req_approval = bool(appr_item)

        rec = ConsolidatedRecommendation(
            encounter_id=encounter.id,
            patient_id=patient.id,
            tenant_id=tenant_id,
            triage_priority=f"ESI-{encounter.esi_level or 3}",
            triage_rationale=existing_dec.reasoning or "Existing cached clinical decision",
            recommended_department=proposed.get("target_department") or "DEP-ER",
            patient_flow_action=f"Route to {proposed.get('target_department') or 'DEP-ER'}",
            recommended_bed_id=proposed.get("bed_id"),
            required_resources=[],
            workforce_constraints=[],
            escalation_level=existing_dec.risk_level or "LOW",
            missing_information=[],
            warnings=[],
            candidate_alternatives=existing_dec.alternatives or [],
            human_approval_required=req_approval,
            approval_item_id=appr_item.id if appr_item else None,
            workflow_status="APPROVAL_PENDING" if req_approval else "RECOMMENDATION_READY",
            decision_id=existing_dec.id,
            recommendation_timestamp=str(existing_dec.created_at) if existing_dec.created_at else now_iso,
            state_version=1
        )

        return HospitalWorkflowState(
            workflow_id=f"wf-cached-{existing_dec.id[:8]}",
            tenant_id=tenant_id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            correlation_id=correlation_id,
            workflow_status=rec.workflow_status,
            encounter_snapshot={"id": encounter.id, "patient_id": patient.id},
            hospital_state_snapshot={"timestamp": now_iso},
            triage_result=TriageResult(
                agent_id="triage_agent",
                esi_level=int(encounter.esi_level or 3),
                priority_level="MODERATE",
                severity=existing_dec.risk_level or "LOW",
                score=0.0,
                recommended_care_level="GENERAL",
                clinical_urgency="STANDARD",
                rationale=existing_dec.reasoning or "Cached decision",
                timestamp=now_iso
            ),
            recommendation=rec,
            approval_status="PENDING" if req_approval else "NOT_REQUIRED",
            state_version=1,
            created_at=str(existing_dec.created_at) if existing_dec.created_at else now_iso,
            updated_at=now_iso
        )
