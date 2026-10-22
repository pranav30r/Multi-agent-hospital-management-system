"""
Hospital Coordinated Multi-Agent Workflow Schemas.

Defines strictly typed input and output contracts for:
- Agent A: Intake and Triage (TriageResult)
- Agent B: Patient Flow (PatientFlowResult)
- Agent C: Bed & Resource Matching (ResourceMatchResult)
- Agent D: Workforce & Staffing (WorkforceAssessment)
- Agent E: Escalation & Safety (EscalationResult)
- Consolidated Recommendation (ConsolidatedRecommendation)
- Shared Workflow State (HospitalWorkflowState)
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class TriageResult(BaseModel):
    """Output contract for Agent A: Intake and Triage."""
    agent_id: str = Field(default="triage_agent")
    esi_level: int = Field(..., ge=1, le=5, description="Emergency Severity Index level (1=Resuscitation, 5=Non-urgent)")
    priority_level: str = Field(..., description="CRITICAL, HIGH, MODERATE, LOW, ROUTINE")
    severity: str = Field(..., description="CRITICAL, HIGH, MODERATE, LOW")
    score: float = Field(default=0.0, ge=0.0, description="Quantitative acuity severity score")
    red_flags: List[Dict[str, Any]] = Field(default_factory=list, description="Physiological and symptom red flags")
    recommended_care_level: str = Field(..., description="ICU, EMERGENCY, GENERAL, OUTPATIENT")
    clinical_urgency: str = Field(..., description="IMMEDIATE, URGENT, STANDARD, ROUTINE")
    requires_telemetry: bool = Field(default=False)
    requires_isolation: bool = Field(default=False)
    missing_information: List[str] = Field(default_factory=list, description="Missing intake or vital parameters")
    rationale: str = Field(..., description="Clinical triage justification")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")

    model_config = ConfigDict(extra="ignore")


class PatientFlowResult(BaseModel):
    """Output contract for Agent B: Patient Flow."""
    agent_id: str = Field(default="patient_coordinator_agent")
    current_stage: str = Field(default="TRIAGE", description="Current encounter operational stage")
    target_department: str = Field(..., description="Department or clinical service routing")
    recommended_protocol: Optional[str] = Field(None, description="Clinical pathway or guideline protocol")
    next_operational_steps: List[str] = Field(default_factory=list, description="Immediate care delivery actions")
    missing_prerequisites: List[str] = Field(default_factory=list, description="Prerequisite tests or clearances needed")
    transfer_requirements: List[str] = Field(default_factory=list, description="Telemetry, transport escort, or stretcher requirements")
    flow_bottlenecks: List[str] = Field(default_factory=list, description="Identified operational congestion points")
    handoff_brief: Dict[str, Any] = Field(default_factory=dict, description="Structured clinical handoff brief")
    rationale: str = Field(..., description="Operational flow justification")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")

    model_config = ConfigDict(extra="ignore")


class ResourceMatchResult(BaseModel):
    """Output contract for Agent C: Bed and Resource Matching."""
    agent_id: str = Field(default="bed_manager_agent")
    recommended_bed_id: Optional[str] = Field(None, description="Ranked top candidate bed target")
    recommended_department_id: Optional[str] = Field(None, description="Department hosting the bed")
    bed_type: Optional[str] = Field(None, description="ICU_VENTILATOR, CARDIAC_MONITOR, EMERGENCY_BAY, STANDARD_INPATIENT")
    feasibility: str = Field(..., description="FEASIBLE, CONSTRAINED, UNAVAILABLE, NOT_REQUIRED")
    candidate_beds: List[str] = Field(default_factory=list, description="Ranked list of candidate bed identifiers")
    alternative_beds: List[str] = Field(default_factory=list, description="Feasible alternative bed identifiers")
    rejected_constraints: List[str] = Field(default_factory=list, description="Hard constraints that failed for excluded beds")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Confidence in resource recommendation")
    rationale: str = Field(..., description="Resource matching justification")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")

    model_config = ConfigDict(extra="ignore")


class WorkforceAssessment(BaseModel):
    """Output contract for Agent D: Workforce and Staffing."""
    agent_id: str = Field(default="staff_scheduler_agent")
    assigned_doctor_id: Optional[str] = Field(None, description="Recommended attending clinician")
    assigned_nurse_id: Optional[str] = Field(None, description="Recommended primary care nurse")
    feasibility: str = Field(..., description="FEASIBLE, REBALANCED, WARNING_OVERLOAD, CRITICAL_SHORTAGE, DATA_UNAVAILABLE")
    shortages_detected: List[str] = Field(default_factory=list, description="Roster or skill coverage gaps")
    coverage_constraints: List[str] = Field(default_factory=list, description="Workload ratio or shift limits")
    alternative_staff: List[Dict[str, Any]] = Field(default_factory=list, description="Alternative staff options")
    workforce_data_available: bool = Field(default=True, description="False if roster data is unavailable")
    rationale: str = Field(..., description="Staffing capacity assessment justification")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")

    model_config = ConfigDict(extra="ignore")


class EscalationResult(BaseModel):
    """Output contract for Agent E: Escalation and Safety."""
    agent_id: str = Field(default="emergency_escalation_agent")
    escalation_required: bool = Field(default=False, description="True if case requires clinical escalation")
    emergency_level: str = Field(default="STANDARD_MONITORING", description="STANDARD_MONITORING, RAPID_RESPONSE, CODE_BLUE, DISASTER_SURGE")
    urgency: str = Field(default="ROUTINE", description="IMMEDIATE, URGENT, ROUTINE")
    escalation_reasons: List[str] = Field(default_factory=list, description="Specific triggers warranting escalation")
    policy_violations: List[str] = Field(default_factory=list, description="Clinical governance or safety violations")
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list, description="Cross-agent recommendation conflicts")
    required_human_actions: List[str] = Field(default_factory=list, description="Mandatory clinician or charge nurse sign-offs")
    requires_human_approval: bool = Field(default=False, description="Enforces Human-in-the-Loop approval gate")
    rationale: str = Field(..., description="Safety and escalation evaluation justification")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")

    model_config = ConfigDict(extra="ignore")


class ConsolidatedRecommendation(BaseModel):
    """Unified recommendation produced by the Coordinator for clinician review."""
    encounter_id: str
    patient_id: str
    tenant_id: str
    triage_priority: str
    triage_rationale: str
    recommended_department: str
    patient_flow_action: str
    recommended_bed_id: Optional[str] = None
    required_resources: List[str] = Field(default_factory=list)
    workforce_constraints: List[str] = Field(default_factory=list)
    escalation_level: str
    escalation_reason: Optional[str] = None
    missing_information: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    candidate_alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    human_approval_required: bool = False
    approval_item_id: Optional[str] = None
    workflow_status: str = Field(
        default="RECOMMENDATION_READY",
        description="INITIALIZED, ASSESSMENT_COMPLETED, RECOMMENDATION_READY, APPROVAL_PENDING, APPROVED, ALLOCATED, REJECTED, ESCALATED, FAILED"
    )
    decision_id: Optional[str] = None
    recommendation_timestamp: str
    state_version: int = 1

    model_config = ConfigDict(extra="ignore")


class HospitalWorkflowState(BaseModel):
    """
    Central typed workflow state carried through the hospital multi-agent pipeline.
    Preserves immutable input snapshots, agent-produced outputs, provenance, and audit metrics.
    """
    workflow_id: str = Field(..., description="Unique UUID for this workflow execution")
    tenant_id: str = Field(default="HOSP-DEFAULT")
    patient_id: str
    encounter_id: str
    correlation_id: str = Field(..., description="End-to-end request tracing identifier")
    workflow_status: str = Field(
        default="INITIALIZED",
        description="INITIALIZED, ASSESSMENT_COMPLETED, RECOMMENDATION_READY, APPROVAL_PENDING, APPROVED, ALLOCATED, REJECTED, ESCALATED, FAILED"
    )

    # Immutable Context Snapshots
    encounter_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Point-in-time encounter data")
    hospital_state_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Point-in-time hospital capacity snapshot")

    # Typed Agent Assessments
    triage_result: Optional[TriageResult] = None
    patient_flow_result: Optional[PatientFlowResult] = None
    resource_match_result: Optional[ResourceMatchResult] = None
    workforce_assessment: Optional[WorkforceAssessment] = None
    escalation_result: Optional[EscalationResult] = None

    # Telemetry, Diagnostics & Warnings
    warnings: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    agent_errors: List[Dict[str, Any]] = Field(default_factory=list)

    # Synthesis & Governance Gating
    recommendation: Optional[ConsolidatedRecommendation] = None
    approval_status: str = Field(default="NOT_REQUIRED", description="NOT_REQUIRED, PENDING, APPROVED, REJECTED")
    state_version: int = 1
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="ignore")
