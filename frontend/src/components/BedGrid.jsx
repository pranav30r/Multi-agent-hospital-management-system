import { useEffect, useState, useCallback } from "react";
import { listBeds, listDepartments } from "../api/beds.js";
import { useEvents } from "../context/EventContext.jsx";

function BedGrid() {
  const [beds, setBeds] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
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

  // Map backend status to CSS class
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
      <h2>Bed Occupancy ({beds.filter(b => b.status === 'OCCUPIED' || b.status === 'RESERVED').length}/{beds.length} in use)</h2>

      {Object.entries(grouped).map(([deptName, deptBeds]) => (
        <div key={deptName} style={{ marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', color: '#6b7280', marginBottom: '8px', textAlign: 'left' }}>{deptName}</h3>
          <div className="bed-grid">
            {deptBeds.map((bed) => (
              <div
                key={bed.id}
                className={`bed ${statusClass(bed.status)}`}
                title={[
                  bed.bed_type,
                  bed.is_isolation ? 'Isolation' : '',
                  bed.has_ventilator ? 'Ventilator' : '',
                  bed.has_telemetry ? 'Telemetry' : '',
                  bed.current_patient_id ? `Patient: ${bed.current_patient_id}` : ''
                ].filter(Boolean).join(' | ')}
              >
                <strong>{bed.id}</strong>
                <span>{bed.status}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export default BedGrid;