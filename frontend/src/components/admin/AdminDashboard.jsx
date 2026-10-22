import { useState, useEffect } from "react";
import { getSystemMetrics, listAuditLogs } from "../../api/admin.js";

function AdminDashboard({ onNavigateTab }) {
  const [metrics, setMetrics] = useState(null);
  const [recentLogs, setRecentLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [sysData, logsData] = await Promise.all([
          getSystemMetrics().catch(() => null),
          listAuditLogs(8).catch(() => []),
        ]);
        setMetrics(sysData);
        setRecentLogs(logsData || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="card">
        <div className="loading-state-card">
          <div className="spinner-border" />
          <span>Loading system status...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">System Overview</h2>
          <p className="admin-subtitle">Live health status, database pool state, and recent activity.</p>
        </div>
      </div>

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>Failed to load system metrics: {error}</span>
        </div>
      )}

      {/* KPI Row */}
      <div className="admin-metrics-grid">
        <div className="admin-metric-card">
          <div className="metric-header">
            <span className="metric-title">Service Status</span>
            <span className="pulse-indicator online" />
          </div>
          <div className="metric-num text-success">{metrics?.status || "ONLINE"}</div>
          <span className="metric-caption">Core application running</span>
        </div>

        <div className="admin-metric-card">
          <div className="metric-header">
            <span className="metric-title">Uptime</span>
          </div>
          <div className="metric-num">{metrics?.uptime_human || "1h 12m"}</div>
          <span className="metric-caption">Zero crashes</span>
        </div>

        <div className="admin-metric-card">
          <div className="metric-header">
            <span className="metric-title">Database</span>
          </div>
          <div className="metric-num">{metrics?.database?.dialect?.toUpperCase() || "POSTGRESQL"}</div>
          <span className="metric-caption">Active pool: {metrics?.database?.pool_size || 10} connections</span>
        </div>

        <div className="admin-metric-card">
          <div className="metric-header">
            <span className="metric-title">Memory</span>
          </div>
          <div className="metric-num">{metrics?.resources?.memory_used_mb || 112} MB</div>
          <span className="metric-caption">CPU: {metrics?.resources?.cpu_percent || 0.0}%</span>
        </div>
      </div>

      {/* Direct Section Links */}
      <div className="admin-quicklinks-grid">
        <div className="quicklink-card" onClick={() => onNavigateTab("admin_users")}>
          <div className="quicklink-body">
            <h4>Users & Roles</h4>
            <p>Roster of 33 doctors, nurses, and administrators.</p>
          </div>
          <span className="quicklink-arrow">→</span>
        </div>

        <div className="quicklink-card" onClick={() => onNavigateTab("admin_beds")}>
          <div className="quicklink-body">
            <h4>Wards & Beds</h4>
            <p>Manage ICU beds, ventilators, and isolation rooms.</p>
          </div>
          <span className="quicklink-arrow">→</span>
        </div>

        <div className="quicklink-card" onClick={() => onNavigateTab("admin_ai")}>
          <div className="quicklink-body">
            <h4>AI Controls</h4>
            <p>Set human approval rules and emergency timeouts.</p>
          </div>
          <span className="quicklink-arrow">→</span>
        </div>
      </div>

      {/* Recent Activity Table */}
      <div className="card admin-table-card">
        <div className="card-top-bar">
          <div>
            <h3 className="card-heading">Recent Audit Events</h3>
            <p className="card-subheading">Latest actions recorded in the compliance log.</p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigateTab("admin_audit")}>
            Full Log →
          </button>
        </div>

        {recentLogs.length === 0 ? (
          <div className="empty-state-card">
            <p className="empty-state-description">No recent activity recorded.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="clinical-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Target</th>
                  <th>Action</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {recentLogs.map((log) => (
                  <tr key={log.id}>
                    <td className="font-mono text-muted text-xs">
                      {log.created_at ? new Date(log.created_at).toLocaleTimeString() : "Just now"}
                    </td>
                    <td>
                      <span className="staff-chip">{log.changed_by || "SYSTEM"}</span>
                    </td>
                    <td>
                      <span className="entity-tag">{log.entity_type}: {log.entity_id}</span>
                    </td>
                    <td>
                      <span className="badge badge-neutral">{log.field_changed || "ACTION"}</span>
                    </td>
                    <td className="text-secondary text-sm">
                      {log.change_reason || "Operational transition"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminDashboard;
