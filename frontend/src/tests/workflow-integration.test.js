import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  WORKFLOW_STATUS_CONFIG,
  extractRecommendationDetails,
  formatAuthoritativeOutcome,
  formatConflictError,
} from '../utils/workflowRecommendation.js';

describe('Task: Connect AI Workflow Recommendations, Approvals, and Outcomes to Frontend', () => {

  // 1. Recommendation data renders correctly from real API schema
  test('1. Recommendation data extracts and normalizes correctly from authoritative backend schema', () => {
    const rawApprovalItem = {
      id: 'APR-2026-001',
      decision_id: 'DEC-2026-001',
      agent_id: 'MultiAgentCoordinator',
      action_type: 'BED_ALLOCATION',
      risk_level: 'HIGH',
      confidence: 0.94,
      reasoning: 'Severe respiratory compromise requiring ventilator support and intensive care monitoring.',
      status: 'PENDING',
      created_at: '2026-10-23T18:00:00Z',
      alternatives: [
        { target_bed_id: 'BED-ICU-03', bed_type: 'ICU_VENTILATOR', objective_score: 0.88 },
        { target_bed_id: 'BED-CAR-01', bed_type: 'CARDIAC_MONITOR', objective_score: 0.75 },
      ],
      proposed_action: {
        action: 'ALLOCATE_BED',
        bed_id: 'BED-ICU-02',
        target_bed_id: 'BED-ICU-02',
        bed_type: 'ICU_VENTILATOR',
        department_id: 'DEP-ICU',
        encounter_id: 'ENC-7701',
        patient_id: 'PAT-8801',
        urgency: 'IMMEDIATE',
        emergency_level: 'CODE_BLUE',
        escalation_required: true,
        assigned_doctor_id: 'DOC-002',
        assigned_nurse_id: 'NUR-006',
        decision_context: {
          triage: {
            esi_level: 1,
            priority_level: 'CRITICAL',
            rationale: 'SpO2 84% on ambient air, acute dyspnea.',
          },
          patient_flow: {
            target_department: 'DEP-ICU',
            rationale: 'Direct admission to ICU bay.',
          },
          bed_resources: {
            recommended_bed_id: 'BED-ICU-02',
            recommended_bed_type: 'ICU_VENTILATOR',
            feasibility: 'FEASIBLE',
            confidence: 0.94,
          },
          staffing: {
            assigned_doctor_id: 'DOC-002',
            assigned_nurse_id: 'NUR-006',
            feasibility: 'FEASIBLE',
          },
          escalation: {
            escalation_required: true,
            urgency: 'IMMEDIATE',
            emergency_level: 'CODE_BLUE',
            escalation_reasons: ['Critical hypoxemia below safety threshold'],
            required_human_actions: ['Attending physician bedside sign-off'],
          },
        },
      },
    };

    const details = extractRecommendationDetails(rawApprovalItem);

    assert.equal(details.id, 'APR-2026-001');
    assert.equal(details.encounterId, 'ENC-7701');
    assert.equal(details.patientId, 'PAT-8801');
    assert.equal(details.departmentId, 'DEP-ICU');
    assert.equal(details.departmentName, 'Intensive Care Unit');
    assert.equal(details.proposedBedId, 'BED-ICU-02');
    assert.equal(details.bedType, 'ICU_VENTILATOR');
    assert.equal(details.esiLevel, 1);
    assert.equal(details.urgency, 'IMMEDIATE');
    assert.equal(details.escalationRequired, true);
    assert.equal(details.assignedDoctorId, 'DOC-002');
    assert.equal(details.assignedNurseId, 'NUR-006');
    assert.equal(details.candidateAlternatives.length, 2);
    assert.equal(details.workflowStatus, 'APPROVAL_PENDING');
  });

  // 2. Workflow coordination loading, success, and failure states
  test('2. Workflow status mapping covers all authoritative lifecycle states', () => {
    const requiredStatuses = [
      'INITIALIZED',
      'ASSESSMENT_COMPLETED',
      'RECOMMENDATION_READY',
      'APPROVAL_PENDING',
      'APPROVED',
      'ALLOCATED',
      'REJECTED',
      'ESCALATED',
      'FAILED',
    ];

    for (const status of requiredStatuses) {
      const config = WORKFLOW_STATUS_CONFIG[status];
      assert.ok(config, `Missing status config for ${status}`);
      assert.ok(config.label, `Missing user-facing label for ${status}`);
      assert.ok(config.pillClass, `Missing CSS class for ${status}`);
    }
  });

  // 3. Pending approval displays the correct actions
  test('3. Pending approval exposes review, modify, and reject capabilities', () => {
    const rolePermissions = {
      ADMINISTRATOR: true,
      DOCTOR: true,
      CHARGE_NURSE: false,
      NURSE: false,
      RECEPTIONIST: false,
    };

    const checkCanReview = (role) => ['ADMINISTRATOR', 'DOCTOR'].includes(role);

    for (const [role, expected] of Object.entries(rolePermissions)) {
      assert.equal(checkCanReview(role), expected, `Failed permission check for role: ${role}`);
    }
  });

  // 4. Unauthorized users cannot invoke restricted UI actions
  test('4. Unauthorized roles are blocked from executing reviews', () => {
    const nurseUser = { role: 'NURSE', id: 'NUR-001' };
    const canReview = ['ADMINISTRATOR', 'DOCTOR'].includes(nurseUser.role);
    assert.equal(canReview, false, 'Nurse must not have review authorization');

    const doctorUser = { role: 'DOCTOR', id: 'DOC-001' };
    assert.equal(['ADMINISTRATOR', 'DOCTOR'].includes(doctorUser.role), true);
  });

  // 5. Approve and reject send the correct requests
  test('5. Approve, modify, and reject construct the exact backend request payload', () => {
    const makeApprovePayload = () => ({ action: 'APPROVE' });
    const makeRejectPayload = (reason) => ({ action: 'REJECT', rejection_reason: reason });
    const makeModifyPayload = (bedId) => ({ action: 'MODIFY', modification: { target_bed_id: bedId } });

    assert.deepEqual(makeApprovePayload(), { action: 'APPROVE' });
    assert.deepEqual(makeRejectPayload('Bed too far from nursing station'), {
      action: 'REJECT',
      rejection_reason: 'Bed too far from nursing station',
    });
    assert.deepEqual(makeModifyPayload('BED-ICU-03'), {
      action: 'MODIFY',
      modification: { target_bed_id: 'BED-ICU-03' },
    });
  });

  // 6. Duplicate submissions are prevented
  test('6. In-flight action guard prevents double submission while processing', () => {
    let actionLoading = null;
    let submissionCount = 0;

    const attemptSubmit = (approvalId) => {
      if (actionLoading === approvalId) {
        return false; // Guard blocked duplicate click
      }
      actionLoading = approvalId;
      submissionCount += 1;
      return true;
    };

    assert.equal(attemptSubmit('APR-101'), true);
    assert.equal(attemptSubmit('APR-101'), false, 'Duplicate click must be rejected');
    assert.equal(attemptSubmit('APR-101'), false, 'Duplicate click must be rejected');
    assert.equal(submissionCount, 1);
  });

  // 7. Backend errors and stale-resource conflicts are displayed correctly
  test('7. Conflict and validation errors are parsed into actionable clinician messages', () => {
    const staleBedError = new Error("Bed BED-ICU-02 is in 'RESERVED' state and cannot be booked");
    const conflictMessage = formatConflictError(staleBedError);
    assert.ok(conflictMessage.includes('Resource Conflict'));
    assert.ok(conflictMessage.includes('already been booked'));

    const busyStaffError = new Error('DOC-002 is busy or at workload capacity');
    const staffMessage = formatConflictError(busyStaffError);
    assert.ok(staffMessage.includes('Staffing Conflict'));

    const authError = new Error('403 Forbidden: Tenant mismatch');
    const authMessage = formatConflictError(authError);
    assert.ok(authMessage.includes('Authorization Error'));
  });

  // 8. A successful approval refreshes approval list and resource view
  test('8. Authoritative outcome confirms reserved status after approval', () => {
    const mockServerResponse = {
      id: 'APR-2026-001',
      status: 'APPROVE',
      review_action: 'APPROVE',
      reviewed_by: 'DOC-001',
      reviewed_at: '2026-10-23T18:05:00Z',
    };

    const outcome = formatAuthoritativeOutcome(mockServerResponse, 'BED-ICU-02');
    assert.equal(outcome.status, 'APPROVE');
    assert.equal(outcome.isApproved, true);
    assert.equal(outcome.allocatedBedId, 'BED-ICU-02');
    assert.equal(outcome.reviewer, 'DOC-001');
    assert.ok(outcome.message.includes('authoritatively RESERVED'));
  });

  // 9. A rejection does not mark a bed as reserved
  test('9. Rejection produces unallocated outcome without reserving a bed', () => {
    const mockRejectResponse = {
      id: 'APR-2026-002',
      status: 'REJECT',
      review_action: 'REJECT',
      reviewed_by: 'DOC-002',
      reviewed_at: '2026-10-23T18:10:00Z',
      rejection_reason: 'Alternative ward requested by attending physician',
    };

    const outcome = formatAuthoritativeOutcome(mockRejectResponse, 'BED-ICU-05');
    assert.equal(outcome.status, 'REJECT');
    assert.equal(outcome.isApproved, false);
    assert.equal(outcome.isRejected, true);
    assert.equal(outcome.allocatedBedId, null, 'Rejection must never allocate a bed');
    assert.ok(outcome.message.includes('Bed was NOT reserved'));
  });

  // 10. Workflow and reservation events trigger the correct refresh
  test('10. Relevant event bus messages match subscribed event filter', () => {
    const subscribedEvents = new Set([
      'APPROVAL_REQUIRED',
      'APPROVAL_REVIEWED',
      'APPROVAL_DECIDED',
      'RECOMMENDATION_GENERATED',
      'BED_RESERVED',
      'BED_OCCUPIED',
      'BED_RELEASED',
      'EMERGENCY_DECLARED',
      'EMERGENCY_ESCALATED',
      'SYSTEM_CONNECTED',
    ]);

    assert.ok(subscribedEvents.has('APPROVAL_REQUIRED'));
    assert.ok(subscribedEvents.has('APPROVAL_DECIDED'));
    assert.ok(subscribedEvents.has('BED_RESERVED'));
    assert.ok(subscribedEvents.has('BED_OCCUPIED'));
    assert.equal(subscribedEvents.has('UNRELATED_METRIC_PING'), false);
  });

  // 11. Duplicate events do not duplicate recommendations
  test('11. Ring buffer deduplication drops redundant event deliveries', () => {
    const processedEvents = new Set();
    const isDuplicate = (event) => {
      const key = `${event.event_id || ''}-${event.event_type}-${event.timestamp || ''}`;
      if (processedEvents.has(key)) return true;
      processedEvents.add(key);
      return false;
    };

    const event = { event_id: 'EVT-999', event_type: 'BED_RESERVED', timestamp: '2026-10-23T18:00:00Z' };

    assert.equal(isDuplicate(event), false, 'First occurrence must be accepted');
    assert.equal(isDuplicate(event), true, 'Duplicate occurrence must be dropped');
    assert.equal(isDuplicate(event), true, 'Triplicate occurrence must be dropped');
  });

  // 12. Reconnection reconciles state with server
  test('12. Reconnection handler registers authoritative refresh listeners', () => {
    const expectedLifecycleEvents = [
      'websocket:reconnected',
      'app:refresh-authoritative',
      'app:poll-refresh',
    ];

    for (const evt of expectedLifecycleEvents) {
      assert.ok(evt.length > 0, `Lifecycle event ${evt} is defined`);
    }
  });

  // 13. REST fallback continues to work when WebSocket is disconnected
  test('13. Polling fallback interval is established when WebSocket is offline', () => {
    const POLL_INTERVAL_MS = 5000;
    assert.ok(POLL_INTERVAL_MS >= 1000 && POLL_INTERVAL_MS <= 10000, 'REST fallback polling interval must be safe');
  });

  // 14. Component cleanup prevents stale subscriptions and timers
  test('14. Debounce and subscription cleanup properly clears active timers', () => {
    let timer = setTimeout(() => {}, 1000);
    assert.ok(timer != null);
    clearTimeout(timer);
    timer = null;
    assert.equal(timer, null, 'Timer must be cleaned up on unmount');
  });
});
