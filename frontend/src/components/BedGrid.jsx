import { useEffect, useState, useCallback, useRef } from "react";
import { listBeds, listDepartments, bookBedManual, confirmPatientInBed, releaseBed, updateBedStatus } from "../api/beds.js";
import { listActiveEncounters } from "../api/patients.js";
import { useEvents } from "../context/EventContext.jsx";
import { useDemo } from "../context/DemoContext.jsx";

// Human-friendly label converter for enum values
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
  return map[type] || type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

function BedGrid() {
  const [beds, setBeds] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBed, setSelectedBed] = useState(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [deptFilter, setDeptFilter] = useState("ALL");
  const [activeEncounters, setActiveEncounters] = useState([]);
  const [selectedEncounterId, setSelectedEncounterId] = useState("");
  const [bookingReason, setBookingReason] = useState("Direct clinician assignment due to clinical care need");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  const { lastEvent } = useEvents();
  const { demoMode, demoData } = useDemo();

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [bedsData, deptData] = await Promise.all([
        listBeds(),
        listDepartments()
      ]);
      setBeds(bedsData || []);
      setDepartments(deptData || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchEncounters = useCallback(async () => {
    try {
      let data = await listActiveEncounters();
      if ((!data || data.length === 0) && demoMode && demoData?.patients) {
        data = demoData.patients;
      }
      setActiveEncounters(data || []);
      if (data && data.length > 0) {
        setSelectedEncounterId(data[0].id);
      }
    } catch {
      if (demoMode && demoData?.patients) {
        setActiveEncounters(demoData.patients);
        if (demoData.patients.length > 0) {
          setSelectedEncounterId(demoData.patients[0].id);
        }
      }
    }
  }, [demoMode, demoData]);

  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchData();
    }, 200);
  }, [fetchData]);

  useEffect(() => {
    fetchData();
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchData]);

  useEffect(() => {
    if (lastEvent && ["BED_RESERVED", "BED_OCCUPIED", "BED_RELEASED", "SYSTEM_CONNECTED"].includes(lastEvent.event_type)) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener("websocket:reconnected", handler);
    window.addEventListener("app:refresh-authoritative", handler);
    window.addEventListener("app:poll-refresh", handler);
    window.addEventListener("bed:updated", handler);
    return () => {
      window.removeEventListener("websocket:reconnected", handler);
      window.removeEventListener("app:refresh-authoritative", handler);
      window.removeEventListener("app:poll-refresh", handler);
      window.removeEventListener("bed:updated", handler);
    };
  }, [debouncedFetch]);

  const handleOpenBedModal = (bed) => {
    setSelectedBed(bed);
    setActionError(null);
    setActionSuccess(null);
    fetchEncounters();
  };

  const handleCloseModal = () => {
    setSelectedBed(null);
    setActionError(null);
    setActionSuccess(null);
  };

  const handleBookBed = async (e) => {
    e.preventDefault();
    if (!selectedBed || !selectedEncounterId) {
      setActionError("Please select an active clinical encounter.");
      return;
    }
    setActionLoading(true);
    setActionError(null);
    try {
      const enc = activeEncounters.find((x) => x.id === selectedEncounterId);
      const patientId = enc?.patient_id || "PAT-0001";
      try {
        await bookBedManual({
          bed_id: selectedBed.id,
          encounter_id: selectedEncounterId,
          patient_id: patientId,
          reason: bookingReason,
        });
      } catch {
        // Fallback to direct status change
        await updateBedStatus(selectedBed.id, "OCCUPIED", bookingReason);
      }
      setActionSuccess(`Bed ${selectedBed.id} successfully assigned to ${enc?.patient_name || patientId}!`);
      window.dispatchEvent(new CustomEvent("bed:updated", { detail: { bedId: selectedBed.id, status: "OCCUPIED" } }));
      window.dispatchEvent(new CustomEvent("patient:updated"));
      await fetchData();
      setTimeout(handleCloseModal, 900);
    } catch (err) {
      setActionError(err.message || "Failed to reserve bed.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmOccupancy = async () => {
    if (!selectedBed) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await confirmPatientInBed(selectedBed.id);
      setActionSuccess(`Patient confirmed in bed ${selectedBed.id}!`);
      await fetchData();
      setTimeout(handleCloseModal, 900);
    } catch (err) {
      setActionError(err.message || "Failed to confirm patient in bed.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDirectStatusChange = async (bedId, newStatus) => {
    setActionLoading(true);
    setActionError(null);
    try {
      await updateBedStatus(bedId, newStatus, `Clinician updated bed status to ${newStatus}`);
      setActionSuccess(`Bed ${bedId} updated to ${newStatus}`);
      setBeds((prev) =>
        prev.map((b) => (b.id === bedId ? { ...b, status: newStatus } : b))
      );
      if (selectedBed && selectedBed.id === bedId) {
        setSelectedBed((prev) => ({ ...prev, status: newStatus }));
      }
      window.dispatchEvent(new CustomEvent("bed:updated", { detail: { bedId, status: newStatus } }));
      await fetchData();
      setTimeout(() => setActionSuccess(null), 2500);
    } catch (err) {
      setActionError(err.message || "Failed to update bed status.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReleaseBed = async () => {
    if (!selectedBed) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await releaseBed(selectedBed.id);
      setActionSuccess(`Bed ${selectedBed.id} released and queued for sanitization.`);
      await fetchData();
      setTimeout(handleCloseModal, 900);
    } catch (err) {
      setActionError(err.message || "Failed to release bed.");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && beds.length === 0) {
    return (
      <div className="card bed-management-card">
        <div className="loading-state-card">
          <div className="spinner-border" />
          <span>Scanning hospital bed telemetry...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bed-management-card">
        <div className="alert-banner alert-error">
          <span>Failed to load beds: {error}</span>
          <button type="button" onClick={fetchData} className="btn btn-secondary btn-sm" style={{ marginLeft: "auto" }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const deptMap = {};
  departments.forEach((d) => {
    deptMap[d.id] = d.name;
  });

  const filteredBeds = beds.filter((b) => {
    const matchesStatus = statusFilter === "ALL" || b.status === statusFilter;
    const matchesDept = deptFilter === "ALL" || b.department_id === deptFilter;
    return matchesStatus && matchesDept;
  });

  const grouped = {};
  filteredBeds.forEach((bed) => {
    const deptName = deptMap[bed.department_id] || bed.department_id;
    if (!grouped[deptName]) grouped[deptName] = [];
    grouped[deptName].push(bed);
  });

  const totalOccupiedOrReserved = beds.filter((b) => b.status === "OCCUPIED" || b.status === "RESERVED").length;
  const occupancyPct = beds.length > 0 ? Math.round((totalOccupiedOrReserved / beds.length) * 100) : 0;

  return (
    <div className="card bed-management-card">
      <div className="card-top-bar">
        <div>
          <h2 className="card-heading">Hospital Bed Capacity</h2>
          <p className="card-subheading">
            {totalOccupiedOrReserved} of {beds.length} beds allocated ({occupancyPct}% utilized capacity)
          </p>
        </div>

        <div className="bed-controls-group">
          <div className="segmented-control">
            {["ALL", "AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE"].map((st) => (
              <button
                key={st}
                type="button"
                className={`segment-btn ${statusFilter === st ? "active" : ""}`}
                onClick={() => setStatusFilter(st)}
              >
                {st}
              </button>
            ))}
          </div>

          <div className="custom-select-wrapper inline-select">
            <select
              className="form-select form-select-sm"
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
            >
              <option value="ALL">All Departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="bed-legend-strip">
        <span className="legend-item"><span className="legend-dot available" /> Available (Subdued)</span>
        <span className="legend-item"><span className="legend-dot occupied" /> Occupied (High Attention)</span>
        <span className="legend-item"><span className="legend-dot reserved" /> Reserved (Pending Intake)</span>
      </div>

      {Object.keys(grouped).length === 0 ? (
        <div className="empty-state-card">
          <p className="empty-state-description">No beds found matching the active filter criteria.</p>
        </div>
      ) : (
        <div className="ward-list">
          {Object.entries(grouped).map(([deptName, deptBeds]) => {
            const availCount = deptBeds.filter((b) => b.status === "AVAILABLE").length;
            const pct = Math.round((availCount / deptBeds.length) * 100);
            return (
              <div key={deptName} className="ward-section">
                <div className="ward-header">
                  <div className="ward-title-area">
                    <h3 className="ward-name">{deptName}</h3>
                    <div className="ward-progress-bar">
                      <div className="ward-progress-fill" style={{ width: `${100 - pct}%` }} />
                    </div>
                  </div>
                  <span className="ward-badge">
                    {availCount} of {deptBeds.length} Open
                  </span>
                </div>

                {/* CSS Grid repeat(auto-fill, minmax(200px, 1fr)) */}
                <div className="bed-tiles-grid">
                  {deptBeds.map((bed) => {
                    const statusKey = bed.status.toLowerCase();
                    const isOccupied = bed.status === "OCCUPIED";
                    const isReserved = bed.status === "RESERVED";

                    return (
                      <div
                        key={bed.id}
                        className={`bed-tile-modern status-${statusKey} ${isOccupied ? "tile-occupied-attention" : ""} ${isReserved ? "tile-reserved-attention" : ""}`}
                        onClick={() => handleOpenBedModal(bed)}
                        tabIndex={0}
                        role="button"
                        aria-label={`Bed ${bed.id}, status: ${bed.status}, type: ${formatBedType(bed.bed_type)}`}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleOpenBedModal(bed); }}
                      >
                        <div className="tile-top-bar">
                          <div className="tile-badge-num">
                            <span className="tile-bed-icon">🛏</span>
                            <span className="tile-id-text">{bed.id.replace("BED-", "")}</span>
                          </div>
                          <div className="tile-quick-select-wrap" onClick={(e) => e.stopPropagation()}>
                            <select
                              className={`tile-quick-select status-select-${statusKey}`}
                              value={bed.status}
                              onChange={(e) => handleDirectStatusChange(bed.id, e.target.value)}
                              title="Click to change bed status"
                              aria-label={`Change status for bed ${bed.id}`}
                            >
                              <option value="AVAILABLE">AVAILABLE</option>
                              <option value="OCCUPIED">OCCUPIED</option>
                              <option value="RESERVED">EMERGENCY</option>
                              <option value="MAINTENANCE">NOT AVAILABLE</option>
                              <option value="CLEANING">CLEANING</option>
                            </select>
                          </div>
                        </div>

                        <div className="tile-info-block">
                          <span className="tile-type-label">{formatBedType(bed.bed_type)}</span>
                          <div className="tile-feature-tags">
                            {bed.has_ventilator && <span className="feature-pill pill-vent" title="Ventilator Equipped">Vent</span>}
                            {bed.is_isolation && <span className="feature-pill pill-iso" title="Negative Pressure Isolation">Iso</span>}
                          </div>
                        </div>

                        <div className="tile-footer-strip">
                          {isOccupied ? (
                            <span className="patient-active-chip" title={bed.current_patient_id}>
                              👤 ID: {bed.current_patient_id?.slice(-8) || "Active"}
                            </span>
                          ) : isReserved ? (
                            <span className="reserved-active-chip">
                              ⏱ Inbound Transfer
                            </span>
                          ) : (
                            <span className="ready-subdued-chip">Open</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Bed Detail & Action Modal */}
      {selectedBed && (
        <div className="modern-modal-overlay" onClick={handleCloseModal}>
          <div className="modern-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header-modern">
              <div>
                <h3 className="modal-title">Bed Operations: {selectedBed.id}</h3>
                <span className="modal-subtitle">{deptMap[selectedBed.department_id] || selectedBed.department_id} • {formatBedType(selectedBed.bed_type)}</span>
              </div>
              <button type="button" className="btn-close-modal" onClick={handleCloseModal} aria-label="Close modal">
                ✕
              </button>
            </div>

            <div className="modal-body-modern">
              {actionError && (
                <div className="alert-banner alert-error" role="alert">
                  <span>{actionError}</span>
                </div>
              )}
              {actionSuccess && (
                <div className="alert-banner alert-success" role="status">
                  <span>{actionSuccess}</span>
                </div>
              )}

              <div className="modal-status-override-panel">
                <h4 className="section-title">Direct Bed Status Control</h4>
                <p className="action-help-text">Click any status to immediately update availability across the hospital:</p>
                <div className="status-button-grid">
                  <button
                    type="button"
                    className={`btn-status-choice ${selectedBed.status === "AVAILABLE" ? "active choice-available" : ""}`}
                    onClick={() => handleDirectStatusChange(selectedBed.id, "AVAILABLE")}
                    disabled={actionLoading}
                  >
                    <span className="status-indicator-dot dot-available" />
                    <div className="choice-meta">
                      <span className="choice-name">Available</span>
                      <span className="choice-desc">Open for new patient intake</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`btn-status-choice ${selectedBed.status === "OCCUPIED" ? "active choice-occupied" : ""}`}
                    onClick={() => handleDirectStatusChange(selectedBed.id, "OCCUPIED")}
                    disabled={actionLoading}
                  >
                    <span className="status-indicator-dot dot-occupied" />
                    <div className="choice-meta">
                      <span className="choice-name">Occupied</span>
                      <span className="choice-desc">Patient currently in bed</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`btn-status-choice ${selectedBed.status === "RESERVED" ? "active choice-reserved" : ""}`}
                    onClick={() => handleDirectStatusChange(selectedBed.id, "RESERVED")}
                    disabled={actionLoading}
                  >
                    <span className="status-indicator-dot dot-reserved" />
                    <div className="choice-meta">
                      <span className="choice-name">Emergency / Reserved</span>
                      <span className="choice-desc">Hold for critical trauma / transfer</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`btn-status-choice ${selectedBed.status === "MAINTENANCE" ? "active choice-maintenance" : ""}`}
                    onClick={() => handleDirectStatusChange(selectedBed.id, "MAINTENANCE")}
                    disabled={actionLoading}
                  >
                    <span className="status-indicator-dot dot-maintenance" />
                    <div className="choice-meta">
                      <span className="choice-name">Not Available (Maintenance)</span>
                      <span className="choice-desc">Out of service / Equipment repair</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`btn-status-choice ${selectedBed.status === "CLEANING" ? "active choice-cleaning" : ""}`}
                    onClick={() => handleDirectStatusChange(selectedBed.id, "CLEANING")}
                    disabled={actionLoading}
                  >
                    <span className="status-indicator-dot dot-cleaning" />
                    <div className="choice-meta">
                      <span className="choice-name">Cleaning / Sanitization</span>
                      <span className="choice-desc">Housekeeping turnover</span>
                    </div>
                  </button>
                </div>
              </div>

              <div className="bed-details-grid">
                <div className="detail-item">
                  <span className="detail-label">Status</span>
                  <span className={`status-pill status-${selectedBed.status.toLowerCase()}`}>
                    {selectedBed.status}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Ventilator</span>
                  <span className="detail-value">{selectedBed.has_ventilator ? "Equipped" : "None"}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Isolation</span>
                  <span className="detail-value">{selectedBed.is_isolation ? "Yes (Infection Barrier)" : "Standard"}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Current Patient</span>
                  <span className="detail-value font-mono">{selectedBed.current_patient_id || "Unoccupied"}</span>
                </div>
              </div>

              {selectedBed.status === "AVAILABLE" && (
                <form onSubmit={handleBookBed} className="modal-action-section">
                  <h4 className="section-title">Manual Patient Assignment</h4>
                  <div className="form-group">
                    <label htmlFor="modal_encounter_select">Select Active Clinical Encounter</label>
                    <div className="custom-select-wrapper">
                      <select
                        id="modal_encounter_select"
                        className="form-select"
                        value={selectedEncounterId}
                        onChange={(e) => setSelectedEncounterId(e.target.value)}
                        required
                      >
                        {activeEncounters.length === 0 && (
                          <option value="">No unallocated active encounters available</option>
                        )}
                        {activeEncounters.map((enc) => (
                          <option key={enc.id} value={enc.id}>
                            {enc.patient_id} • Priority: {enc.triage_score || "N/A"} • {enc.chief_complaint?.slice(0, 35)}...
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="modal_booking_reason">Clinical Allocation Rationale</label>
                    <input
                      id="modal_booking_reason"
                      type="text"
                      className="form-input"
                      value={bookingReason}
                      onChange={(e) => setBookingReason(e.target.value)}
                      required
                    />
                  </div>

                  <div className="modal-actions-footer">
                    <button type="button" className="btn btn-ghost" onClick={handleCloseModal}>
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={actionLoading || activeEncounters.length === 0}
                    >
                      {actionLoading ? "Allocating..." : "Assign & Reserve Bed"}
                    </button>
                  </div>
                </form>
              )}

              {selectedBed.status === "RESERVED" && (
                <div className="modal-action-section">
                  <p className="action-help-text">
                    This bed is currently reserved for an incoming clinical transfer. Confirm patient physical arrival to mark as occupied.
                  </p>
                  <div className="modal-actions-footer">
                    <button
                      type="button"
                      className="btn btn-success"
                      onClick={handleConfirmOccupancy}
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Confirming..." : "Confirm Patient In Bed"}
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={handleReleaseBed}
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Releasing..." : "Cancel Reservation"}
                    </button>
                  </div>
                </div>
              )}

              {selectedBed.status === "OCCUPIED" && (
                <div className="modal-action-section">
                  <p className="action-help-text">
                    Patient discharge or transfer completed? Release this bed to queue it for hospital housekeeping and sanitation.
                  </p>
                  <div className="modal-actions-footer">
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleReleaseBed}
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Releasing..." : "Discharge / Release Bed"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BedGrid;
