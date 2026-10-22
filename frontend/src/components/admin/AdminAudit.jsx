import { useState, useEffect } from "react";
import { listAuditLogs } from "../../api/admin.js";

function AdminAudit() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [entityFilter, setEntityFilter] = useState("ALL");

  const fetchLogs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listAuditLogs(200);
      setLogs(data || []);
    } catch (err) {
      setError(err.message || "Failed to retrieve audit trail");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleExportCSV = () => {
    if (logs.length === 0) return;
    const headers = ["ID", "Timestamp", "Tenant", "Entity Type", "Entity ID", "Field Changed", "Old Value", "New Value", "Changed By", "Reason"];
    const rows = filteredLogs.map(l => [
      l.id,
      l.created_at,
      l.tenant_id,
      l.entity_type,
      l.entity_id,
      l.field_changed,
      `"${(l.old_value || '').replace(/"/g, '""')}"`,
      `"${(l.new_value || '').replace(/"/g, '""')}"`,
      l.changed_by,
      `"${(l.change_reason || '').replace(/"/g, '""')}"`
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `medicenter_audit_trail_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const entities = ["ALL", "staff", "bed", "patient", "encounter", "approval", "auth"];

  const filteredLogs = logs.filter(l => {
    const matchesEntity = entityFilter === "ALL" || l.entity_type?.toLowerCase() === entityFilter.toLowerCase();
    const hay = `${l.entity_id} ${l.changed_by} ${l.field_changed} ${l.change_reason} ${l.entity_type}`.toLowerCase();
    const matchesSearch = hay.includes(searchTerm.toLowerCase().trim());
    return matchesEntity && matchesSearch;
  });

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">Regulatory & Clinical Audit Trail</h2>
          <p className="admin-subtitle">
            Cryptographic, append-only provenance of all clinical approvals, patient intakes, bed transfers, and authentication events.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleExportCSV}
          disabled={logs.length === 0}
        >
          📥 Export Audit Log (CSV)
        </button>
      </div>

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={fetchLogs} style={{ marginLeft: "auto" }}>
            Retry
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="admin-filter-bar">
        <div className="search-input-group">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="form-input search-input"
            placeholder="Filter audit entries by actor ID, bed number, or clinical reason..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="custom-select-wrapper inline-select">
          <select
            className="form-select"
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
          >
            {entities.map((ent) => (
              <option key={ent} value={ent}>
                {ent === "ALL" ? "All Entity Types" : ent.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="card">
          <div className="loading-state-card">
            <div className="spinner-border" />
            <span>Reading immutable audit ledger...</span>
          </div>
        </div>
      ) : (
        <div className="card admin-table-card">
          <div className="table-responsive">
            <table className="clinical-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Actor / Clinician</th>
                  <th>Target Entity</th>
                  <th>Field / Operation</th>
                  <th>Previous State</th>
                  <th>Transitioned State</th>
                  <th>Audit Context / Reason</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-6 text-muted">
                      No audit events match the current filter parameters.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => (
                    <tr key={log.id}>
                      <td className="font-mono text-xs text-muted whitespace-nowrap">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : "N/A"}
                      </td>
                      <td>
                        <span className="staff-chip font-mono font-semibold">{log.changed_by || "SYSTEM"}</span>
                      </td>
                      <td>
                        <span className="entity-tag">{log.entity_type}: {log.entity_id}</span>
                      </td>
                      <td>
                        <span className="badge badge-neutral">{log.field_changed}</span>
                      </td>
                      <td className="font-mono text-xs text-muted">{log.old_value || "—"}</td>
                      <td className="font-mono text-xs text-primary font-semibold">{log.new_value || "—"}</td>
                      <td className="text-secondary text-sm">{log.change_reason || "Operational update"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminAudit;
