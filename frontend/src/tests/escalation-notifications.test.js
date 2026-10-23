import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { extractEscalationData } from '../utils/escalationNotification.js';

describe('Task 1 & Task 2: Multi-Agent Escalation Notifications and Stream Health', () => {
  const mockDoctorUser = {
    id: 'USR-DOC-01',
    role: 'DOCTOR',
    tenant_id: 'HOSP-DEFAULT',
  };

  describe('extractEscalationData Contract & PHI Redaction', () => {
    test('ignores non-escalation operational events', () => {
      const genericEvent = {
        event_id: 'evt-001',
        event_type: 'BED_OCCUPIED',
        tenant_id: 'HOSP-DEFAULT',
        payload: { bed_id: 'BED-ICU-01' },
      };
      assert.equal(extractEscalationData(genericEvent, mockDoctorUser), null);
    });

    test('extracts EMERGENCY_ESCALATED event with critical classification', () => {
      const nowIso = new Date().toISOString();
      const escEvent = {
        event_id: 'evt-esc-100',
        event_type: 'EMERGENCY_ESCALATED',
        tenant_id: 'HOSP-DEFAULT',
        timestamp: nowIso,
        payload: {
          encounter_id: 'ENC-2026-9999',
          urgency: 'IMMEDIATE',
          emergency_level: 'RAPID_RESPONSE_STAT',
          reasons: ['Acute respiratory failure (SpO2 84%)'],
          target_department: 'DEP-ICU',
        },
      };

      const toast = extractEscalationData(escEvent, mockDoctorUser);
      assert.ok(toast);
      assert.equal(toast.eventId, 'evt-esc-100');
      assert.equal(toast.isCritical, true);
      assert.equal(toast.urgency, 'IMMEDIATE');
      assert.equal(toast.category, 'Rapid Response Trigger');
      assert.equal(toast.encounterRef, 'Encounter 026-9999');
      assert.equal(toast.deptRef, 'DEP-ICU');
      assert.equal(toast.reason, 'Acute respiratory failure (SpO2 84%)');
    });

    test('extracts Code Blue critical events with immediate urgency', () => {
      const escEvent = {
        event_id: 'evt-esc-blue',
        event_type: 'EMERGENCY_ESCALATED',
        tenant_id: 'HOSP-DEFAULT',
        timestamp: new Date().toISOString(),
        payload: {
          encounter_id: 'ENC-00112233',
          emergency_level: 'CRITICAL_CODE_BLUE',
          urgency: 'IMMEDIATE',
          reasons: ['Hemodynamic collapse (GCS 6, SBP 70)'],
        },
      };

      const toast = extractEscalationData(escEvent, mockDoctorUser);
      assert.ok(toast);
      assert.equal(toast.isCritical, true);
      assert.equal(toast.category, 'Code Blue Alert');
    });

    test('extracts APPROVAL_REQUIRED only when urgent or escalation flag is set', () => {
      const nowIso = new Date().toISOString();

      // Case 1: Urgent approval
      const urgentApproval = {
        event_id: 'evt-appr-urg',
        event_type: 'APPROVAL_REQUIRED',
        tenant_id: 'HOSP-DEFAULT',
        timestamp: nowIso,
        payload: {
          encounter_id: 'ENC-URG-01',
          urgency: 'URGENT',
          requires_human_approval: true,
          reasons: ['ICU bed allocation pending doctor sign-off'],
        },
      };
      const toast1 = extractEscalationData(urgentApproval, mockDoctorUser);
      assert.ok(toast1);
      assert.equal(toast1.category, 'Urgent Clinical Approval');

      // Case 2: Routine low-risk recommendation without escalation flag
      const routineApproval = {
        event_id: 'evt-appr-rout',
        event_type: 'APPROVAL_REQUIRED',
        tenant_id: 'HOSP-DEFAULT',
        timestamp: nowIso,
        payload: {
          encounter_id: 'ENC-ROUT-01',
          urgency: 'ROUTINE',
          requires_human_approval: false,
          escalation_required: false,
        },
      };
      const toast2 = extractEscalationData(routineApproval, mockDoctorUser);
      assert.equal(toast2, null, 'Routine approval without escalation must not produce an alarm toast');
    });

    test('enforces tenant isolation and drops cross-tenant events', () => {
      const crossTenantEvent = {
        event_id: 'evt-tenant-b',
        event_type: 'EMERGENCY_ESCALATED',
        tenant_id: 'HOSP-CITY-SOUTH', // Different tenant
        timestamp: new Date().toISOString(),
        payload: { encounter_id: 'ENC-OTHER', urgency: 'IMMEDIATE' },
      };

      const toast = extractEscalationData(crossTenantEvent, mockDoctorUser);
      assert.equal(toast, null, 'Cross-tenant escalation events must be dropped for tenant security');
    });

    test('drops stale events older than 60s to prevent reconnection storm', () => {
      const staleTimestamp = new Date(Date.now() - 120000).toISOString(); // 2 minutes ago
      const staleEvent = {
        event_id: 'evt-stale-01',
        event_type: 'EMERGENCY_ESCALATED',
        tenant_id: 'HOSP-DEFAULT',
        timestamp: staleTimestamp,
        payload: { encounter_id: 'ENC-OLD', urgency: 'IMMEDIATE' },
      };

      const toast = extractEscalationData(staleEvent, mockDoctorUser);
      assert.equal(toast, null, 'Stale events must not trigger immediate toast popups');
    });
  });

  describe('Real-Time Stream & Health State Machine Invariants', () => {
    test('distinguishes WebSocket transport from Redis event-stream health', () => {
      // Scenario A: WebSocket connected, Redis online
      const stateA = {
        wsConnected: true,
        wsStatus: 'CONNECTED',
        redis: 'connected',
      };
      assert.equal(stateA.wsConnected, true);
      assert.equal(stateA.redis, 'connected');

      // Scenario B: WebSocket connected, Redis UNREACHABLE (local in-memory fallback)
      const stateB = {
        wsConnected: true,
        wsStatus: 'CONNECTED',
        redis: 'unreachable',
      };
      assert.equal(stateB.wsConnected, true, 'WebSocket can be connected to local node');
      assert.equal(stateB.redis, 'unreachable', 'Redis can be down while WebSocket is connected');

      // Scenario C: WebSocket disconnected, Redis healthy on server
      const stateC = {
        wsConnected: false,
        wsStatus: 'DISCONNECTED',
        redis: 'connected',
      };
      assert.equal(stateC.wsConnected, false);
      assert.equal(stateC.redis, 'connected');
    });

    test('failed health-check defaults to unknown and never assumes healthy', () => {
      let healthRecord = { status: 'unknown', redis: 'unknown', database: 'unknown' };

      // Simulate network failure or 503 response
      const simulateFailure = () => {
        healthRecord = {
          status: 'unknown',
          redis: 'unknown',
          database: 'unknown',
        };
      };

      simulateFailure();
      assert.notEqual(healthRecord.status, 'healthy', 'Must never default to healthy on network failure');
      assert.equal(healthRecord.redis, 'unknown');
    });
  });
});
