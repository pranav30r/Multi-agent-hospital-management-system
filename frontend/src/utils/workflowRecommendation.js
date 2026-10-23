/**
 * Utility functions and data contracts for Hospital Multi-Agent Workflow
 * Recommendations, Approvals, and Authoritative Outcome State.
 */

export const WORKFLOW_STATUS_CONFIG = {
  INITIALIZED: { label: 'Initializing', pillClass: 'status-neutral' },
  ASSESSMENT_COMPLETED: { label: 'Assessment Completed', pillClass: 'status-neutral' },
  RECOMMENDATION_READY: { label: 'Recommendation Ready', pillClass: 'status-available' },
  APPROVAL_PENDING: { label: 'Pending Human Approval', pillClass: 'status-reserved' },
  APPROVED: { label: 'Approved (Awaiting Execution)', pillClass: 'status-available' },
  ALLOCATED: { label: 'Allocation Confirmed', pillClass: 'status-occupied' },
  REJECTED: { label: 'Rejected', pillClass: 'status-blocked' },
  ESCALATED: { label: 'Escalated to Supervisory', pillClass: 'status-danger' },
  FAILED: { label: 'Failed / Blocked', pillClass: 'status-danger' },
};

export const DEPARTMENT_NAMES = {
  'DEP-ER': 'Emergency Department',
  'DEP-ICU': 'Intensive Care Unit',
  'DEP-CARD': 'Cardiology & Telemetry Unit',
  'DEP-GEN': 'General Inpatient Ward',
  'DEP-WA': 'General Ward A',
  'DEP-WB': 'General Ward B',
  'DEP-SURG': 'Surgical Inpatient Ward',
};

/**
 * Extracts and normalizes structured details from either an ApprovalItem or a HospitalWorkflowState.
 */
export function extractRecommendationDetails(source) {
  if (!source) return null;

  // Handle ApprovalItem structure
  if (source.action_type || source.proposed_action) {
    const proposed = source.proposed_action || {};
    const context = proposed.decision_context || {};
    const triage = context.triage || {};
    const flow = context.patient_flow || {};
    const bedRes = context.bed_resources || {};
    const staff = context.staffing || {};
    const esc = context.escalation || {};

    const rawDept = proposed.department_id || proposed.target_department || proposed.target_department_id || flow.target_department;
    const deptId = (rawDept && String(rawDept).toLowerCase() !== 'none') ? rawDept : ((triage.esi_level <= 2 || source.risk_level === 'CRITICAL' || source.risk_level === 'HIGH') ? 'DEP-ICU' : 'DEP-ER');
    const rawBed = proposed.target_bed_id || proposed.bed_id || bedRes.recommended_bed_id;
    const proposedBed = (rawBed && String(rawBed).toLowerCase() !== 'none' && String(rawBed).toLowerCase() !== 'null') ? rawBed : null;

    let wfRationale = staff.rationale || null;
    if (wfRationale && wfRationale.includes('0.0:1')) {
      wfRationale = wfRationale.replace(/Avg Nurse Ratio:\s*0\.0:1\.?/gi, 'Active Nurse Load: 0 assigned patients (full capacity available).');
    }

    return {
      id: source.id,
      decisionId: source.decision_id,
      encounterId: proposed.encounter_id || flow.encounter_id || 'ENC-PENDING',
      patientId: proposed.patient_id || source.patient_id || 'PAT-PENDING',
      patientName: source.patient_name || null,
      departmentId: deptId,
      departmentName: DEPARTMENT_NAMES[deptId] || deptId,
      proposedBedId: proposedBed,
      bedType: proposed.bed_type || bedRes.recommended_bed_type || 'STANDARD',
      triagePriority: proposed.urgency || triage.priority_level || source.risk_level || 'ROUTINE',
      esiLevel: triage.esi_level || (source.risk_level === 'CRITICAL' ? 1 : source.risk_level === 'HIGH' ? 2 : 3),
      triageRationale: triage.rationale || source.reasoning || 'Standard clinical intake evaluation.',
      flowRationale: flow.rationale || (flow.workflow_phase ? `Route to ${flow.workflow_phase}` : (deptId ? `Route to ${DEPARTMENT_NAMES[deptId] || deptId} for care.` : 'Awaiting clinical routing')),
      resourceRationale: bedRes.rationale || source.reasoning || (proposedBed ? `Assigned bed ${proposedBed}` : `No compatible bed currently available in ${DEPARTMENT_NAMES[deptId] || deptId}`),
      workforceRationale: wfRationale,
      assignedDoctorId: proposed.assigned_doctor_id || staff.assigned_doctor_id,
      assignedNurseId: proposed.assigned_nurse_id || staff.assigned_nurse_id,
      staffingFeasibility: staff.feasibility || 'FEASIBLE',
      urgency: proposed.urgency || esc.urgency || (source.risk_level === 'CRITICAL' ? 'IMMEDIATE' : 'ROUTINE'),
      emergencyLevel: proposed.emergency_level || esc.emergency_level || 'STANDARD_MONITORING',
      escalationRequired: Boolean(proposed.escalation_required || esc.escalation_required || source.risk_level === 'CRITICAL'),
      escalationReasons: esc.escalation_reasons || [],
      requiredHumanActions: esc.required_human_actions || [],
      candidateAlternatives: source.alternatives || bedRes.alternative_beds || [],
      warnings: flow.bottlenecks_identified || triage.missing_information || [],
      workflowStatus: source.status === 'PENDING' ? 'APPROVAL_PENDING' : source.status,
      confidence: source.confidence ?? bedRes.confidence ?? 0.9,
      riskLevel: source.risk_level || 'MEDIUM',
      createdAt: source.created_at || new Date().toISOString(),
      rawSource: source,
    };
  }

  // Handle HospitalWorkflowState structure
  const rec = source.recommendation || {};
  const triage = source.triage_result || {};
  const flow = source.patient_flow_result || {};
  const bedRes = source.resource_match_result || {};
  const staff = source.workforce_assessment || {};
  const esc = source.escalation_result || {};

  const rawStateDept = rec.recommended_department || flow.target_department;
  const deptId = (rawStateDept && String(rawStateDept).toLowerCase() !== 'none') ? rawStateDept : ((triage.esi_level <= 2 || esc.urgency === 'IMMEDIATE') ? 'DEP-ICU' : 'DEP-ER');
  const rawStateBed = rec.recommended_bed_id || bedRes.recommended_bed_id;
  const proposedBed = (rawStateBed && String(rawStateBed).toLowerCase() !== 'none' && String(rawStateBed).toLowerCase() !== 'null') ? rawStateBed : null;

  return {
    id: rec.approval_item_id || source.workflow_id,
    decisionId: rec.decision_id,
    encounterId: source.encounter_id,
    patientId: source.patient_id,
    patientName: source.encounter_snapshot?.patient_name || null,
    departmentId: deptId,
    departmentName: DEPARTMENT_NAMES[deptId] || deptId,
    proposedBedId: proposedBed,
    bedType: bedRes.recommended_bed_type || 'STANDARD',
    triagePriority: rec.triage_priority || triage.priority_level || 'ROUTINE',
    esiLevel: triage.esi_level || 3,
    triageRationale: rec.triage_rationale || triage.rationale || 'Evaluation completed.',
    flowRationale: flow.rationale || rec.patient_flow_action || (deptId ? `Route to ${DEPARTMENT_NAMES[deptId] || deptId} for clinical evaluation.` : 'Awaiting clinical routing'),
    resourceRationale: bedRes.rationale || (proposedBed ? `Assigned bed ${proposedBed}` : `No compatible bed currently available in ${DEPARTMENT_NAMES[deptId] || deptId}`),
    workforceRationale: (() => {
      let wr = staff.rationale;
      if (wr && wr.includes('0.0:1')) {
        wr = wr.replace(/Avg Nurse Ratio:\s*0\.0:1\.?/gi, 'Active Nurse Load: 0 assigned patients (full capacity available).');
      }
      return wr;
    })(),
    assignedDoctorId: staff.assigned_doctor_id,
    assignedNurseId: staff.assigned_nurse_id,
    staffingFeasibility: staff.feasibility || 'FEASIBLE',
    urgency: esc.urgency || 'ROUTINE',
    emergencyLevel: esc.emergency_level || 'STANDARD_MONITORING',
    escalationRequired: Boolean(esc.escalation_required || source.workflow_status === 'ESCALATED'),
    escalationReasons: esc.escalation_reasons || [],
    requiredHumanActions: esc.required_human_actions || [],
    candidateAlternatives: rec.candidate_alternatives || bedRes.alternative_beds || [],
    warnings: source.warnings || rec.warnings || [],
    workflowStatus: source.workflow_status || 'RECOMMENDATION_READY',
    confidence: bedRes.confidence ?? 0.85,
    riskLevel: esc.urgency === 'IMMEDIATE' ? 'CRITICAL' : esc.urgency === 'URGENT' ? 'HIGH' : 'MEDIUM',
    createdAt: rec.recommendation_timestamp || new Date().toISOString(),
    rawSource: source,
  };
}

