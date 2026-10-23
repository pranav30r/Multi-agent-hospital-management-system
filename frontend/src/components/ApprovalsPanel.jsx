import { useEffect, useState, useCallback, useRef } from 'react';
import { listApprovalHistory, listPendingApprovals, reviewApproval } from '../api/approvals.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { listBeds } from '../api/beds.js';
import { Icon } from './common/Icon.jsx';
import {
  WORKFLOW_STATUS_CONFIG,
  extractRecommendationDetails,
  formatAuthoritativeOutcome,
  formatConflictError,
} from '../utils/workflowRecommendation.js';

function ApprovalsPanel() {
  const { user } = useAuth();
  const { lastEvent } = useEvents();
  const { demoMode, demoData } = useDemo();

  const [approvals, setApprovals] = useState([]);
  const [history, setHistory] = useState([]);
  const [activeTab, setActiveTab] = useState('pending'); // 'pending' | 'history'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // In-flight tracking & duplicate prevention
  const [actionLoading, setActionLoading] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectingId, setRejectingId] = useState(null);
  const [modifyingId, setModifyingId] = useState(null);
  const [availableBeds, setAvailableBeds] = useState([]);
  const [selectedBedId, setSelectedBedId] = useState('');

  // Authoritative server-confirmed outcomes & item conflicts
  const [authoritativeOutcome, setAuthoritativeOutcome] = useState(null);
  const [itemErrors, setItemErrors] = useState({});

  const canReview = user && ['ADMINISTRATOR', 'DOCTOR'].includes(user.role);

  const fetchApprovals = useCallback(async () => {
    if (demoMode) {
      setApprovals(demoData.approvals || []);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await listPendingApprovals();
      setApprovals(data || []);
    } catch (err) {
      setError(formatConflictError(err));
    } finally {
      setLoading(false);
    }
  }, [demoMode, demoData]);

  const fetchHistory = useCallback(async () => {
    if (demoMode) return;
    try {
      const data = await listApprovalHistory();
      setHistory(data || []);
    } catch (err) {
      setError(formatConflictError(err));
    }
  }, [demoMode]);

  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchApprovals();
    }, 200);
  }, [fetchApprovals]);

  useEffect(() => {
    fetchApprovals();
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchApprovals]);

  useEffect(() => {
    if (activeTab === 'history') fetchHistory();
  }, [activeTab, fetchHistory]);

  // Real-time Event Subscription with Deduplication
  const processedEventsRef = useRef(new Set());
  useEffect(() => {
    if (!lastEvent) return;

    const eventKey = `${lastEvent.event_id || ''}-${lastEvent.event_type}-${lastEvent.timestamp || ''}`;
    if (lastEvent.event_id && processedEventsRef.current.has(eventKey)) return;
    if (lastEvent.event_id) {
      processedEventsRef.current.add(eventKey);
      if (processedEventsRef.current.size > 100) {
        const first = processedEventsRef.current.values().next().value;
        processedEventsRef.current.delete(first);
      }
    }

    const relevantEventTypes = [
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
    ];

    if (relevantEventTypes.includes(lastEvent.event_type)) {
      debouncedFetch();
      if (activeTab === 'history') fetchHistory();
    }
  }, [lastEvent, debouncedFetch, fetchHistory, activeTab]);

  useEffect(() => {
    const handler = () => {
      debouncedFetch();
      fetchHistory();
    };
    window.addEventListener('websocket:reconnected', handler);
    window.addEventListener('app:refresh-authoritative', handler);
    window.addEventListener('app:poll-refresh', handler);
    return () => {
      window.removeEventListener('websocket:reconnected', handler);
      window.removeEventListener('app:refresh-authoritative', handler);
      window.removeEventListener('app:poll-refresh', handler);
    };
  }, [debouncedFetch, fetchHistory]);

  const handleReview = async (approvalId, action, reason, modification) => {
    if (actionLoading === approvalId) return; // Prevent duplicate clicks
    setActionLoading(approvalId);
    setItemErrors((prev) => ({ ...prev, [approvalId]: null }));

    const targetItem = approvals.find((a) => a.id === approvalId);
    const details = extractRecommendationDetails(targetItem);

    try {
      let result = null;
      if (!demoMode) {
        const body = { action };
        if (action === 'REJECT' && reason) body.rejection_reason = reason;
        if (action === 'MODIFY') body.modification = modification;
        result = await reviewApproval(approvalId, body);
        await Promise.all([fetchApprovals(), fetchHistory()]);
      } else {
        result = {
          id: approvalId,
          status: action,
          review_action: action,
          reviewed_by: user ? `${user.first_name || ''} ${user.last_name || ''}`.trim() : 'Attending Physician',
          reviewed_at: new Date().toISOString(),
          rejection_reason: reason,
          modification,
        };
      }

      // Authoritative outcome presentation
      const outcome = formatAuthoritativeOutcome(result, details?.proposedBedId);
      setAuthoritativeOutcome(outcome);

      // Dispatch cross-view sync events
      const targetBed = modification?.target_bed_id || details?.proposedBedId;
      if (action === 'APPROVE' || action === 'MODIFY') {
        window.dispatchEvent(
          new CustomEvent('bed:updated', {
            detail: {
              bedId: targetBed,
              status: 'RESERVED',
              patientId: details?.patientId,
              encounterId: details?.encounterId,
            },
          })
        );
      }
      window.dispatchEvent(new CustomEvent('patient:updated'));
      window.dispatchEvent(new CustomEvent('app:refresh-authoritative'));

      // Clean local transient review states
      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      setRejectingId(null);
      setModifyingId(null);
      setSelectedBedId('');
      setRejectReason('');
    } catch (err) {
      const formatted = formatConflictError(err);
      setItemErrors((prev) => ({ ...prev, [approvalId]: formatted }));
      // Dispatch refresh so user has updated state on conflict
      window.dispatchEvent(new CustomEvent('app:refresh-authoritative'));
    } finally {
      setActionLoading(null);
    }
  };

  const beginModification = async (item) => {
    setError(null);
    setItemErrors((prev) => ({ ...prev, [item.id]: null }));
    try {
      const beds = await listBeds(undefined, 'AVAILABLE');
      const alternatives = item.alternatives || [];
      const supportedBedIds = new Set(
        [
          item.proposed_action?.target_bed_id,
          item.proposed_action?.bed_id,
          ...alternatives.map((candidate) => candidate.target_bed_id || candidate.bed_id),
        ].filter(Boolean)
      );

      // Prefer candidate alternatives if present, else fallback to all available beds
      const eligibleBeds = beds.filter((bed) => supportedBedIds.size === 0 || supportedBedIds.has(bed.id));
      setAvailableBeds(eligibleBeds.length > 0 ? eligibleBeds : beds);
      setSelectedBedId(eligibleBeds[0]?.id || beds[0]?.id || '');
      setModifyingId(item.id);
    } catch (err) {
      setError(formatConflictError(err));
    }
  };

  return (
    <div className="approvals-container-clean">
      <div className="card approvals-card">
        {/* Header with Title and Tabs */}
        <div className="card-top-bar">
          <div>
            <div className="title-with-badge">
              <h2 className="card-heading">Clinical AI Approvals</h2>
              <span className={`status-pill ${approvals.length > 0 ? 'status-reserved' : 'status-available'}`}>
                {approvals.length} Pending Decision{approvals.length === 1 ? '' : 's'}
              </span>
            </div>
            <p className="card-subheading">
              Physician oversight gate: autonomous high-risk bed transfers and resource preemption require human sign-off.
            </p>
          </div>

          <div className="segmented-control" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'pending'}
              className={`segment-btn ${activeTab === 'pending' ? 'active' : ''}`}
              onClick={() => setActiveTab('pending')}
            >
              Active Queue ({approvals.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'history'}
              className={`segment-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              Authoritative History ({history.length})
            </button>
          </div>
        </div>

        {/* Regulatory Governance Banner */}
        <div className="clinical-info-banner">
          <Icon name="shield" size={18} className="banner-icon" />
          <div className="banner-text">
            <strong>Decision Support Protocol:</strong> Multi-agent recommendations are operational proposals, not clinical diagnoses. Proposed beds remain unreserved until an attending physician signs off.
          </div>
        </div>

        {/* Authoritative Outcome Feedback Banner */}
        {authoritativeOutcome && (
          <div
            className={`alert-banner ${authoritativeOutcome.isApproved ? 'alert-success' : 'alert-warning'}`}
            style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            role="status"
            aria-live="polite"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Icon name={authoritativeOutcome.isApproved ? 'check-circle' : 'alert-circle'} size={18} />
              <span>{authoritativeOutcome.message}</span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setAuthoritativeOutcome(null)}
              aria-label="Dismiss confirmation"
            >
              ✕
            </button>
          </div>
        )}

        {activeTab === 'pending' ? (
          loading ? (
            <div className="loading-state-card">
              <div className="spinner-border" />
              <span>Querying pending clinical decision queue...</span>
            </div>
          ) : error ? (
            <div className="alert-banner alert-error" role="alert">
              <Icon name="alert-triangle" size={16} />
              <span>{error}</span>
              <button type="button" onClick={fetchApprovals} className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }}>
                Retry
              </button>
            </div>
          ) : approvals.length === 0 ? (
            <div className="empty-state-card">
              <div className="empty-state-icon-circle">
                <Icon name="check-circle" size={26} color="var(--color-success)" />
              </div>
              <h3 className="empty-state-title">No Pending Approvals</h3>
              <p className="empty-state-description">
                All multi-agent resource recommendations have been reviewed. Safe operational status maintained.
              </p>
            </div>
          ) : (
            <div className="approvals-stack">
              {approvals.map((item) => {
                const details = extractRecommendationDetails(item);
                const hasValidBed = Boolean(
                  details.proposedBedId &&
                  String(details.proposedBedId).trim().toLowerCase() !== 'none' &&
                  String(details.proposedBedId).trim().toLowerCase() !== 'null'
                );
                const statusMeta = WORKFLOW_STATUS_CONFIG[details.workflowStatus] || WORKFLOW_STATUS_CONFIG.APPROVAL_PENDING;
                const isItemLoading = actionLoading === item.id;
                const conflictError = itemErrors[item.id];

                return (
                  <div
                    key={item.id}
                    className={`approval-card-modern ${details.escalationRequired ? 'card-escalated' : ''}`}
                    aria-busy={isItemLoading}
                  >
                    {/* Top Row: Patient & Encounter Context */}
                    <div className="approval-card-top-row">
                      <div className="approval-patient-tag">
                        <span className="patient-avatar-square">
                          {details.patientName ? details.patientName.slice(0, 2).toUpperCase() : 'PT'}
                        </span>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <h4 className="patient-title">
                              {details.patientName || details.patientId}
                            </h4>
                            <span className="badge-tag department-tag">
                              {details.departmentName} ({details.departmentId})
                            </span>
                          </div>
                          <span className="patient-sub">
                            Encounter: <strong>{details.encounterId}</strong> • Priority: <strong>ESI-{details.esiLevel} ({details.triagePriority})</strong> • Coordinator: <strong>{item.agent_id}</strong>
                          </span>
                        </div>
                      </div>

                      <div className="risk-confidence-group">
                        <span className={`status-pill ${statusMeta.pillClass}`}>
                          {statusMeta.label}
                        </span>
                        {details.confidence != null && (
                          <span className="confidence-pill">
                            Confidence: {Math.round(details.confidence * 100)}%
                          </span>
                        )}
                        <span className={`risk-badge-clean risk-${(details.riskLevel || 'MEDIUM').toLowerCase()}`}>
                          {details.riskLevel || 'MEDIUM'} RISK
                        </span>
                      </div>
                    </div>

                    {/* Escalation Warning Banner */}
                    {details.escalationRequired && (
                      <div className="escalation-alert-box" role="alert">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Icon name="alert-triangle" size={16} color="var(--color-danger)" />
                          <strong>Clinical Escalation Required ({details.urgency} / {details.emergencyLevel})</strong>
                        </div>
                        {details.escalationReasons?.length > 0 && (
                          <div style={{ fontSize: '12px', marginTop: '4px' }}>
                            Triggers: {details.escalationReasons.join('; ')}
                          </div>
                        )}
                        {details.requiredHumanActions?.length > 0 && (
                          <div style={{ fontSize: '12px', marginTop: '2px', fontWeight: 600 }}>
                            Required Clinical Action: {details.requiredHumanActions.join(', ')}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Resource Matching & Proposed Allocation Grid */}
                    <div className="approval-body-block">
                      <div className="rec-box-clean">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                          <span className="rec-box-label">PROPOSED BED & RESOURCE ALLOCATION:</span>
                          <span className="proposed-note-badge">Proposed (Unreserved)</span>
                        </div>
                        <div className="allocation-spec-row">
                          <span className="rec-box-value">
                            🛏 Bed Station: <strong>{details.proposedBedId || 'No eligible bed available'}</strong>
                          </span>
                          <span className="compatibility-tag">
                            Bed Type: <strong>{details.bedType}</strong>
                          </span>
                          {details.assignedDoctorId && (
                            <span className="staff-tag">
                              Doctor: <strong>{details.assignedDoctorId}</strong>
                            </span>
                          )}
                          {details.assignedNurseId && (
                            <span className="staff-tag">
                              Nurse: <strong>{details.assignedNurseId}</strong>
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Clinical & Flow Rationale */}
                      <div className="rationale-block">
                        <p className="clinical-rationale-text">
                          <strong>Clinical Assessment Rationale:</strong> {details.triageRationale}
                        </p>
                        {details.flowRationale && (
                          <p className="clinical-rationale-text" style={{ marginTop: '4px' }}>
                            <strong>Patient Flow & Routing:</strong> {details.flowRationale}
                          </p>
                        )}
                        {details.resourceRationale && details.resourceRationale !== details.triageRationale && (
                          <p className="clinical-rationale-text" style={{ marginTop: '4px' }}>
                            <strong>Resource Matching Justification:</strong> {details.resourceRationale}
                          </p>
                        )}
                        {details.workforceRationale && (
                          <p className="clinical-rationale-text" style={{ marginTop: '4px' }}>
                            <strong>Staffing Feasibility:</strong> {details.workforceRationale}
                          </p>
                        )}
                      </div>

                      {/* Alternative Eligible Beds */}
                      {details.candidateAlternatives?.filter(cand => (cand.target_bed_id || cand.bed_id) && String(cand.target_bed_id || cand.bed_id).toLowerCase() !== 'none' && String(cand.target_bed_id || cand.bed_id).toLowerCase() !== 'null').length > 0 && (
                        <div className="alternatives-box">
                          <span className="alternatives-title">Eligible Alternative Resources:</span>
                          <div className="alternatives-list">
                            {details.candidateAlternatives
                              .filter(cand => (cand.target_bed_id || cand.bed_id) && String(cand.target_bed_id || cand.bed_id).toLowerCase() !== 'none' && String(cand.target_bed_id || cand.bed_id).toLowerCase() !== 'null')
                              .map((cand, idx) => (
                                <span key={idx} className="alternative-chip">
                                  {cand.target_bed_id || cand.bed_id} ({cand.bed_type || 'Standard'}, Score: {cand.objective_score ?? 'N/A'})
                                </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Missing Information / Warnings */}
                      {details.warnings?.length > 0 && (
                        <div className="warnings-box">
                          <Icon name="info" size={14} />
                          <span>Warnings / Missing Inputs: {details.warnings.join('; ')}</span>
                        </div>
                      )}
                    </div>

                    {/* Conflict Error Message */}
                    {conflictError && (
                      <div className="alert-banner alert-error" style={{ margin: '12px 0 0 0' }} role="alert">
                        <Icon name="alert-triangle" size={16} />
                        <span style={{ fontSize: '13px' }}>{conflictError}</span>
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          style={{ marginLeft: 'auto' }}
                          onClick={() => beginModification(item)}
                        >
                          Select Alternative Bed
                        </button>
                      </div>
                    )}

                    {/* Action Buttons & Review Gate */}
                    {canReview ? (
                      <div className="approval-actions-clean">
                        {modifyingId === item.id ? (
                          <div className="reject-inline-block">
                            <label htmlFor={`bed-choice-${item.id}`} style={{ fontWeight: 600, fontSize: '13px' }}>
                              Select Verified Alternative Bed:
                            </label>
                            <select
                              id={`bed-choice-${item.id}`}
                              className="form-input"
                              value={selectedBedId}
                              onChange={(event) => setSelectedBedId(event.target.value)}
                              disabled={isItemLoading}
                            >
                              {availableBeds.map((bed) => (
                                <option key={bed.id} value={bed.id}>
                                  {bed.id} • {bed.bed_type} • {bed.department_id}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => handleReview(item.id, 'MODIFY', null, { target_bed_id: selectedBedId })}
                              disabled={isItemLoading || !selectedBedId}
                            >
                              {isItemLoading ? 'Executing Allocation...' : 'Confirm Modified Allocation'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => {
                                setModifyingId(null);
                                setSelectedBedId('');
                              }}
                              disabled={isItemLoading}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : rejectingId === item.id ? (
                          <div className="reject-inline-block">
                            <input
                              type="text"
                              className="form-input"
                              placeholder="Clinical rationale for declining this AI proposal (required)..."
                              value={rejectReason}
                              onChange={(e) => setRejectReason(e.target.value)}
                              disabled={isItemLoading}
                              autoFocus
                            />
                            <button
                              type="button"
                              className="btn btn-danger btn-sm"
                              onClick={() => handleReview(item.id, 'REJECT', rejectReason)}
                              disabled={isItemLoading || !rejectReason.trim()}
                            >
                              {isItemLoading ? 'Rejecting...' : 'Confirm Decline (No Bed Reserved)'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => {
                                setRejectingId(null);
                                setRejectReason('');
                              }}
                              disabled={isItemLoading}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="actions-button-row" style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'stretch' }}>
                            {!hasValidBed && (
                              <div className="alert-banner alert-warning" style={{ margin: '0 0 6px 0', fontSize: '13px', padding: '6px 12px' }} role="alert">
                                <Icon name="alert-triangle" size={14} />
                                <span>No eligible bed available. Escalation or alternative placement requires review.</span>
                              </div>
                            )}
                            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                              <button
                                type="button"
                                className="btn btn-outline btn-sm"
                                onClick={() => beginModification(item)}
                                disabled={isItemLoading}
                              >
                                Modify Allocation
                              </button>
                              <button
                                type="button"
                                className="btn btn-outline btn-sm"
                                onClick={() => setRejectingId(item.id)}
                                disabled={isItemLoading}
                              >
                                Decline / Reject
                              </button>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => handleReview(item.id, 'APPROVE')}
                                disabled={isItemLoading || !hasValidBed}
                                title={!hasValidBed ? "Cannot reserve: No eligible bed is currently available." : "Approve and reserve this bed"}
                              >
                                {isItemLoading ? 'Authorizing & Reserving...' : '✓ Approve & Reserve Bed'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="read-only-notice">
                        <Icon name="lock" size={14} />
                        <span>Attending physician credentials required to review or execute resource allocations.</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )
        ) : (
          /* Authoritative History Log Tab */
          <div className="history-tab-content">
            {history.length === 0 ? (
              <div className="empty-state-card">
                <p className="empty-state-description">No approval actions executed during current active session.</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="clinical-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Patient & Encounter</th>
                      <th>Proposed vs Final Bed</th>
                      <th>Decision</th>
                      <th>Reviewed By</th>
                      <th>Clinical Rationale / Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h, i) => {
                      const proposedBed = h.proposed_action?.target_bed_id || h.proposed_action?.bed_id || '—';
                      const finalBed = h.modification?.target_bed_id || proposedBed;
                      const action = h.review_action || h.status;
                      const isApproved = ['APPROVE', 'APPROVED', 'MODIFY', 'MODIFIED'].includes(action);

                      return (
                        <tr key={h.id || i}>
                          <td className="font-mono text-xs text-muted">
                            {h.reviewed_at ? new Date(h.reviewed_at).toLocaleString() : '—'}
                          </td>
                          <td>
                            <div style={{ fontWeight: 600 }}>{h.patient_name || h.patient_id}</div>
                            <span className="text-muted text-xs font-mono">{h.proposed_action?.encounter_id || h.decision_id}</span>
                          </td>
                          <td className="text-xs font-mono">
                            {isApproved ? (
                              <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>
                                🛏 {finalBed} (RESERVED)
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>
                                {proposedBed} (Not Allocated)
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`status-pill ${isApproved ? 'status-available' : 'status-blocked'}`}>
                              {action}
                            </span>
                          </td>
                          <td className="text-secondary">{h.reviewed_by || '—'}</td>
                          <td className="text-muted text-xs">
                            {h.rejection_reason ? (
                              <span style={{ color: 'var(--color-danger)' }}>Reason: {h.rejection_reason}</span>
                            ) : (
                              h.reasoning || 'Standard clinical review protocol'
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ApprovalsPanel;
