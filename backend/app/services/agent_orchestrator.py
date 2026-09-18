import logging
import uuid
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient, Encounter
from app.models.bed import Bed
from app.models.staff import Staff
from app.models.department import Department
from app.models.emergency import EmergencyEvent
from app.models.clinical_document import ClinicalDocument
from app.models.agent import (
    AgentDecision, AgentMessage, OptimizationRun,
    ApprovalItem, AuditLog
)
from app.services.clinical_intelligence_service import ClinicalIntelligenceService
from app.services.clinical_priority_service import ClinicalPriorityService
from app.services.clinical_summary_service import ClinicalSummaryService
from app.services.emergency_service import EmergencyService
from app.utils.datetime_utils import utc_now, utc_now_iso

logger = logging.getLogger(__name__)


# ─── 1. Triage Agent ──────────────────────────────────────────────────────────

class TriageAgent:
    """
    Autonomous Triage Decision Support Agent.
    Evaluates patient symptoms, vitals, intake session, red flags, severity score,
    and ESI priority tier to recommend clinical acuity and target care level.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
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
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }


# ─── 2. Bed Manager Agent ─────────────────────────────────────────────────────

class BedManagerAgent:
    """
    Autonomous Bed & Resource Inventory Agent (Bed Manager Agent).
    Evaluates real-time bed capacity, ward type matching, telemetry/isolation requirements,
    and step-down transitions to propose feasible candidate bed assignments without mutating resource state.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Queries live bed availability and evaluates suitability for triage recommendation.
        """
        care_level = triage_output.get("recommended_care_level", "GENERAL")
        requires_isolation = triage_output.get("requires_isolation", False)
        requires_telemetry = triage_output.get("requires_telemetry", False)

        # Map care level to bed types
        target_bed_types = {
            "ICU": ["ICU", "CARDIAC_MONITOR"],
            "EMERGENCY": ["EMERGENCY", "ICU", "GENERAL"],
            "GENERAL": ["GENERAL", "EMERGENCY"],
            "OUTPATIENT": []
        }.get(care_level, ["GENERAL"])

        if care_level == "OUTPATIENT":
            return {
                "agent_id": "bed_manager_agent",
                "status": "NOT_REQUIRED",
                "recommended_bed_id": None,
                "recommended_department_id": "DEP-OPD",
                "bed_type": None,
                "alternative_beds": [],
                "occupancy_rate": 0.0,
                "feasibility": "FEASIBLE",
                "rationale": "Outpatient encounter does not require inpatient bed reservation.",
                "timestamp": utc_now_iso()
            }

        # Query all available beds belonging to this tenant's departments
        query = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.status == "AVAILABLE"
                )
            )
        )
        res = await self.db.execute(query)
        available_beds: List[Bed] = res.scalars().all()

        # Query total bed inventory for occupancy stats for this tenant
        total_res = await self.db.execute(
            select(func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(Department.tenant_id == tenant_id)
        )
        total_beds = total_res.scalar() or 1
        occupied_res = await self.db.execute(
            select(func.count(Bed.id))
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.status.in_(["OCCUPIED", "RESERVED"])
                )
            )
        )
        occupied_beds = occupied_res.scalar() or 0
        occupancy_rate = round(occupied_beds / total_beds, 2)

        # Match optimal candidate beds
        matching_beds = [b for b in available_beds if b.bed_type in target_bed_types]
        if requires_isolation:
            iso_beds = [b for b in matching_beds if b.is_isolation]
            if iso_beds:
                matching_beds = iso_beds

        if requires_telemetry:
            telem_beds = [b for b in matching_beds if b.has_telemetry or b.bed_type == "ICU"]
            if telem_beds:
                matching_beds = telem_beds

        if matching_beds:
            primary_bed = matching_beds[0]
            alt_beds = [b.id for b in matching_beds[1:4]]
            feasibility = "FEASIBLE"
            rationale = (
                f"Optimal bed {primary_bed.id} ({primary_bed.bed_type}) identified in department {primary_bed.department_id}. "
                f"{len(matching_beds)} compatible beds available (Facility Occupancy: {occupancy_rate*100:.0f}%)."
            )
            rec_bed_id = primary_bed.id
            rec_dept_id = primary_bed.department_id
            rec_bed_type = primary_bed.bed_type
        elif available_beds:
            # Fallback bed from available general inventory
            fallback_bed = available_beds[0]
            alt_beds = [b.id for b in available_beds[1:3]]
            feasibility = "CONSTRAINED"
            rationale = (
                f"No direct {care_level} beds available. Fallback bed {fallback_bed.id} ({fallback_bed.bed_type}) "
                f"in department {fallback_bed.department_id} proposed under capacity pressure."
            )
            rec_bed_id = fallback_bed.id
            rec_dept_id = fallback_bed.department_id
            rec_bed_type = fallback_bed.bed_type
        else:
            feasibility = "UNAVAILABLE"
            rationale = f"Critical bed shortage: zero available beds across all hospital units (Occupancy: 100%). Surge holding area required."
            rec_bed_id = None
            rec_dept_id = "DEP-ER"
            rec_bed_type = "SURGE_HOLDING"
            alt_beds = []

        return {
            "agent_id": "bed_manager_agent",
            "status": "COMPLETED",
            "recommended_bed_id": rec_bed_id,
            "recommended_department_id": rec_dept_id,
            "bed_type": rec_bed_type,
            "alternative_beds": alt_beds,
            "occupancy_rate": occupancy_rate,
            "feasibility": feasibility,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def propose_counter_proposal(
        self,
        triage_output: Dict[str, Any],
        initial_bed_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Formulates a structured counter-proposal when optimal bed tier is constrained or unavailable.
        Evaluates step-down telemetry units, observation surge beds, or emergency holding areas.
        """
        alt_beds = initial_bed_output.get("alternative_beds", [])
        if alt_beds:
            proposed_bed_id = alt_beds[0]
            bed_obj = (
                await self.db.execute(
                    select(Bed)
                    .join(Department, Bed.department_id == Department.id)
                    .where(
                        and_(
                            Department.tenant_id == tenant_id,
                            Bed.id == proposed_bed_id
                        )
                    )
                )
            ).scalar_one_or_none()
            dept_id = bed_obj.department_id if bed_obj else "DEP-WA"
            bed_type = bed_obj.bed_type if bed_obj else "STEP_DOWN"
            counter_rationale = f"Propose step-down bed {proposed_bed_id} ({bed_type}) in {dept_id} with continuous vital monitoring."
        else:
            proposed_bed_id = None
            dept_id = "DEP-ER"
            bed_type = "EMERGENCY_HOLDING"
            counter_rationale = "Propose emergency holding area placement with STAT clinical consultation and continuous telemetry."

        return {
            "agent_id": "bed_manager_agent",
            "message_type": "COUNTER_PROPOSAL",
            "proposed_bed_id": proposed_bed_id,
            "proposed_department_id": dept_id,
            "proposed_bed_type": bed_type,
            "rationale": counter_rationale,
            "timestamp": utc_now_iso()
        }

    async def evaluate_discharge_stepdown_proposal(
        self,
        proposal: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Evaluates a Patient Care Coordinator discharge or step-down transfer proposal.
        Checks real-time bed inventory in the requested target department belonging to this tenant.
        If unavailable, formulates a genuine alternative counter-proposal using available beds belonging to this tenant.
        """
        trans_type = proposal.get("transition_type")
        if trans_type == "OUTPATIENT_DISCHARGE":
            return {
                "agent_id": "bed_manager_agent",
                "decision": "ACCEPT",
                "department_id": "DEP-OPD",
                "allocated_bed_id": None,
                "rationale": "Outpatient discharge confirmed; inpatient bed de-allocated or not required.",
                "timestamp": utc_now_iso()
            }

        target_dept = proposal.get("proposed_destination", "DEP-WA")
        req_iso = proposal.get("requires_isolation", False)
        req_telem = proposal.get("requires_telemetry", False)

        # 1. Query available beds in target department belonging to this tenant
        stmt = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.department_id == target_dept,
                    Bed.status == "AVAILABLE"
                )
            )
        )
        res = await self.db.execute(stmt)
        target_beds: List[Bed] = res.scalars().all()

        if req_iso:
            target_beds = [b for b in target_beds if b.is_isolation]
        if req_telem:
            target_beds = [b for b in target_beds if b.has_telemetry or b.bed_type == "ICU"]

        if target_beds:
            allocated = target_beds[0]
            return {
                "agent_id": "bed_manager_agent",
                "decision": "ACCEPT",
                "allocated_bed_id": allocated.id,
                "department_id": target_dept,
                "bed_type": allocated.bed_type,
                "has_telemetry": allocated.has_telemetry,
                "is_isolation": allocated.is_isolation,
                "rationale": f"Accepted step-down assignment to bed {allocated.id} ({allocated.bed_type}) in {target_dept}.",
                "timestamp": utc_now_iso()
            }

        # 2. If target department has no matching beds, find alternative general / step-down ward bed belonging to this tenant
        alt_stmt = (
            select(Bed)
            .join(Department, Bed.department_id == Department.id)
            .where(
                and_(
                    Department.tenant_id == tenant_id,
                    Bed.department_id != target_dept,
                    Department.code != "ER",
                    Bed.department_id != "DEP-ER",
                    Bed.bed_type.in_(["GENERAL", "STEP_DOWN", "CARDIAC_MONITOR"]),
                    Bed.status == "AVAILABLE"
                )
            )
        )
        alt_res = await self.db.execute(alt_stmt)
        alt_beds: List[Bed] = alt_res.scalars().all()

        if req_iso:
            alt_iso_beds = [b for b in alt_beds if b.is_isolation]
            if alt_iso_beds:
                alt_beds = alt_iso_beds
        if req_telem:
            alt_telem_beds = [b for b in alt_beds if b.has_telemetry or b.bed_type in ["ICU", "CARDIAC_MONITOR"]]
            if alt_telem_beds:
                alt_beds = alt_telem_beds

        if alt_beds:
            counter_bed = alt_beds[0]
            return {
                "agent_id": "bed_manager_agent",
                "decision": "COUNTER_PROPOSAL",
                "counter_bed_id": counter_bed.id,
                "counter_department_id": counter_bed.department_id,
                "counter_bed_type": counter_bed.bed_type,
                "has_telemetry": counter_bed.has_telemetry,
                "is_isolation": counter_bed.is_isolation,
                "rationale": f"Target department {target_dept} has no available matching beds. Counter-proposing bed {counter_bed.id} ({counter_bed.bed_type}) in {counter_bed.department_id}.",
                "timestamp": utc_now_iso()
            }

        # 3. No available beds facility-wide
        return {
            "agent_id": "bed_manager_agent",
            "decision": "REJECT",
            "rationale": f"Target department {target_dept} and all secondary hospital wards have zero available beds.",
            "timestamp": utc_now_iso()
        }


# Alias for backward compatibility
BedManagementAgent = BedManagerAgent


# ─── 3. Staff Scheduler Agent ─────────────────────────────────────────────────

class StaffSchedulerAgent:
    """
    Autonomous Staff Scheduler & Workload Balancing Agent.
    Monitors clinician rosters, shift schedules, nurse-to-patient load ratios, and doctor availability
    to propose balanced clinical team assignments and shift coverage without modifying staff records directly.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Evaluates clinical staffing capacity in the proposed target department.
        """
        dept_id = bed_output.get("recommended_department_id") or encounter.current_department_id or "DEP-ER"

        # Query all active staff
        staff_query = select(Staff).where(
            and_(
                Staff.tenant_id == tenant_id,
                Staff.status.in_(["AVAILABLE", "BUSY"])
            )
        )
        res = await self.db.execute(staff_query)
        all_staff: List[Staff] = res.scalars().all()

        doctors = [s for s in all_staff if s.role == "DOCTOR"]
        nurses = [s for s in all_staff if s.role in ["NURSE", "CHARGE_NURSE"]]

        # Prioritize staff in target department, then hospital-wide
        dept_doctors = [d for d in doctors if d.department_id == dept_id] or doctors
        dept_nurses = [n for n in nurses if n.department_id == dept_id] or nurses

        # Select least loaded doctor and nurse
        assigned_doc = min(dept_doctors, key=lambda d: d.current_workload) if dept_doctors else None
        assigned_nurse = min(dept_nurses, key=lambda n: n.current_workload) if dept_nurses else None

        # Calculate average nurse workload
        avg_nurse_load = (
            sum(n.current_workload for n in dept_nurses) / len(dept_nurses)
            if dept_nurses else 0.0
        )

        # Assess feasibility
        if assigned_doc and assigned_nurse:
            if assigned_nurse.current_workload >= assigned_nurse.max_workload:
                feasibility = "WARNING_OVERLOAD"
                rationale = (
                    f"Staff assignment feasible with load pressure: Doctor {assigned_doc.id} (load {assigned_doc.current_workload}/{assigned_doc.max_workload}), "
                    f"Nurse {assigned_nurse.id} at capacity ({assigned_nurse.current_workload}/{assigned_nurse.max_workload})."
                )
            else:
                feasibility = "FEASIBLE"
                rationale = (
                    f"Balanced team assigned: Doctor {assigned_doc.id} (load {assigned_doc.current_workload}/{assigned_doc.max_workload}), "
                    f"Nurse {assigned_nurse.id} (load {assigned_nurse.current_workload}/{assigned_nurse.max_workload}). Avg Nurse Ratio: {avg_nurse_load:.1f}:1."
                )
        else:
            feasibility = "CRITICAL_SHORTAGE"
            rationale = "Critical clinical staff shortage: No on-duty doctor or nurse available for assignment."

        return {
            "agent_id": "staff_scheduler_agent",
            "status": "COMPLETED",
            "assigned_doctor_id": assigned_doc.id if assigned_doc else None,
            "assigned_nurse_id": assigned_nurse.id if assigned_nurse else None,
            "avg_nurse_load": round(avg_nurse_load, 1),
            "feasibility": feasibility,
            "rationale": rationale,
            "timestamp": utc_now_iso()
        }

    async def propose_rebalanced_workload(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        initial_staff_output: Dict[str, Any],
        encounter: Encounter,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Formulates a rebalanced staff allocation when primary clinician workload exceeds capacity.
        """
        query = select(Staff).where(
            and_(
                Staff.tenant_id == tenant_id,
                Staff.status.in_(["AVAILABLE", "BUSY"])
            )
        ).order_by(Staff.current_workload.asc())
        res = await self.db.execute(query)
        on_duty_staff = res.scalars().all()

        doctors = [s for s in on_duty_staff if s.role == "DOCTOR"]
        nurses = [s for s in on_duty_staff if s.role in ["NURSE", "CHARGE_NURSE"]]

        rebalanced_doc = doctors[0] if doctors else None
        rebalanced_nurse = nurses[0] if nurses else None

        return {
            "agent_id": "staff_scheduler_agent",
            "message_type": "REVISED_PROPOSAL",
            "assigned_doctor_id": rebalanced_doc.id if rebalanced_doc else None,
            "assigned_nurse_id": rebalanced_nurse.id if rebalanced_nurse else None,
            "feasibility": "REBALANCED" if (rebalanced_doc or rebalanced_nurse) else "CRITICAL_SHORTAGE",
            "rationale": f"Rebalanced staff assignment to Doctor {rebalanced_doc.id if rebalanced_doc else 'None'} and Nurse {rebalanced_nurse.id if rebalanced_nurse else 'None'}.",
            "timestamp": utc_now_iso()
        }


# Alias for backward compatibility
StaffWorkloadAgent = StaffSchedulerAgent


# ─── 4. Emergency Escalation Agent ────────────────────────────────────────────

class EmergencyEscalationAgent:
    """
    Autonomous Emergency & Rapid Response Escalation Agent.
    Evaluates acute physiological red flags, hemodynamic collapse indicators,
    and facility-wide disaster declarations to determine emergency escalation triggers
    without mutating hospital state directly.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
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


# ─── 5. Patient Coordinator Agent ─────────────────────────────────────────────

class PatientCoordinatorAgent:
    """
    Autonomous Patient Care Coordinator & Clinical Handoff Agent.
    Synthesizes intake context, diagnostic investigation statuses, and discharge readiness
    to formulate structured physician handoff briefs and patient continuity recommendations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
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


# ─── 6. Coordinator Agent ─────────────────────────────────────────────────────

class CoordinatorAgent:
    """
    Autonomous Multi-Agent Workflow Coordinator.
    Synthesizes messages from all 5 specialized agents (Triage, Bed, Staff, Emergency Escalation,
    and Patient Coordinator), detects operational conflicts, builds multi-objective candidate
    operational plans, evaluates clinical safety policies, and routes consequential actions to
    the Human-in-the-Loop approval queue.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def coordinate(
        self,
        triage_output: Dict[str, Any],
        bed_output: Dict[str, Any],
        staff_output: Dict[str, Any],
        emergency_output: Dict[str, Any],
        coordinator_output: Dict[str, Any],
        encounter: Encounter,
        patient: Patient,
        tenant_id: str,
        trigger_reason: Optional[str] = None,
        actor_id: str = "SYSTEM",
        negotiation_messages: Optional[List[Dict[str, Any]]] = None,
        active_conflicts: Optional[List[Dict[str, Any]]] = None,
        revised_proposals: Optional[Dict[str, Any]] = None,
        negotiation_status: str = "NONE"
    ) -> Dict[str, Any]:
        """
        Coordinates all 5 agent outputs, integrates negotiation exchanges, builds candidate plans,
        and creates authoritative decision and audit records.
        """
        start_time = time.perf_counter()
        conflicts = list(active_conflicts) if active_conflicts is not None else []

        # 1. Cross-Agent Conflict Detection (if not already precomputed)
        if active_conflicts is None:
            if triage_output["recommended_care_level"] == "ICU" and bed_output["feasibility"] == "UNAVAILABLE":
                conflicts.append({
                    "type": "BED_CAPACITY_CONFLICT",
                    "severity": "CRITICAL",
                    "description": "Triage demands immediate ICU admission, but zero ICU beds are available."
                })

            if staff_output["feasibility"] == "CRITICAL_SHORTAGE":
                conflicts.append({
                    "type": "STAFF_SHORTAGE_CONFLICT",
                    "severity": "HIGH",
                    "description": "Insufficient clinical staff on duty for recommended care tier."
                })

            if emergency_output["escalation_required"] and bed_output["feasibility"] == "CONSTRAINED":
                conflicts.append({
                    "type": "EMERGENCY_RESOURCE_MISMATCH",
                    "severity": "HIGH",
                    "description": "Emergency escalation active but optimal critical care bed is constrained."
                })

        # 2. Formulate Multi-Objective Candidate Plans
        candidates = []

        # Check if revised proposals were negotiated
        revised = revised_proposals or {}
        bed_counter = revised.get("bed_counter_proposal")
        staff_revised = revised.get("staff_revised_proposal")

        target_bed_p0 = bed_output.get("recommended_bed_id")
        target_dept_p0 = bed_output.get("recommended_department_id")
        assigned_doc_p0 = staff_output.get("assigned_doctor_id")
        assigned_nurse_p0 = staff_output.get("assigned_nurse_id")

        if bed_counter and bed_counter.get("proposed_bed_id"):
            target_bed_p0 = bed_counter.get("proposed_bed_id")
            target_dept_p0 = bed_counter.get("proposed_department_id")

        if staff_revised and staff_revised.get("assigned_doctor_id"):
            assigned_doc_p0 = staff_revised.get("assigned_doctor_id")
            assigned_nurse_p0 = staff_revised.get("assigned_nurse_id") or assigned_nurse_p0

        stepdown_neg = revised.get("stepdown_negotiation")
        if stepdown_neg:
            coord_eval = stepdown_neg.get("coordinator_evaluation", {})
            bed_resp = stepdown_neg.get("bed_response", {})
            if coord_eval.get("message_type") == "ACCEPT":
                if bed_resp.get("allocated_bed_id") or bed_resp.get("counter_bed_id"):
                    target_bed_p0 = bed_resp.get("allocated_bed_id") or bed_resp.get("counter_bed_id")
                if bed_resp.get("department_id") or bed_resp.get("counter_department_id"):
                    target_dept_p0 = bed_resp.get("department_id") or bed_resp.get("counter_department_id")

        # Plan 0: Primary Optimal / Negotiated Plan
        candidates.append({
            "plan_index": 0,
            "plan_type": "PRIMARY_RECOMMENDED" if not revised else "NEGOTIATED_OPTIMAL",
            "care_level": triage_output["recommended_care_level"],
            "target_bed_id": target_bed_p0,
            "target_department_id": target_dept_p0,
            "assigned_doctor_id": assigned_doc_p0,
            "assigned_nurse_id": assigned_nurse_p0,
            "emergency_level": emergency_output.get("emergency_level"),
            "objective_score": 0.92 if not conflicts else (0.85 if negotiation_status == "RESOLVED" else 0.70),
            "waiting_time_score": 0.95,
            "resource_util_score": 0.88,
            "staff_balance_score": 0.90 if staff_output["feasibility"] in ["FEASIBLE", "REBALANCED"] else 0.65,
            "hard_constraint_pass": len(conflicts) == 0 or negotiation_status == "RESOLVED",
            "description": f"Direct placement in {bed_output.get('bed_type', 'unit')} with assigned doctor {assigned_doc_p0}."
        })

        # Plan 1: Step-Down / Alternative Plan
        alt_bed = (bed_output.get("alternative_beds") or [None])[0]
        candidates.append({
            "plan_index": 1,
            "plan_type": "ALTERNATIVE_STEP_DOWN",
            "care_level": "EMERGENCY" if triage_output["recommended_care_level"] == "ICU" else "GENERAL",
            "target_bed_id": alt_bed,
            "target_department_id": bed_output.get("recommended_department_id"),
            "assigned_doctor_id": assigned_doc_p0,
            "assigned_nurse_id": assigned_nurse_p0,
            "emergency_level": emergency_output.get("emergency_level"),
            "objective_score": 0.82,
            "waiting_time_score": 0.85,
            "resource_util_score": 0.80,
            "staff_balance_score": 0.85,
            "hard_constraint_pass": True,
            "description": f"Alternative placement in bed {alt_bed} with continuous telemetry monitoring."
        })

        # Plan 2: Contingency / Surge Stabilization Plan
        candidates.append({
            "plan_index": 2,
            "plan_type": "CONTINGENCY_SURGE",
            "care_level": "EMERGENCY_HOLDING",
            "target_bed_id": None,
            "target_department_id": "DEP-ER",
            "assigned_doctor_id": assigned_doc_p0,
            "assigned_nurse_id": assigned_nurse_p0,
            "emergency_level": emergency_output.get("emergency_level"),
            "objective_score": 0.72,
            "waiting_time_score": 0.70,
            "resource_util_score": 0.75,
            "staff_balance_score": 0.75,
            "hard_constraint_pass": True,
            "description": "Emergency stabilization holding area placement with specialist consult request."
        })

        # Select Best Plan
        selected_plan_idx = 0 if candidates[0]["hard_constraint_pass"] else 1
        selected_plan = candidates[selected_plan_idx]

        # 3. Determine Action Type, Risk Level, and Human Approval Requirement
        care_level = triage_output["recommended_care_level"]
        severity = triage_output["severity"]
        priority_level = triage_output["priority_level"]
        red_flags_count = len(triage_output["red_flags"])
        is_escalated = emergency_output.get("escalation_required", False) or (negotiation_status == "UNRESOLVED_ESCALATED")

        if priority_level == "CRITICAL" or severity in ["HIGH", "CRITICAL"] or red_flags_count >= 2 or care_level == "ICU" or is_escalated:
            action_type = "ICU_BED_ALLOCATION_RECOMMENDATION"
            risk_level = "HIGH"
            requires_human_approval = True
            confidence = 0.94
            reasoning = (
                f"Critical physiological decompensation detected (Severity: {severity}, "
                f"Priority: {priority_level}, Red Flags: {red_flags_count}, Emergency Level: {emergency_output.get('emergency_level')}, "
                f"Negotiation Status: {negotiation_status}). "
                f"Immediate ICU bed allocation and continuous telemetry monitoring recommended."
            )
            proposed_action = {
                "action": "ALLOCATE_BED",
                "bed_type": "ICU",
                "target_bed_id": selected_plan["target_bed_id"],
                "target_department_id": selected_plan["target_department_id"],
                "assigned_doctor_id": selected_plan["assigned_doctor_id"],
                "assigned_nurse_id": selected_plan["assigned_nurse_id"],
                "emergency_actions": emergency_output.get("recommended_emergency_actions", []),
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "priority": "CRITICAL"
            }
        elif priority_level == "HIGH" or red_flags_count == 1 or care_level == "EMERGENCY":
            action_type = "SPECIALIST_CONSULT_RECOMMENDATION"
            risk_level = "MEDIUM"
            requires_human_approval = True
            confidence = 0.88
            reasoning = (
                f"Elevated clinical acuity identified (Severity: {severity}, Priority: {priority_level}, Negotiation: {negotiation_status}). "
                f"Immediate attending emergency physician consultation recommended."
            )
            proposed_action = {
                "action": "ORDER_CONSULT",
                "specialty": "EMERGENCY_MEDICINE",
                "target_bed_id": selected_plan["target_bed_id"],
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "priority": "HIGH"
            }
        elif priority_level == "MODERATE" or (care_level == "GENERAL" and priority_level not in ["ROUTINE", "LOW"]):
            action_type = "OBSERVATION_ADMISSION_RECOMMENDATION"
            risk_level = "LOW"
            requires_human_approval = True
            confidence = 0.82
            reasoning = "Moderate clinical presentation with stable vital signs. Step-down observation ward admission recommended."
            proposed_action = {
                "action": "OBSERVE",
                "department_code": selected_plan["target_department_id"] or "DEP-WA",
                "target_bed_id": selected_plan["target_bed_id"],
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "priority": "MODERATE"
            }
        else:
            action_type = "STANDARD_OPD_ROUTING"
            risk_level = "LOW"
            requires_human_approval = False
            confidence = 0.90
            reasoning = "Normal vital parameters without acute clinical red flags. Routed to standard outpatient consultation queue."
            proposed_action = {
                "action": "QUEUE_OPD",
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "priority": "ROUTINE"
            }

        # 4. Persist Inter-Agent Messages (Full Provenance Traceability)
        messages_to_persist: List[AgentMessage] = [
            AgentMessage(
                sender_agent="triage_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="TRIAGE_ASSESSMENT_COMPLETED",
                payload=triage_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="bed_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="BED_FEASIBILITY_EVALUATED",
                payload=bed_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="staff_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="STAFF_WORKLOAD_EVALUATED",
                payload=staff_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="emergency_escalation_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="EMERGENCY_ESCALATION_EVALUATED",
                payload=emergency_output,
                status="DELIVERED"
            ),
            AgentMessage(
                sender_agent="patient_coordinator_agent",
                receiver_agent="coordinator_agent",
                encounter_id=encounter.id,
                message_type="INFORM",
                subject="PATIENT_COORDINATION_COMPLETED",
                payload=coordinator_output,
                status="DELIVERED"
            ),
        ]

        # Add structured negotiation messages
        if negotiation_messages:
            for nm in negotiation_messages:
                messages_to_persist.append(
                    AgentMessage(
                        sender_agent=nm.get("sender_agent", "unknown_agent"),
                        receiver_agent=nm.get("receiver_agent", "coordinator_agent"),
                        encounter_id=encounter.id,
                        message_type=nm.get("message_type", "INFORM"),
                        subject=nm.get("subject", "NEGOTIATION_UPDATE"),
                        payload=nm.get("payload", {}),
                        status="DELIVERED"
                    )
                )

        # Append final coordinator response message
        msg_coord = AgentMessage(
            sender_agent="coordinator_agent",
            receiver_agent="clinical_execution_boundary",
            encounter_id=encounter.id,
            message_type="RESPONSE",
            subject="OPERATIONAL_PLAN_SELECTED",
            payload={
                "selected_plan": selected_plan,
                "action_type": action_type,
                "risk_level": risk_level,
                "requires_approval": requires_human_approval,
                "emergency_escalation": emergency_output.get("escalation_required"),
                "discharge_readiness": coordinator_output.get("discharge_readiness"),
                "negotiation_status": negotiation_status,
                "negotiation_messages_count": len(negotiation_messages or [])
            },
            status="DELIVERED"
        )
        messages_to_persist.append(msg_coord)

        self.db.add_all(messages_to_persist)
        await self.db.flush()

        # 5. Persist OptimizationRun Entity
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        opt_run = OptimizationRun(
            trigger_type="MULTI_AGENT_COORDINATION",
            encounter_id=encounter.id,
            agents_involved=[
                "triage_agent",
                "bed_agent",
                "staff_agent",
                "emergency_escalation_agent",
                "patient_coordinator_agent",
                "coordinator_agent"
            ],
            candidates_count=len(candidates),
            candidates=candidates,
            selected_plan_index=selected_plan_idx,
            selected_plan=selected_plan,
            objective_score=selected_plan["objective_score"],
            waiting_time_score=selected_plan["waiting_time_score"],
            resource_util_score=selected_plan["resource_util_score"],
            staff_balance_score=selected_plan["staff_balance_score"],
            constraint_violations=len(conflicts),
            hard_constraint_pass=selected_plan["hard_constraint_pass"],
            status="COMPLETED",
            computation_time_ms=max(1, elapsed_ms)
        )
        self.db.add(opt_run)
        await self.db.flush()

        # 6. Persist AgentDecision Entity
        decision = AgentDecision(
            agent_id="MultiAgentCoordinator",
            encounter_id=encounter.id,
            action_type=action_type,
            proposed_action=proposed_action,
            reasoning=reasoning,
            confidence=confidence,
            alternatives=candidates,
            risk_level=risk_level,
            status="PROPOSED"
        )
        self.db.add(decision)
        await self.db.flush()

        # 7. Persist ApprovalItem if Consequential
        approval_item_id = None
        if requires_human_approval:
            approval = ApprovalItem(
                decision_id=decision.id,
                agent_id="MultiAgentCoordinator",
                action_type=action_type,
                risk_level=risk_level,
                proposed_action=proposed_action,
                reasoning=reasoning,
                alternatives=candidates,
                status="PENDING"
            )
            self.db.add(approval)
            await self.db.flush()
            approval_item_id = approval.id

        # 8. Record Immutable Audit Trail
        audit = AuditLog(
            tenant_id=tenant_id,
            entity_type="intelligence_decision",
            entity_id=decision.id,
            field_changed="decision_generated",
            old_value="NONE",
            new_value=action_type,
            changed_by=actor_id,
            change_reason=f"Multi-Agent Workflow Evaluated: {action_type} (Risk: {risk_level})",
            decision_id=decision.id,
            approval_id=approval_item_id
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(decision)

        logger.info(
            f"5-Agent Multi-Agent Workflow Complete for Encounter {encounter.id}: Decision {decision.id} "
            f"({action_type}, Risk: {risk_level}, OptimizationRun: {opt_run.id})"
        )

        # Publish real-time event via Redis Event Bus (PostgreSQL remains authoritative)
        from app.services.events import event_bus
        await event_bus.publish({
            "event_type": "AGENT_DECISION_PROPOSED",
            "tenant_id": tenant_id,
            "source": "coordinator_agent",
            "payload": {
                "decision_id": decision.id,
                "encounter_id": encounter.id,
                "patient_id": patient.id,
                "action_type": action_type,
                "risk_level": risk_level,
                "requires_human_approval": requires_human_approval,
                "approval_item_id": approval_item_id,
                "status": decision.status
            }
        }, tenant_id=tenant_id)

        return {
            "id": decision.id,
            "encounter_id": encounter.id,
            "patient_id": patient.id,
            "agent_id": decision.agent_id,
            "action_type": decision.action_type,
            "risk_level": decision.risk_level,
            "confidence": decision.confidence,
            "proposed_action": decision.proposed_action,
            "reasoning": decision.reasoning,
            "requires_human_approval": requires_human_approval,
            "approval_item_id": approval_item_id,
            "status": decision.status,
            "optimization_run_id": opt_run.id,
            "selected_plan": selected_plan,
            "candidate_plans": candidates,
            "conflicts": conflicts,
            "negotiation_status": negotiation_status,
            "negotiation_messages_count": len(negotiation_messages or []),
            "agent_messages_count": len(messages_to_persist),
            "emergency_escalation": emergency_output,
            "patient_coordination": coordinator_output,
            "created_at": decision.created_at
        }


# ─── 7. MultiAgentOrchestratorService ─────────────────────────────────────────

class MultiAgentOrchestratorService:
    """
    Application Service driving the 5-Agent Multi-Agent Hospital Optimization Pipeline.
    Manages the lifecycle across Triage Agent, Bed Manager Agent, Staff Scheduler Agent,
    Emergency Escalation Agent, Patient Coordinator Agent, and Coordinator Agent
    with strict transactional isolation and idempotency.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.triage_agent = TriageAgent(db)
        self.bed_agent = BedManagerAgent(db)
        self.staff_agent = StaffSchedulerAgent(db)
        self.emergency_agent = EmergencyEscalationAgent(db)
        self.patient_coordinator_agent = PatientCoordinatorAgent(db)
        self.coordinator = CoordinatorAgent(db)

    async def orchestrate_encounter(
        self,
        encounter_id: str,
        tenant_id: str = "HOSP-DEFAULT",
        trigger_reason: Optional[str] = None,
        force_recalculate: bool = False,
        actor_id: str = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Executes the full end-to-end 5-agent decision support workflow for an encounter.
        """
        # 1. Fetch Encounter with row lock
        enc_res = await self.db.execute(
            select(Encounter).where(Encounter.id == encounter_id).with_for_update()
        )
        encounter = enc_res.scalars().first()
        if not encounter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Encounter {encounter_id} not found")

        # 2. Fetch Patient
        p_res = await self.db.execute(select(Patient).where(Patient.id == encounter.patient_id))
        patient = p_res.scalars().first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient {encounter.patient_id} not found")

        # 3. Idempotency check
        if not force_recalculate:
            existing_dec_res = await self.db.execute(
                select(AgentDecision)
                .where(
                    AgentDecision.encounter_id == encounter_id,
                    AgentDecision.status.in_(["PROPOSED", "PENDING", "APPROVED"])
                )
                .order_by(AgentDecision.created_at.desc())
            )
            existing_decision = existing_dec_res.scalars().first()
            if existing_decision:
                appr_res = await self.db.execute(
                    select(ApprovalItem).where(ApprovalItem.decision_id == existing_decision.id)
                )
                appr_item = appr_res.scalars().first()
                opt_res = await self.db.execute(
                    select(OptimizationRun).where(OptimizationRun.encounter_id == encounter_id).order_by(OptimizationRun.started_at.desc())
                )
                opt_run = opt_res.scalars().first()

                logger.info(f"Returning existing active multi-agent decision {existing_decision.id} for encounter {encounter_id}")
                return {
                    "id": existing_decision.id,
                    "encounter_id": encounter_id,
                    "patient_id": patient.id,
                    "agent_id": existing_decision.agent_id,
                    "action_type": existing_decision.action_type,
                    "risk_level": existing_decision.risk_level,
                    "confidence": existing_decision.confidence,
                    "proposed_action": existing_decision.proposed_action,
                    "reasoning": existing_decision.reasoning,
                    "requires_human_approval": bool(appr_item),
                    "approval_item_id": appr_item.id if appr_item else None,
                    "status": existing_decision.status,
                    "optimization_run_id": opt_run.id if opt_run else None,
                    "selected_plan": opt_run.selected_plan if opt_run else None,
                    "candidate_plans": opt_run.candidates if opt_run else [],
                    "conflicts": [],
                    "agent_messages_count": 6,
                    "created_at": existing_decision.created_at
                }

        # 4. Execute LangGraph Multi-Agent StateGraph
        from app.services.agent_graph import HospitalLangGraphOrchestrator
        graph_orchestrator = HospitalLangGraphOrchestrator(self.db, encounter=encounter, patient=patient)
        graph_state = await graph_orchestrator.run(
            tenant_id=tenant_id,
            trigger_reason=trigger_reason,
            force_recalculate=force_recalculate,
            actor_id=actor_id
        )

        if graph_state.get("status") == "FAILED":
            failed_agent = graph_state.get("failed_agent", "unknown_agent")
            err_msg = graph_state.get("error", "Unknown orchestration error")
            logger.error(f"LangGraph execution failed at {failed_agent}: {err_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Multi-agent graph orchestration failed at {failed_agent}: {err_msg}"
            )

        return graph_state.get("coordinator_output", {})
