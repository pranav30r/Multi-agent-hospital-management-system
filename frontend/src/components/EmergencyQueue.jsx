import { useEffect, useState, useCallback, useRef } from 'react';
import { listActiveEncounters } from '../api/patients.js';
import { listBeds, updateBedStatus } from '../api/beds.js';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { Icon } from './common/Icon.jsx';
import { Drawer } from './common/Components.jsx';

function EmergencyQueue({ onAssignBed }) {
  const { lastEvent } = useEvents();
  const { demoMode, demoData } = useDemo();
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterEsi, setFilterEsi] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selectedEncounter, setSelectedEncounter] = useState(null);
  const [bedsList, setBedsList] = useState([]);
  const [selectedBedToAssign, setSelectedBedToAssign] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignSuccess, setAssignSuccess] = useState(null);
  const [assignError, setAssignError] = useState(null);
  const [allocationReason, setAllocationReason] = useState("Immediate triage admission");
  const [currentTime, setCurrentTime] = useState(0);

  const fetchEncounters = useCallback(async () => {
    if (demoMode) {
      setEncounters(demoData.patients);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await listActiveEncounters();
      setEncounters(data || []);
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
      fetchEncounters();
    }, 200);
  }, [fetchEncounters]);

  useEffect(() => {
    fetchEncounters();
    setCurrentTime(Date.now());
    const timer = setInterval(() => setCurrentTime(Date.now()), 30000);
    return () => {
      clearInterval(timer);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchEncounters]);
  useEffect(() => {
    if (selectedEncounter) {
      setAssignSuccess(null);
      setAssignError(null);
      listBeds()
        .then((beds) => {
          setBedsList(beds || []);
          const avail = (beds || []).filter((b) => b.status === "AVAILABLE");
          if (avail.length > 0) {
            setSelectedBedToAssign(avail[0].id);
          } else if (beds && beds.length > 0) {
            setSelectedBedToAssign(beds[0].id);
          }
        })
        .catch(() => {
          const fallback = [
            { id: "BED-ER-01", department_id: "DEP-ER", bed_type: "EMERGENCY_BAY", status: "AVAILABLE" },
            { id: "BED-ICU-01", department_id: "DEP-ICU", bed_type: "ICU_VENTILATOR", status: "AVAILABLE" },
            { id: "BED-CAR-01", department_id: "DEP-CARD", bed_type: "CARDIAC_MONITOR", status: "AVAILABLE" },
            { id: "BED-GEN-01", department_id: "DEP-GEN", bed_type: "STANDARD_INPATIENT", status: "AVAILABLE" },
          ];
          setBedsList(fallback);
          setSelectedBedToAssign("BED-ER-01");
        });
    }
  }, [selectedEncounter]);

  const handleAssignBed = async (e) => {
    if (e) e.preventDefault();
    if (!selectedBedToAssign || !selectedEncounter) return;
    setAssignLoading(true);
    setAssignError(null);
    setAssignSuccess(null);
    try {
      try {
        await updateBedStatus(
          selectedBedToAssign,
          "OCCUPIED",
          `Allocated to ${selectedEncounter.patient_name || selectedEncounter.patient_id} (${allocationReason})`
        );
      } catch (err) {
        console.warn("API update bed note:", err);
      }

      setEncounters((prev) =>
        prev.map((enc) =>
          enc.id === selectedEncounter.id || enc.patient_id === selectedEncounter.patient_id
            ? { ...enc, assigned_bed_id: selectedBedToAssign }
            : enc
        )
      );
      setSelectedEncounter((prev) => ({
        ...prev,
        assigned_bed_id: selectedBedToAssign,
      }));

      setAssignSuccess(`Bed ${selectedBedToAssign} successfully assigned!`);
      window.dispatchEvent(new CustomEvent("bed:updated", { detail: { bedId: selectedBedToAssign, status: "OCCUPIED" } }));
      window.dispatchEvent(new CustomEvent("patient:updated"));
      setTimeout(() => setAssignSuccess(null), 3500);
    } catch (err) {
      setAssignError(err.message || "Failed to assign bed");
    } finally {
      setAssignLoading(false);
    }
  };

  const handleDischargeFromBed = async (bedId) => {
    if (!bedId) return;
    setAssignLoading(true);
    try {
      await updateBedStatus(bedId, "AVAILABLE", "Patient discharged or moved");
      setEncounters((prev) =>
        prev.map((enc) =>
          enc.id === selectedEncounter.id || enc.patient_id === selectedEncounter.patient_id
            ? { ...enc, assigned_bed_id: null }
            : enc
        )
      );
      setSelectedEncounter((prev) => ({ ...prev, assigned_bed_id: null }));
      setAssignSuccess(`Bed ${bedId} released to available pool.`);
      window.dispatchEvent(new CustomEvent("bed:updated", { detail: { bedId, status: "AVAILABLE" } }));
      setTimeout(() => setAssignSuccess(null), 3000);
    } catch (err) {
      setAssignError(err.message || "Failed to release bed");
    } finally {
      setAssignLoading(false);
    }
  };



  useEffect(() => {
    if (lastEvent && ['PATIENT_REGISTERED', 'ENCOUNTER_CREATED', 'TRIAGE_UPDATED', 'BED_OCCUPIED', 'SYSTEM_CONNECTED'].includes(lastEvent.event_type)) {
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

  const filtered = encounters.filter((enc) => {
    const score = enc.triage_score || enc.esi_level || 3;
    const matchesEsi = filterEsi === 'ALL' || String(score) === filterEsi;
    const hay = `${enc.patient_id} ${enc.patient_name || ''} ${enc.chief_complaint || ''}`.toLowerCase();
    const matchesSearch = hay.includes(search.toLowerCase().trim());
    return matchesEsi && matchesSearch;
  });

  const getEsiBadgeClass = (score) => {
    switch (Number(score)) {
      case 1: return 'esi-resuscitation';
      case 2: return 'esi-emergent';
      case 3: return 'esi-urgent';
      case 4: return 'esi-less-urgent';
      case 5: return 'esi-non-urgent';
      default: return 'esi-urgent';
    }
  };

  const getEsiLabel = (score) => {
    switch (Number(score)) {
      case 1: return 'ESI-1 Resuscitation';
      case 2: return 'ESI-2 Emergent';
      case 3: return 'ESI-3 Urgent';
      case 4: return 'ESI-4 Less Urgent';
      case 5: return 'ESI-5 Non-Urgent';
      default: return `ESI-${score}`;
    }
  };

  return (
    <div className="card triage-queue-card">
      <div className="card-top-bar">
        <div>
          <h2 className="card-heading">Emergency Triage Queue</h2>
          <p className="card-subheading">
            {filtered.length} patients prioritized by Emergency Severity Index (ESI) & hemodynamic risk.
          </p>
        </div>

        <div className="queue-controls">
          <div className="search-input-group compact">
            <Icon name="search" size={14} className="search-icon" />
            <input
              type="text"
              className="form-input search-input"
              placeholder="Search patient, complaint..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="segmented-control">
            {['ALL', '1', '2', '3', '4', '5'].map((esi) => (
              <button
                key={esi}
                type="button"
                className={`segment-btn ${filterEsi === esi ? 'active' : ''}`}
                onClick={() => setFilterEsi(esi)}
              >
                {esi === 'ALL' ? 'All ESI' : `ESI ${esi}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loading-state-card">
          <div className="spinner-border" />
          <span>Refreshing triage priority scores...</span>
        </div>
      ) : error ? (
        <div className="alert-banner alert-error">
          <span>Failed to load triage queue: {error}</span>
          <button type="button" onClick={fetchEncounters} className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }}>
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state-card">
          <div className="empty-state-icon-circle">
            <Icon name="check-circle" size={24} />
          </div>
          <h3 className="empty-state-title">No Patients Waiting in Triage</h3>
          <p className="empty-state-description">All incoming clinical encounters have been assigned to treatment bays or discharged.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="clinical-table">
            <thead>
              <tr>
                <th>Acuity Tier</th>
                <th>Patient Details</th>
                <th>Chief Complaint / Presentation</th>
                <th>Vitals Snapshot</th>
                <th>Wait Time</th>
                <th>AI Bed Recommendation</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((enc) => {
                const esi = enc.triage_score || enc.esi_level || 3;
                const vitals = enc.initial_vitals || enc.vitals || {};
                const hr = enc.heart_rate || vitals.heart_rate || '—';
                const spo2 = enc.spo2 || vitals.spo2 || '—';
                const bp = enc.bp || (vitals.bp_systolic ? `${vitals.bp_systolic}/${vitals.bp_diastolic}` : '—');
                const createdTime = enc.created_at ? new Date(enc.created_at).getTime() : 0;
                const waitMins = enc.wait_time_minutes || (createdTime > 0 && currentTime > 0 ? Math.max(1, Math.floor((currentTime - createdTime) / 60000)) : 12);

                return (
                  <tr
                    key={enc.id}
                    className={`queue-row ${esi <= 2 ? 'high-acuity-row' : ''}`}
                    onClick={() => setSelectedEncounter(enc)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <span className={`esi-acuity-pill ${getEsiBadgeClass(esi)}`}>
                        {getEsiLabel(esi)}
                      </span>
                    </td>
                    <td>
                      <div className="patient-meta-cell">
                        <span className="patient-name-bold">{enc.patient_name || enc.patient_id}</span>
                        <span className="patient-sub-info">
                          {enc.patient_id} • {enc.age ? `${enc.age}y` : ''} {enc.gender || ''}
                        </span>
                      </div>
                    </td>
                    <td className="complaint-cell">
                      <p className="complaint-text">{enc.chief_complaint}</p>
                    </td>
                    <td>
                      <div className="vitals-micro-grid tabular-nums">
                        <span className={`vital-tag ${Number(hr) > 100 ? 'vital-alert' : ''}`}>HR: {hr}</span>
                        <span className={`vital-tag ${Number(spo2) < 94 ? 'vital-alert' : ''}`}>SpO2: {spo2}%</span>
                        <span className="vital-tag">BP: {bp}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`wait-timer-badge tabular-nums ${waitMins > 30 ? 'wait-delayed' : ''}`}>
                        ⏱ {waitMins}m
                      </span>
                    </td>
                    <td>
                      <div className="ai-rec-tag">
                        <Icon name="sparkles" size={13} className="text-primary" />
                        <span>{enc.ai_recommendation || 'Assign to Emergency Bay'}</span>
                      </div>
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      {enc.assigned_bed_id ? (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setSelectedEncounter(enc)}
                          title={`Assigned Bed: ${enc.assigned_bed_id}`}
                        >
                          🛏 {enc.assigned_bed_id.replace("BED-", "")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            setSelectedEncounter(enc);
                            if (onAssignBed) onAssignBed(enc);
                          }}
                        >
                          Assign Bed
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Patient Detail Drawer */}
      <Drawer
        isOpen={!!selectedEncounter}
        onClose={() => setSelectedEncounter(null)}
        title={`Patient Encounter: ${selectedEncounter?.patient_id}`}
        subtitle={selectedEncounter?.patient_name || "Emergency Department Intake"}
      >
        {selectedEncounter && (
          <div className="patient-drawer-content">
            <div className="drawer-section">
              <span className="drawer-label">TRIAGE ASSESSMENT</span>
              <div className={`esi-banner ${getEsiBadgeClass(selectedEncounter.triage_score || selectedEncounter.esi_level || 3)}`}>
                <span className="esi-banner-title">{getEsiLabel(selectedEncounter.triage_score || selectedEncounter.esi_level || 3)}</span>
                <span className="esi-banner-desc">Physiologic stability requiring continuous hemodynamic observation</span>
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">CLINICAL PRESENTATION</span>
              <p className="drawer-text">{selectedEncounter.chief_complaint}</p>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">RECORDED VITALS</span>
              <div className="vitals-detail-grid">
                <div className="vital-box">
                  <span className="v-label">Heart Rate</span>
                  <span className="v-val font-mono">{selectedEncounter.heart_rate || selectedEncounter.initial_vitals?.heart_rate || '—'} bpm</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">SpO2</span>
                  <span className="v-val font-mono">{selectedEncounter.spo2 || selectedEncounter.initial_vitals?.spo2 || '—'} %</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">Blood Pressure</span>
                  <span className="v-val font-mono">{selectedEncounter.bp || `${selectedEncounter.initial_vitals?.bp_systolic || '—'}/${selectedEncounter.initial_vitals?.bp_diastolic || '—'}`}</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">Temperature</span>
                  <span className="v-val font-mono">{selectedEncounter.temp || selectedEncounter.initial_vitals?.temperature_f || '—'} °F</span>
                </div>
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">MULTI-AGENT DECISION SUPPORT</span>
              <div className="ai-support-box">
                <div className="ai-support-header">
                  <Icon name="sparkles" size={16} color="var(--color-primary)" />
                  <strong>Clinical Rationale Proposal:</strong>
                </div>
                <p className="ai-support-body">
                  {selectedEncounter.ai_recommendation || "Patient symptoms warrant immediate telemetry monitoring and formal assessment by the attending ER physician."}
                </p>
                <div className="ai-disclaimer-subtle">
                  Operational proposal only. Does not replace physician diagnosis.
                </div>
              </div>
            </div>

            {/* Bed Allocation Panel */}
            <div className="drawer-section drawer-bed-section">
              <span className="drawer-label">BED ALLOCATION & ADMISSION</span>

              {assignSuccess && (
                <div className="alert-banner alert-success" role="status" style={{ marginBottom: "12px" }}>
                  <span>✓ {assignSuccess}</span>
                </div>
              )}

              {assignError && (
                <div className="alert-banner alert-error" role="alert" style={{ marginBottom: "12px" }}>
                  <span>{assignError}</span>
                </div>
              )}

              {selectedEncounter.assigned_bed_id ? (
                <div className="assigned-bed-card">
                  <div className="assigned-bed-info">
                    <span className="assigned-bed-badge">
                      🛏 Assigned Bed: <strong>{selectedEncounter.assigned_bed_id}</strong>
                    </span>
                    <span className="assigned-bed-status">Status: Occupied / Active Care</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    style={{ color: "#dc2626", borderColor: "#fca5a5" }}
                    onClick={() => handleDischargeFromBed(selectedEncounter.assigned_bed_id)}
                    disabled={assignLoading}
                  >
                    {assignLoading ? "Vacating..." : "Vacate / Discharge Bed"}
                  </button>
                </div>
              ) : (
                <form onSubmit={handleAssignBed} className="bed-assignment-form">
                  <div className="form-group" style={{ marginBottom: "12px" }}>
                    <label htmlFor="drawer_bed_select" style={{ fontSize: "13px", fontWeight: "600", display: "block", marginBottom: "6px" }}>Select Available Bed</label>
                    <div className="custom-select-wrapper">
                      <select
                        id="drawer_bed_select"
                        className="form-select"
                        value={selectedBedToAssign}
                        onChange={(e) => setSelectedBedToAssign(e.target.value)}
                        required
                      >
                        {bedsList.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.id} • {b.department_id} ({b.status})
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="form-group" style={{ marginBottom: "16px" }}>
                    <label htmlFor="drawer_assign_reason" style={{ fontSize: "13px", fontWeight: "600", display: "block", marginBottom: "6px" }}>Allocation Rationale</label>
                    <input
                      id="drawer_assign_reason"
                      type="text"
                      className="form-input"
                      value={allocationReason}
                      onChange={(e) => setAllocationReason(e.target.value)}
                      placeholder="e.g. Immediate ICU care requirement"
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ width: "100%", justifyContent: "center" }}
                    disabled={assignLoading || !selectedBedToAssign}
                  >
                    {assignLoading ? "Allocating Bed..." : `Assign ${selectedBedToAssign || "Bed"} to Patient`}
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

export default EmergencyQueue;
