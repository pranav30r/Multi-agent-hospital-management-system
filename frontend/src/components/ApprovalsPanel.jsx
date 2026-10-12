import { useEffect, useState, useCallback, useRef } from 'react';
import { listPendingApprovals, reviewApproval } from '../api/approvals.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useEvents } from '../context/EventContext.jsx';

function ApprovalsPanel() {
  const { user } = useAuth();
  const { lastEvent } = useEvents();
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectingId, setRejectingId] = useState(null);

  // Only show for ADMINISTRATOR and DOCTOR roles
  const canReview = user && ['ADMINISTRATOR', 'DOCTOR'].includes(user.role);

  const fetchApprovals = useCallback(async () => {
    try {
      setError(null);
      const data = await listPendingApprovals();
      setApprovals(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced refresh to prevent duplicate in-flight API requests
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

  // Refresh on relevant WebSocket events
  useEffect(() => {
    if (lastEvent && ['APPROVAL_REQUIRED', 'APPROVAL_REVIEWED', 'APPROVAL_DECIDED', 'BED_RESERVED', 'SYSTEM_CONNECTED'].includes(lastEvent.event_type)) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener('bed:updated', handler);
    window.addEventListener('websocket:reconnected', handler);
    return () => {
      window.removeEventListener('bed:updated', handler);
      window.removeEventListener('websocket:reconnected', handler);
    };
  }, [debouncedFetch]);

  const handleReview = async (approvalId, action, reason) => {
    setActionLoading(approvalId);
    try {
      const body = { action };
      if (action === 'REJECT' && reason) body.rejection_reason = reason;
      await reviewApproval(approvalId, body);
      window.dispatchEvent(new CustomEvent('approvals:updated'));
      setRejectingId(null);
      setRejectReason('');
      await fetchApprovals();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) return <section className="approval-section"><p className="loading">Loading approvals...</p></section>;
  if (error) {
    return (
      <section className="approval-section">
        <h2>Human Review Queue</h2>
        <p className="error-message">{error}</p>
        <button onClick={fetchApprovals} className="retry-btn">Retry</button>
      </section>
    );
  }
  if (approvals.length === 0) {
    return (
      <section className="approval-section">
        <h2>Human Review Queue</h2>
        <p className="empty-state">No pending approvals requiring clinician review</p>
      </section>
    );
  }

  return (
    <section className="approval-section">
      <h2>Human Review Queue ({approvals.length})</h2>
      <table className="queue-table">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Action</th>
            <th>Risk</th>
            <th>Reasoning</th>
            {canReview && <th>Decision</th>}
          </tr>
        </thead>
        <tbody>
          {approvals.map(item => (
            <tr key={item.id}>
              <td>{item.agent_id}</td>
              <td>{item.action_type}</td>
              <td><span className={`risk-badge risk-${item.risk_level.toLowerCase()}`}>{item.risk_level}</span></td>
              <td className="reasoning-cell">{item.reasoning}</td>
              {canReview && (
                <td className="action-buttons">
                  {rejectingId === item.id ? (
                    <div className="reject-form">
                      <input
                        type="text"
                        placeholder="Rejection reason"
                        value={rejectReason}
                        onChange={e => setRejectReason(e.target.value)}
                      />
                      <button onClick={() => handleReview(item.id, 'REJECT', rejectReason)} disabled={actionLoading === item.id}>
                        Confirm
                      </button>
                      <button onClick={() => { setRejectingId(null); setRejectReason(''); }} className="clear-button">
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => handleReview(item.id, 'APPROVE')}
                        disabled={actionLoading === item.id}
                        className="approve-btn"
                      >
                        {actionLoading === item.id ? '...' : 'Approve'}
                      </button>
                      <button
                        onClick={() => setRejectingId(item.id)}
                        disabled={actionLoading === item.id}
                        className="reject-btn"
                      >
                        Reject
                      </button>
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default ApprovalsPanel;
