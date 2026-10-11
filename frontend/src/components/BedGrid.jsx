import { useEffect, useState, useCallback } from "react";
import { listBeds, listDepartments, bookBedManual, confirmPatientInBed } from "../api/beds.js";
import { listActiveEncounters } from "../api/patients.js";
import { useEvents } from "../context/EventContext.jsx";

function BedGrid() {
  const [beds, setBeds] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBed, setSelectedBed] = useState(null);
  const [activeEncounters, setActiveEncounters] = useState([]);
  const [selectedEncounterId, setSelectedEncounterId] = useState("");
  const [manualPatientId, setManualPatientId] = useState("");
  const [manualEncounterId, setManualEncounterId] = useState("");
  const [bookingReason, setBookingReason] = useState("Direct clinician assignment due to clinical care need");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  const { lastEvent } = useEvents();

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [bedsData, deptData] = await Promise.all([
        listBeds(),
        listDepartments()
      ]);
      setBeds(bedsData);
      setDepartments(deptData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchEncounters = useCallback(async () => {
    try {
      const data = await listActiveEncounters();
      setActiveEncounters(data || []);
      if (data && data.length > 0) {
        setSelectedEncounterId(data[0].id);
      }
    } catch {
      // Non-blocking fallback
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Refresh on bed-related WebSocket events
  useEffect(() => {
    if (lastEvent && lastEvent.event_type &&
        (lastEvent.event_type.includes('BED') || lastEvent.event_type.includes('ADMISSION') || lastEvent.event_type.includes('DISCHARGE'))) {
      fetchData();
    }
  }, [lastEvent, fetchData]);

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
    setManualPatientId("");
    setManualEncounterId("");
  };

  const handleBookBed = async (e) => {
    e.preventDefault();
    if (!selectedBed) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);

    let pId = "";
    let eId = "";

    if (activeEncounters.length > 0 && selectedEncounterId) {
      const enc = activeEncounters.find(item => item.id === selectedEncounterId);
      if (enc) {
        pId = enc.patient_id;
        eId = enc.id;
      }
    }

    if (!pId || !eId) {
      pId = manualPatientId.trim();
      eId = manualEncounterId.trim();
    }

    if (!pId || !eId) {
      setActionError("Patient ID and Encounter ID are required to reserve this bed.");
      setActionLoading(false);
      return;
    }

    try {
      await bookBedManual({
        bed_id: selectedBed.id,
        patient_id: pId,
        encounter_id: eId,
        reason: bookingReason.trim() || "Clinician bed assignment"
      });
      setActionSuccess(`Bed ${selectedBed.id} successfully reserved for patient ${pId}.`);
      window.dispatchEvent(new CustomEvent('bed:updated'));
      await fetchData();
      setTimeout(() => {
        handleCloseModal();
      }, 1500);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmArrival = async () => {
    if (!selectedBed) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      await confirmPatientInBed(selectedBed.id);
      setActionSuccess(`Patient arrival confirmed. Bed ${selectedBed.id} is now OCCUPIED.`);
      window.dispatchEvent(new CustomEvent('bed:updated'));
      await fetchData();
      setTimeout(() => {
        handleCloseModal();
      }, 1500);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <section className="bed-section">
        <h2>Bed Occupancy</h2>
        <p className="loading">Loading beds...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="bed-section">
        <h2>Bed Occupancy</h2>
        <p className="error-message">{error}</p>
      </section>
    );
  }

  if (beds.length === 0) {
    return (
      <section className="bed-section">
        <h2>Bed Occupancy</h2>
        <p className="empty-state">No beds found</p>
      </section>
    );
  }

  // Group beds by department
  const deptMap = {};
  departments.forEach(d => { deptMap[d.id] = d.name; });

  const grouped = {};
  beds.forEach(bed => {
    const deptName = deptMap[bed.department_id] || bed.department_id;
    if (!grouped[deptName]) grouped[deptName] = [];
    grouped[deptName].push(bed);
  });

  const statusClass = (status) => {
    switch (status) {
      case 'AVAILABLE': return 'available';
      case 'OCCUPIED': return 'occupied';
      case 'RESERVED': return 'reserved';
      case 'CLEANING': return 'reserved';
      case 'MAINTENANCE': return 'occupied';
      case 'BLOCKED': return 'occupied';
      default: return '';
    }
  };

  return (
    <section className="bed-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <h2 style={{ margin: 0 }}>
          Bed Occupancy ({beds.filter(b => b.status === 'OCCUPIED' || b.status === 'RESERVED').length}/{beds.length} in use)
        </h2>
        <span style={{ fontSize: '12px', color: '#6b7280' }}>Click any bed to book or view status</span>
      </div>

      {Object.entries(grouped).map(([deptName, deptBeds]) => (
        <div key={deptName} style={{ marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', color: '#6b7280', marginBottom: '8px', textAlign: 'left' }}>{deptName}</h3>
          <div className="bed-grid">
            {deptBeds.map((bed) => (
              <div
                key={bed.id}
                className={`bed ${statusClass(bed.status)}`}
                onClick={() => handleOpenBedModal(bed)}
                title="Click to view details or reserve bed"
              >
                <strong>{bed.id}</strong>
                <span>{bed.status}</span>
                {bed.current_patient_id && (
                  <span style={{ fontSize: '11px', color: '#4b5563', fontWeight: 'normal' }}>
                    {bed.current_patient_id}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Bed Detail & Booking Modal */}
      {selectedBed && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-card" onClick={e => e.stopPropagation()} style={{ width: '480px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ margin: 0 }}>Bed Details: {selectedBed.id}</h2>
              <button
                onClick={handleCloseModal}
                style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#6b7280' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', padding: '12px', background: '#f9fafb', borderRadius: '4px' }}>
                <div><strong>Department:</strong> {deptMap[selectedBed.department_id] || selectedBed.department_id}</div>
                <div><strong>Type:</strong> {selectedBed.bed_type}</div>
                <div>
                  <strong>Status:</strong>{' '}
                  <span style={{ fontWeight: 'bold', color: selectedBed.status === 'AVAILABLE' ? '#16a34a' : selectedBed.status === 'RESERVED' ? '#ca8a04' : '#dc2626' }}>
                    {selectedBed.status}
                  </span>
                </div>
                <div>
                  <strong>Capabilities:</strong>{' '}
                  {[
                    selectedBed.has_ventilator ? 'Ventilator' : '',
                    selectedBed.has_telemetry ? 'Telemetry' : '',
                    selectedBed.is_isolation ? 'Isolation' : ''
                  ].filter(Boolean).join(', ') || 'Standard'}
                </div>
              </div>

              {actionError && <p className="error-message">{actionError}</p>}
              {actionSuccess && <p style={{ color: '#15803d', background: '#dcfce7', padding: '8px', borderRadius: '4px', fontSize: '13px' }}>{actionSuccess}</p>}

              {/* State 1: Bed is AVAILABLE -> Booking form */}
              {selectedBed.status === 'AVAILABLE' && (
                <form onSubmit={handleBookBed} style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '8px' }}>
                  <h4 style={{ margin: '4px 0', color: '#1e3a5f' }}>Reserve / Book This Bed</h4>

                  {activeEncounters.length > 0 ? (
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#374151', marginBottom: '4px' }}>
                        Select Active Encounter / Patient:
                      </label>
                      <select
                        value={selectedEncounterId}
                        onChange={e => setSelectedEncounterId(e.target.value)}
                        style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}
                      >
                        {activeEncounters.map(enc => (
                          <option key={enc.id} value={enc.id}>
                            {enc.patient_id} — {enc.id} (ESI {enc.esi_level}: {enc.chief_complaint})
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '12px', color: '#374151', marginBottom: '4px' }}>Patient ID:</label>
                        <input
                          type="text"
                          placeholder="e.g. PAT-001"
                          value={manualPatientId}
                          onChange={e => setManualPatientId(e.target.value)}
                          style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}
                          required
                        />
                      </div>
                      <div>
                        <label style={{ display: 'block', fontSize: '12px', color: '#374151', marginBottom: '4px' }}>Encounter ID:</label>
                        <input
                          type="text"
                          placeholder="e.g. ENC-001"
                          value={manualEncounterId}
                          onChange={e => setManualEncounterId(e.target.value)}
                          style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}
                          required
                        />
                      </div>
                    </div>
                  )}

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', color: '#374151', marginBottom: '4px' }}>Reason / Clinical Indication:</label>
                    <input
                      type="text"
                      value={bookingReason}
                      onChange={e => setBookingReason(e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}
                      required
                    />
                  </div>

                  <div className="modal-actions" style={{ marginTop: '12px' }}>
                    <button
                      type="button"
                      onClick={handleCloseModal}
                      style={{ padding: '8px 16px', background: '#e5e7eb', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '8px' }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="action-btn"
                      disabled={actionLoading}
                    >
                      {actionLoading ? "Reserving..." : "Confirm & Reserve Bed"}
                    </button>
                  </div>
                </form>
              )}

              {/* State 2: Bed is RESERVED -> Arrival confirmation */}
              {selectedBed.status === 'RESERVED' && (
                <div style={{ marginTop: '8px' }}>
                  <p style={{ fontSize: '13px', color: '#4b5563' }}>
                    This bed is currently reserved for <strong>Patient: {selectedBed.current_patient_id || 'Assigned'}</strong> (Encounter: {selectedBed.current_encounter_id || 'Pending'}).
                  </p>
                  <div className="modal-actions" style={{ marginTop: '16px' }}>
                    <button
                      type="button"
                      onClick={handleCloseModal}
                      style={{ padding: '8px 16px', background: '#e5e7eb', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '8px' }}
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={handleConfirmArrival}
                      className="action-btn"
                      disabled={actionLoading}
                      style={{ background: '#16a34a' }}
                    >
                      {actionLoading ? "Confirming..." : "Confirm Patient Arrival (Occupied)"}
                    </button>
                  </div>
                </div>
              )}

              {/* State 3: Bed is OCCUPIED */}
              {selectedBed.status === 'OCCUPIED' && (
                <div style={{ marginTop: '8px' }}>
                  <p style={{ fontSize: '13px', color: '#4b5563' }}>
                    Patient <strong>{selectedBed.current_patient_id}</strong> is currently admitted in this bed under encounter <strong>{selectedBed.current_encounter_id}</strong>.
                  </p>
                  <div className="modal-actions" style={{ marginTop: '16px' }}>
                    <button
                      type="button"
                      onClick={handleCloseModal}
                      className="action-btn"
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default BedGrid;