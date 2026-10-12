import { useEffect, useState, useCallback, useRef } from "react";
import { getHospitalState } from "../api/dashboard.js";
import { useEvents } from "../context/EventContext.jsx";

function MetricCards() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { lastEvent } = useEvents();

  const fetchState = useCallback(async () => {
    try {
      setError(null);
      const data = await getHospitalState();
      setState(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchState();
    }, 200);
  }, [fetchState]);

  useEffect(() => {
    fetchState();
    // Poll every 15 seconds for near-real-time updates
    const interval = setInterval(fetchState, 15000);
    return () => {
      clearInterval(interval);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchState]);

  // Refresh on relevant WebSocket events
  useEffect(() => {
    if (lastEvent) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener('encounter:created', handler);
    window.addEventListener('emergency:updated', handler);
    window.addEventListener('approvals:updated', handler);
    window.addEventListener('bed:updated', handler);
    window.addEventListener('websocket:reconnected', handler);
    return () => {
      window.removeEventListener('encounter:created', handler);
      window.removeEventListener('emergency:updated', handler);
      window.removeEventListener('approvals:updated', handler);
      window.removeEventListener('bed:updated', handler);
      window.removeEventListener('websocket:reconnected', handler);
    };
  }, [debouncedFetch]);

  if (loading) {
    return (
      <section className="metrics">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="metric-card">
            <h3>Loading...</h3>
            <p className="loading">...</p>
          </div>
        ))}
      </section>
    );
  }

  if (error) {
    return (
      <section className="metrics">
        <div className="metric-card" style={{ gridColumn: 'span 4' }}>
          <p className="error-message">Failed to load dashboard: {error}</p>
          <button onClick={fetchState} className="retry-btn">Retry</button>
        </div>
      </section>
    );
  }

  return (
    <section className="metrics">
      <div className="metric-card">
        <h3>ICU Occupancy</h3>
        <p>{state?.icu?.utilization_pct ?? 0}%</p>
      </div>

      <div className="metric-card">
        <h3>ER Queue</h3>
        <p>{state?.er?.active_patients ?? 0} Patients</p>
      </div>

      <div className="metric-card">
        <h3>Active Alerts</h3>
        <p>{(state?.active_emergencies ?? 0) + (state?.approvals?.pending ?? 0)}</p>
      </div>

      <div className="metric-card">
        <h3>Available Beds</h3>
        <p>{state?.beds?.AVAILABLE ?? 0}</p>
      </div>
    </section>
  );
}

export default MetricCards;