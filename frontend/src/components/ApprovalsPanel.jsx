import { useEffect, useState, useCallback, useRef } from 'react';
import { listPendingApprovals, reviewApproval } from '../api/approvals.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { Icon } from './common/Icon.jsx';

function ApprovalsPanel() {
  const { user } = useAuth();
  const { lastEvent } = useEvents();
  const { demoMode, demoData } = useDemo();

  const [approvals, setApprovals] = useState([]);
  const [history, setHistory] = useState([]);
  const [activeTab, setActiveTab] = useState('pending'); // 'pending' | 'history'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectingId, setRejectingId] = useState(null);

  const canReview = user && ['ADMINISTRATOR', 'DOCTOR'].includes(user.role);

  const fetchApprovals = useCallback(async () => {
    if (demoMode) {
      setApprovals(demoData.approvals);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await listPendingApprovals();
      setApprovals(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [demoMode, demoData]);

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
    if (lastEvent && ['APPROVAL_REQUIRED', 'APPROVAL_REVIEWED', 'APPROVAL_DECIDED', 'BED_RESERVED', 'SYSTEM_CONNECTED'].includes(lastEvent.event_type)) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener("websocket:reconnected", handler);
    window.addEventListener("app:refresh-authoritative", handler);
    window.addEventListener("app:poll-refresh", handler);
    return () => {
      window.removeEventListener("websocket:reconnected", handler);
      window.removeEventListener("app:refresh-authoritative", handler);
      window.removeEventListener("app:poll-refresh", handler);
    };
  }, [debouncedFetch]);

  const handleReview = async (approvalId, action, reason) => {
    setActionLoading(approvalId);
    try {
      if (!demoMode) {
        const body = { action };
        if (action === 'REJECT' && reason) body.rejection_reason = reason;
        await reviewApproval(approvalId, body);
      }

      // Add to local history list
      const target = approvals.find((a) => a.id === approvalId);
      if (target) {
        setHistory((prev) => [
          {
            ...target,
            decision: action,
            decision_by: user ? `${user.first_name} ${user.last_name}` : 'Attending Physician',
            decision_time: new Date().toISOString(),
            rejection_reason: reason,
          },
          ...prev,
        ]);
      }

      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      window.dispatchEvent(new CustomEvent("bed:updated"));
      window.dispatchEvent(new CustomEvent("patient:updated"));
      setRejectingId(null);
      setRejectReason('');
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const formatProposedAction = (action) => {
    if (!action) return "Resource Allocation";
    if (typeof action === 'object') {
      const parts = [];
      if (action.bed_id || action.target_bed_id) parts.push(`Bed Station: ${action.bed_id || action.target_bed_id}`);
      if (action.target_department) parts.push(`Department: ${action.target_department}`);
      if (action.allocation) parts.push(`Equipment: ${action.allocation}`);
      if (action.encounter_id) parts.push(`Encounter: ${action.encounter_id}`);
      return parts.length > 0 ? parts.join(" • ") : JSON.stringify(action);
    }
    return String(action);
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
                {approvals.length} Pending Actions
              </span>
            </div>
            <p className="card-subheading">
              Physician oversight gate: autonomous high-risk bed transfers and resource preemption require human sign-off.
            </p>
          </div>

          <div className="segmented-control">
            <button
              type="button"
              className={`segment-btn ${activeTab === 'pending' ? 'active' : ''}`}
              onClick={() => setActiveTab('pending')}
            >
              Active Queue ({approvals.length})
            </button>
            <button
              type="button"
              className={`segment-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              History Log ({history.length})
            </button>
          </div>
        </div>

        {/* Regulatory Info Banner */}
        <div className="clinical-info-banner">
          <Icon name="shield" size={18} className="banner-icon" />
          <div className="banner-text">
            <strong>Decision Support Protocol:</strong> Autonomous multi-agent recommendations are operational proposals, not clinical diagnoses. Clinicians must verify current bedside patient status prior to approval.
          </div>
        </div>

        {activeTab === 'pending' ? (
          loading ? (
            <div className="loading-state-card">
              <div className="spinner-border" />
              <span>Querying pending clinical decision queue...</span>
            </div>
          ) : error ? (
            <div className="alert-banner alert-error">
              <Icon name="alert-triangle" size={16} />
              <span>{error}</span>
              <button type="button" onClick={fetchApprovals} className="btn btn-secondary btn-sm" style={{ marginLeft: "auto" }}>
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
              {approvals.map((item) => (
                <div key={item.id} className="approval-card-modern">
                  <div className="approval-card-top-row">
                    <div className="approval-patient-tag">
                      <span className="patient-avatar-square">PT</span>
                      <div>
                        <h4 className="patient-title">{item.patient_name || item.proposed_action?.patient_id || "Emergency Patient"}</h4>
                        <span className="patient-sub">{item.patient_id || item.proposed_action?.patient_id || "ID-4029"} • Agent: <strong>{item.agent_id}</strong></span>
                      </div>
                    </div>

                    <div className="risk-confidence-group">
                      <span className="confidence-pill">
                        Confidence: {Math.round((item.confidence || 0.92) * 100)}%
                      </span>
                      <span className={`risk-badge-clean risk-${(item.risk_level || 'MEDIUM').toLowerCase()}`}>
                        {item.risk_level || 'MEDIUM'} RISK
                      </span>
                    </div>
                  </div>

                  <div className="approval-body-block">
                    <div className="rec-box-clean">
                      <span className="rec-box-label">RECOMMENDED ACTION:</span>
                      <span className="rec-box-value">{formatProposedAction(item.proposed_action)}</span>
                    </div>

                    <p className="clinical-rationale-text">
                      <strong>Clinical Rationale:</strong> {item.reasoning}
                    </p>
                  </div>

                  {canReview ? (
                    <div className="approval-actions-clean">
                      {rejectingId === item.id ? (
                        <div className="reject-inline-block">
                          <input
                            type="text"
                            className="form-input"
                            placeholder="Enter required clinical reason for rejecting this AI allocation..."
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            autoFocus
                          />
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => handleReview(item.id, 'REJECT', rejectReason)}
                            disabled={actionLoading === item.id || !rejectReason.trim()}
                          >
                            {actionLoading === item.id ? "Rejecting..." : "Confirm Rejection"}
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => { setRejectingId(null); setRejectReason(''); }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="actions-button-row">
                          <button
                            type="button"
                            className="btn btn-outline btn-sm"
                            onClick={() => setRejectingId(item.id)}
                            disabled={actionLoading === item.id}
                          >
                            Request Review / Reject
                          </button>
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => handleReview(item.id, 'APPROVE')}
                            disabled={actionLoading === item.id}
                          >
                            {actionLoading === item.id ? "Authorizing..." : "Approve Allocation"}
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="read-only-notice">
                      Attending physician or supervisory clinical credentials required to execute actions.
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        ) : (
          /* History Tab */
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
                      <th>Patient</th>
                      <th>Proposed Resource</th>
                      <th>Decision</th>
                      <th>Reviewed By</th>
                      <th>Rejection Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h, i) => (
                      <tr key={i}>
                        <td className="font-mono text-xs text-muted">{new Date(h.decision_time).toLocaleTimeString()}</td>
                        <td className="font-semibold">{h.patient_name || h.patient_id}</td>
                        <td className="text-xs font-mono">{formatProposedAction(h.proposed_action)}</td>
                        <td>
                          <span className={`status-pill ${h.decision === 'APPROVE' ? 'status-available' : 'status-occupied'}`}>
                            {h.decision}
                          </span>
                        </td>
                        <td className="text-secondary">{h.decision_by}</td>
                        <td className="text-muted text-xs">{h.rejection_reason || '—'}</td>
                      </tr>
                    ))}
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
