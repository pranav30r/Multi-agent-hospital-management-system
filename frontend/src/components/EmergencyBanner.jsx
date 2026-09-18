import { useEffect, useState, useCallback } from 'react';
import { listActiveEmergencies, resolveEmergency } from '../api/emergencies.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useEvents } from '../context/EventContext.jsx';

function EmergencyBanner() {
  const { user } = useAuth();
  const { lastEvent } = useEvents();
  const [emergencies, setEmergencies] = useState([]);
  const [resolving, setResolving] = useState(null);

  const canResolve = user && ['ADMINISTRATOR', 'DOCTOR', 'CHARGE_NURSE'].includes(user.role);

  const fetchEmergencies = useCallback(async () => {
    try {
      const data = await listActiveEmergencies();
      setEmergencies(data);
    } catch {
      // Non-blocking background fetch error handling
    }
  }, []);

  useEffect(() => { fetchEmergencies(); }, [fetchEmergencies]);

  // Refresh on emergency events
  useEffect(() => {
    if (lastEvent && ['EMERGENCY_DECLARED', 'EMERGENCY_RESOLVED'].includes(lastEvent.event_type)) {
      fetchEmergencies();
    }
  }, [lastEvent, fetchEmergencies]);

  const handleResolve = async (id) => {
    setResolving(id);
    try {
      await resolveEmergency(id);
      await fetchEmergencies();
    } catch {
      // User notification or error handling
    } finally {
      setResolving(null);
    }
  };

  if (emergencies.length === 0) return null;

  return (
    <div className="emergency-banner">
      {emergencies.map(em => (
        <div key={em.id} className="emergency-item">
          <span className="emergency-icon">⚠</span>
          <span className="emergency-info">
            <strong>{em.event_type.replace(/_/g, ' ')}</strong> — {em.severity} — {em.description}
          </span>
          {canResolve && (
            <button
              onClick={() => handleResolve(em.id)}
              disabled={resolving === em.id}
              className="resolve-btn"
            >
              {resolving === em.id ? 'Resolving...' : 'Resolve'}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export default EmergencyBanner;
