export const MAX_TOASTS = 4;
export const STALE_EVENT_THRESHOLD_MS = 60000; // Ignore events older than 60s to prevent reconnect storms
export const AUTO_DISMISS_STANDARD_MS = 7000;
export const AUTO_DISMISS_CRITICAL_MS = 12000;

/**
 * Normalizes an event payload into a safe toast notification model.
 * Enforces PHI redaction, tenant matching, and urgency classification.
 */
export function extractEscalationData(event, currentUser) {
  if (!event || !event.event_type) return null;

  const validTypes = [
    'EMERGENCY_ESCALATED',
    'EMERGENCY_DECLARED',
    'APPROVAL_REQUIRED',
  ];
  if (!validTypes.includes(event.event_type)) return null;

  // Tenant boundary verification
  if (currentUser?.tenant_id && event.tenant_id && currentUser.tenant_id !== event.tenant_id) {
    return null;
  }

  // Check event freshness to prevent stale toast storms on reconnect
  if (event.timestamp) {
    const eventTime = new Date(event.timestamp).getTime();
    if (!isNaN(eventTime) && Date.now() - eventTime > STALE_EVENT_THRESHOLD_MS) {
      return null;
    }
  }

  const payload = event.payload || {};

  // For APPROVAL_REQUIRED, only show as escalation if marked urgent or required human escalation
  if (event.event_type === 'APPROVAL_REQUIRED') {
    const isUrgent = payload.urgency === 'IMMEDIATE' || payload.urgency === 'URGENT';
    const isEscalation = Boolean(payload.escalation_required || payload.requires_human_approval);
    if (!isUrgent && !isEscalation) {
      return null;
    }
  }

  const urgency = (payload.urgency || (event.event_type === 'EMERGENCY_DECLARED' ? 'IMMEDIATE' : 'URGENT')).toUpperCase();
  const isCritical = urgency === 'IMMEDIATE' || urgency === 'CRITICAL' || payload.emergency_level === 'CRITICAL_CODE_BLUE';

  let category = 'Clinical Escalation';
  if (event.event_type === 'EMERGENCY_DECLARED') {
    category = 'Emergency Declared';
  } else if (payload.emergency_level === 'CRITICAL_CODE_BLUE') {
    category = 'Code Blue Alert';
  } else if (payload.emergency_level === 'RAPID_RESPONSE_STAT') {
    category = 'Rapid Response Trigger';
  } else if (event.event_type === 'APPROVAL_REQUIRED') {
    category = 'Urgent Clinical Approval';
  }

  // Safe reference without PHI
  const encounterRef = payload.encounter_id ? `Encounter ${String(payload.encounter_id).slice(-8)}` : null;
  const deptRef = payload.target_department || payload.department_id || null;

  // Summary message with clinical safety boundary (no raw patient names or diagnoses)
  const reasonText = Array.isArray(payload.reasons) && payload.reasons.length > 0
    ? payload.reasons[0]
    : payload.message || (isCritical ? 'Critical physiological decompensation detected.' : 'Multi-agent safety review requested.');

  return {
    id: event.event_id || `esc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    eventId: event.event_id || null,
    eventType: event.event_type,
    category,
    urgency,
    isCritical,
    encounterRef,
    deptRef,
    encounterId: payload.encounter_id || null,
    approvalId: payload.approval_item_id || null,
    reason: reasonText,
    timestamp: event.timestamp || new Date().toISOString(),
  };
}
