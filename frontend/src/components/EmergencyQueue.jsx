import { useEffect, useState, useCallback, useRef } from "react";
import { listActiveEncounters } from "../api/patients.js";
import { useEvents } from "../context/EventContext.jsx";

function EmergencyQueue() {
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { lastEvent } = useEvents();

  const fetchEncounters = useCallback(async () => {
    try {
      setError(null);
      const data = await listActiveEncounters();
      // Sort by ESI level (lower = more urgent)
      data.sort((a, b) => a.esi_level - b.esi_level);
      setEncounters(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEncounters();
    const interval = setInterval(fetchEncounters, 15000);
    return () => clearInterval(interval);
  }, [fetchEncounters]);

  // Debounced refresh to prevent duplicate in-flight API requests
  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchEncounters();
    }, 200);
  }, [fetchEncounters]);

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, []);

  // Refresh on encounter, bed, approval WebSocket events or reconnection
  useEffect(() => {
    if (lastEvent && lastEvent.event_type &&
        (lastEvent.event_type.includes('ENCOUNTER') ||
         lastEvent.event_type.includes('TRIAGE') ||
         lastEvent.event_type.includes('PATIENT') ||
         lastEvent.event_type.includes('BED') ||
         lastEvent.event_type.includes('APPROVAL') ||
         lastEvent.event_type === 'SYSTEM_CONNECTED')) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener('encounter:created', handler);
    window.addEventListener('bed:updated', handler);
    window.addEventListener('approvals:updated', handler);
    window.addEventListener('websocket:reconnected', handler);
    return () => {
      window.removeEventListener('encounter:created', handler);
      window.removeEventListener('bed:updated', handler);
      window.removeEventListener('approvals:updated', handler);
      window.removeEventListener('websocket:reconnected', handler);
    };
  }, [debouncedFetch]);

  if (loading) {
    return (
      <section className="queue-section">
        <h2>Emergency Queue</h2>
        <p className="loading">Loading encounters...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="queue-section">
        <h2>Emergency Queue</h2>
        <p className="error-message">{error}</p>
        <button onClick={fetchEncounters} className="retry-btn">Retry</button>
      </section>
    );
  }

  if (encounters.length === 0) {
    return (
      <section className="queue-section">
        <h2>Emergency Queue</h2>
        <p className="empty-state">No active patients in emergency intake queue</p>
      </section>
    );
  }

  const formatStatus = (status) => {
    return status ? status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Unknown';
  };

  const formatTime = (isoStr) => {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <section className="queue-section">
      <h2>Emergency Queue ({encounters.length} active)</h2>

      <table className="queue-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>ESI Level</th>
            <th>Complaint</th>
            <th>Status</th>
            <th>Arrival</th>
            <th>Department</th>
          </tr>
        </thead>

        <tbody>
          {encounters.map((enc) => (
            <tr key={enc.id}>
              <td>{enc.patient_id}</td>
              <td>ESI {enc.esi_level}</td>
              <td>{enc.chief_complaint}</td>
              <td>{formatStatus(enc.patient_status)}</td>
              <td>{formatTime(enc.arrival_time)}</td>
              <td>{enc.current_department_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default EmergencyQueue;