/**
 * Formats server-confirmed outcome feedback after clinician review.
 */
export function formatAuthoritativeOutcome(reviewResponse, proposedBedId) {
  if (!reviewResponse) return null;
  const status = reviewResponse.review_action || reviewResponse.status;
  const reviewer = reviewResponse.reviewed_by || 'Attending Clinician';
  const timeStr = reviewResponse.reviewed_at ? new Date(reviewResponse.reviewed_at).toLocaleTimeString() : new Date().toLocaleTimeString();

  const isApproved = ['APPROVE', 'APPROVED', 'MODIFY', 'MODIFIED'].includes(status);
  const isRejected = ['REJECT', 'REJECTED'].includes(status);

  const finalBedId = reviewResponse.modification?.target_bed_id || proposedBedId || 'Bed Station';

  return {
    status,
    isApproved,
    isRejected,
    allocatedBedId: isApproved ? finalBedId : null,
    reviewer,
    timestamp: timeStr,
    message: isApproved
      ? `✓ Server Confirmed: Bed ${finalBedId} authoritatively RESERVED by ${reviewer} at ${timeStr}.`
      : `✕ Rejection Confirmed: Recommendation declined by ${reviewer} at ${timeStr}. Bed was NOT reserved.`,
  };
}

/**
 * Translates backend API conflict / validation errors into understandable clinician guidance.
 */
export function formatConflictError(error) {
  if (!error) return 'An unexpected error occurred while communicating with the hospital workflow engine.';
  const msg = typeof error === 'string' ? error : error.message || String(error);

  if (msg.includes('not available for reservation') || msg.includes('state and cannot be booked') || msg.includes('already in')) {
    return 'Resource Conflict: The proposed bed has already been booked or is no longer available in this department. Please choose an alternative bed or recalculate recommendations.';
  }
  if (msg.includes('already assigned to another active patient') || msg.includes('workload capacity')) {
    return 'Staffing Conflict: The proposed clinician is currently at capacity or assigned to another active case. Please modify clinician assignment.';
  }
  if (msg.includes('Tenant mismatch') || msg.includes('403')) {
    return 'Authorization Error: You do not have permission to access or modify records for this hospital partition.';
  }
  if (msg.includes('401') || msg.includes('unauthorized') || msg.includes('credentials')) {
    return 'Authentication Required: Active clinician credentials required to execute this action.';
  }
  return msg;
}
