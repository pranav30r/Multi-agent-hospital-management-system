import React from 'react';

export default function ApprovalQueue({ pendingItems = [], onReview }) {
  if (pendingItems.length === 0) {
    return (
      <div className="panel-card">
        <div className="panel-title">
          <span>✅ Human Review Queue (0)</span>
        </div>
        <div style={{ padding: '1rem', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>
          All AI recommendations auto-approved or reviewed. No pending approvals.
        </div>
      </div>
    );
  }

  return (
    <div className="panel-card" style={{ borderColor: '#f59e0b' }}>
      <div className="panel-title" style={{ color: '#fbbf24' }}>
        <span>⚠️ Human Review Required ({pendingItems.length})</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {pendingItems.map(item => (
          <div 
            key={item.id} 
            style={{ 
              backgroundColor: '#0f172a', 
              border: '1px solid #334155', 
              borderRadius: '8px', 
              padding: '0.9rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="badge" style={{ backgroundColor: item.risk_level === 'HIGH' ? '#dc2626' : '#d97706', color: 'white' }}>
                {item.risk_level} RISK
              </span>
              <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Agent: {item.agent_id}</span>
            </div>

            <div style={{ fontSize: '0.85rem', fontWeight: '600', color: '#f8fafc' }}>
              {item.action_type}: {JSON.stringify(item.proposed_action)}
            </div>

            <div style={{ fontSize: '0.75rem', color: '#cbd5e1', fontStyle: 'italic' }}>
              "{item.reasoning}"
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              <button 
                className="btn btn-primary" 
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem', backgroundColor: '#10b981' }}
                onClick={() => onReview(item.id, { action: 'APPROVE', reviewed_by: 'DOC-001' })}
              >
                ✓ Approve
              </button>

              <button 
                className="btn btn-secondary" 
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                onClick={() => onReview(item.id, { action: 'MODIFY', reviewed_by: 'DOC-001', modification: { note: 'Human adjusted bed candidate' } })}
              >
                ✏️ Modify
              </button>

              <button 
                className="btn btn-danger" 
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                onClick={() => onReview(item.id, { action: 'REJECT', reviewed_by: 'DOC-001', rejection_reason: 'Clinician override' })}
              >
                ✕ Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
