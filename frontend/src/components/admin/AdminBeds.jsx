import { useState, useEffect } from "react";
import { listBeds, listDepartments, updateBedStatus } from "../../api/beds.js";

const formatBedType = (type) => {
  if (!type) return "Standard Medical";
  const map = {
    CARDIAC_MONITOR: "Cardiac Monitor",
    ICU_VENTILATOR: "ICU Ventilator",
    ISOLATION_NEGATIVE_PRESSURE: "Negative Pressure Isolation",
    ISOLATION_ROOM: "Isolation Room",
    STANDARD_INPATIENT: "Standard Inpatient",
    ICU_GENERAL: "ICU General",
    STEP_DOWN: "Step-Down Unit",
    EMERGENCY_BAY: "Emergency Bay",
    TRAUMA_BAY: "Trauma Bay",
    PEDIATRIC_COT: "Pediatric Cot",
    PEDIATRIC: "Pediatric Bed",
  };
  return map[type] || type.replace(/_/g, " ");
};
import { getCustomBeds, saveCustomBeds } from "../../api/admin.js";

function AdminBeds() {
  const [beds, setBeds] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Add bed modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [newBed, setNewBed] = useState({
    id: "",
    department_id: "DEP-ICU",
    bed_type: "ICU_VENTILATOR",
    has_ventilator: true,
    is_isolation: false,
    status: "AVAILABLE",
  });

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [bedsData, deptData] = await Promise.all([
        listBeds(),
        listDepartments(),
      ]);
      const customBeds = getCustomBeds();
      setBeds([...(bedsData || []), ...customBeds]);
      setDepartments(deptData || []);
    } catch (err) {
      setError(err.message || "Failed to load beds and departments");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleToggleBedStatus = async (bed) => {
    const nextStatus = bed.status === "AVAILABLE" ? "MAINTENANCE" : "AVAILABLE";
    try {
      const customBeds = getCustomBeds();
      const isCustom = customBeds.some((b) => b.id === bed.id);
      if (isCustom) {
        const updatedCustom = customBeds.map((b) => (b.id === bed.id ? { ...b, status: nextStatus } : b));
        saveCustomBeds(updatedCustom);
      } else {
        await updateBedStatus(bed.id, nextStatus, `Admin toggled status to ${nextStatus}`);
      }
      setBeds((prev) => prev.map((b) => (b.id === bed.id ? { ...b, status: nextStatus } : b)));
      setSuccessMsg(`Bed ${bed.id} marked as ${nextStatus}.`);
      window.dispatchEvent(new CustomEvent("bed:updated"));
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      setError(err.message || "Failed to update bed status");
    }
  };

  const handleAddBed = (e) => {
    e.preventDefault();
    if (!newBed.id.trim()) return;

    const formattedId = newBed.id.startsWith("BED-") ? newBed.id : `BED-${newBed.id.trim().toUpperCase()}`;
    const bedItem = {
      id: formattedId,
      department_id: newBed.department_id,
      bed_type: newBed.bed_type,
      has_ventilator: newBed.has_ventilator,
      is_isolation: newBed.is_isolation,
      status: "AVAILABLE",
      current_patient_id: null,
    };

    const existingCustom = getCustomBeds();
    const updated = [bedItem, ...existingCustom];
    saveCustomBeds(updated);

    setSuccessMsg(`Bed ${formattedId} configured and registered in capacity index.`);
    setModalOpen(false);
    setNewBed({
      id: "",
      department_id: "DEP-ICU",
      bed_type: "ICU_VENTILATOR",
      has_ventilator: true,
      is_isolation: false,
      status: "AVAILABLE",
    });
    fetchData();
    window.dispatchEvent(new CustomEvent("bed:updated"));
    setTimeout(() => setSuccessMsg(null), 3500);
  };

  const deptMap = {};
  departments.forEach((d) => {
    deptMap[d.id] = d.name;
  });

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">Departments & Bed Capacity Configuration</h2>
          <p className="admin-subtitle">
            Configure clinical units, ventilator-equipped stations, and negative pressure isolation allocations.
          </p>
        </div>

        <button type="button" className="btn btn-primary" onClick={() => setModalOpen(true)}>
          + Add New Bed Station
        </button>
      </div>

      {successMsg && (
        <div className="alert-banner alert-success" role="status">
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={fetchData} style={{ marginLeft: "auto" }}>
            Retry
          </button>
        </div>
      )}

      {/* Department Summary Cards */}
      <div className="admin-metrics-grid">
        {departments.map((dept) => {
          const deptBeds = beds.filter((b) => b.department_id === dept.id);
          const occupied = deptBeds.filter((b) => b.status === "OCCUPIED" || b.status === "RESERVED").length;
          return (
            <div key={dept.id} className="admin-metric-card">
              <div className="metric-header">
                <span className="metric-title">{dept.name}</span>
                <span className="font-mono text-xs text-muted">{dept.id}</span>
              </div>
              <div className="metric-num">
                {deptBeds.length - occupied} / {deptBeds.length}
              </div>
              <span className="metric-caption">Beds Available ({Math.round((occupied / (deptBeds.length || 1)) * 100)}% utilized)</span>
              <div className="workload-progress" style={{ marginTop: "10px" }}>
                <div
                  className="workload-fill"
                  style={{
                    width: `${Math.min(100, Math.round((occupied / (deptBeds.length || 1)) * 100))}%`,
                    backgroundColor: Math.round((occupied / (deptBeds.length || 1)) * 100) > 85 ? "var(--color-danger)" : "var(--color-primary)",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Bed inventory Table */}
      <div className="card admin-table-card">
        <div className="card-top-bar">
          <div>
            <h3 className="card-heading">Configured Bed Stations ({beds.length} Total)</h3>
            <p className="card-subheading">Comprehensive telemetry breakdown across all wards.</p>
          </div>
        </div>

        {loading ? (
          <div className="loading-state-card">
            <div className="spinner-border" />
            <span>Retrieving bed station topology...</span>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="clinical-table">
              <thead>
                <tr>
                  <th>Bed ID</th>
                  <th>Department / Ward</th>
                  <th>Clinical Station Type</th>
                  <th>Ventilator</th>
                  <th>Isolation Unit</th>
                  <th>Current State</th>
                  <th>Active Encounter</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {beds.map((bed) => (
                  <tr key={bed.id}>
                    <td className="font-mono font-semibold">{bed.id}</td>
                    <td>{deptMap[bed.department_id] || bed.department_id}</td>
                    <td>
                      <span className="attribute-pill">{formatBedType(bed.bed_type)}</span>
                    </td>
                    <td>
                      {bed.has_ventilator ? (
                        <span className="feature-pill pill-vent">Equipped</span>
                      ) : (
                        <span className="text-muted text-xs">Standard</span>
                      )}
                    </td>
                    <td>
                      {bed.is_isolation ? (
                        <span className="feature-pill pill-iso">Negative Pressure</span>
                      ) : (
                        <span className="text-muted text-xs">No</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-pill status-${bed.status.toLowerCase()}`}>
                        {bed.status}
                      </span>
                    </td>
                    <td className="font-mono text-xs text-muted">
                      {bed.current_patient_id || "Unoccupied"}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => handleToggleBedStatus(bed)}
                        title="Toggle between Available and Maintenance"
                      >
                        {bed.status === "AVAILABLE" ? "Set Offline" : "Set Available"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Bed Modal */}
      {modalOpen && (
        <div className="modern-modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modern-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header-modern">
              <div>
                <h3 className="modal-title">Provision New Bed Station</h3>
                <span className="modal-subtitle">Enroll station in multi-agent auto-allocation pool</span>
              </div>
              <button type="button" className="btn-close-modal" onClick={() => setModalOpen(false)}>✕</button>
            </div>

            <form className="modal-body-modern" onSubmit={handleAddBed}>
              <div className="form-grid-2col">
                <div className="form-group">
                  <label htmlFor="bed_new_id">Bed Station Identifier *</label>
                  <input
                    id="bed_new_id"
                    type="text"
                    className="form-input"
                    placeholder="e.g. ICU-009 or ER-015"
                    value={newBed.id}
                    onChange={(e) => setNewBed({ ...newBed, id: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="bed_new_dept">Target Department *</label>
                  <div className="custom-select-wrapper">
                    <select
                      id="bed_new_dept"
                      className="form-select"
                      value={newBed.department_id}
                      onChange={(e) => setNewBed({ ...newBed, department_id: e.target.value })}
                    >
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} ({d.id})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="bed_new_type">Clinical Station Specification</label>
                  <div className="custom-select-wrapper">
                    <select
                      id="bed_new_type"
                      className="form-select"
                      value={newBed.bed_type}
                      onChange={(e) => setNewBed({ ...newBed, bed_type: e.target.value })}
                    >
                      <option value="CARDIAC_MONITOR">Cardiac Monitor Unit</option>
                      <option value="ICU_VENTILATOR">ICU Ventilator Station</option>
                      <option value="ISOLATION_NEGATIVE_PRESSURE">Negative Pressure Isolation</option>
                      <option value="STANDARD_INPATIENT">Standard Inpatient Station</option>
                      <option value="TRAUMA_BAY">Trauma Resuscitation Bay</option>
                    </select>
                  </div>
                </div>

                <div className="form-group" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={newBed.has_ventilator}
                      onChange={(e) => setNewBed({ ...newBed, has_ventilator: e.target.checked })}
                    />
                    <span>Equipped with Invasive Ventilator</span>
                  </label>
                  <label className="checkbox-label" style={{ marginTop: "8px" }}>
                    <input
                      type="checkbox"
                      checked={newBed.is_isolation}
                      onChange={(e) => setNewBed({ ...newBed, is_isolation: e.target.checked })}
                    />
                    <span>Equipped with Isolation Barrier</span>
                  </label>
                </div>
              </div>

              <div className="modal-actions-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Enroll Bed Station
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminBeds;
