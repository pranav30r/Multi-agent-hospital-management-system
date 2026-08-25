import React from 'react';

export default function MetricCards({ departments = [], activeEncounters = [], pendingApprovals = [] }) {
  const icuDept = departments.find(d => d.code === 'ICU') || { total_beds: 8, current_occupancy: 6 };
  const erDept = departments.find(d => d.code === 'ER') || { total_beds: 6, current_occupancy: 5 };

  const icuPercent = Math.round((icuDept.current_occupancy / (icuDept.total_beds || 1)) * 100);
  const erPercent = Math.round((erDept.current_occupancy / (erDept.total_beds || 1)) * 100);

  return (
    <div className="metrics-grid">
      <div className="metric-card">
        <div className="metric-header">ICU Capacity Utilization</div>
        <div className="metric-value" style={{ color: icuPercent >= 85 ? '#ef4444' : '#10b981' }}>
          {icuPercent}%
        </div>
        <div className="metric-sub">{icuDept.current_occupancy} of {icuDept.total_beds} ICU Beds Occupied</div>
      </div>

      <div className="metric-card">
        <div className="metric-header">ER Queue Load</div>
        <div className="metric-value" style={{ color: erPercent >= 80 ? '#f59e0b' : '#3b82f6' }}>
          {activeEncounters.length} Patients
        </div>
        <div className="metric-sub">{erDept.current_occupancy} active in ER • Target wait &lt; 25m</div>
      </div>

      <div className="metric-card">
        <div className="metric-header">Human Review Queue</div>
        <div className="metric-value" style={{ color: pendingApprovals.length > 0 ? '#f59e0b' : '#10b981' }}>
          {pendingApprovals.length} Pending
        </div>
        <div className="metric-sub">Requires Clinician / Staff Approval</div>
      </div>

      <div className="metric-card">
        <div className="metric-header">System Health & AI Agents</div>
        <div className="metric-value" style={{ color: '#10b981' }}>
          5 / 5 Active
        </div>
        <div className="metric-sub">Triage • Bed • Staff • Flow • Workflow</div>
      </div>
    </div>
  );
}
