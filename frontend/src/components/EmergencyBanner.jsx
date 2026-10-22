import { useEffect, useState, useCallback, useRef } from "react";
import { listActiveEmergencies, resolveEmergency } from "../api/emergencies.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useEvents } from "../context/EventContext.jsx";

function EmergencyBanner() {
  const { user } = useAuth();
  const { lastEvent } = useEvents();
  const [emergencies, setEmergencies] = useState([]);
  const [resolving, setResolving] = useState(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const canResolve = user && ["ADMINISTRATOR", "DOCTOR", "CHARGE_NURSE"].includes(user.role);

  const fetchEmergencies = useCallback(async () => {
    try {
      const data = await listActiveEmergencies();
      setEmergencies(data || []);
    } catch {
      // Non-blocking background fetch error handling
    }
  }, []);

  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchEmergencies();
    }, 200);
  }, [fetchEmergencies]);

  useEffect(() => {
    fetchEmergencies();
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchEmergencies]);

  useEffect(() => {
    if (
      lastEvent &&
      ["EMERGENCY_DECLARED", "EMERGENCY_RESOLVED", "EMERGENCY_ESCALATED", "SYSTEM_CONNECTED"].includes(
        lastEvent.event_type
      )
    ) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener("websocket:reconnected", handler);
    return () => window.removeEventListener("websocket:reconnected", handler);
  }, [debouncedFetch]);

  const handleResolve = async (id) => {
    setResolving(id);
    try {
      await resolveEmergency(id);
      window.dispatchEvent(new CustomEvent("emergency:updated"));
      await fetchEmergencies();
    } catch {
      // Error handling
    } finally {
      setResolving(null);
    }
  };

  const handleResolveAll = async () => {
    setResolving("all");
    try {
      for (const em of emergencies) {
        await resolveEmergency(em.id);
      }
      window.dispatchEvent(new CustomEvent("emergency:updated"));
      await fetchEmergencies();
    } catch {
      // Error handling
    } finally {
      setResolving(null);
    }
  };

  if (!emergencies || emergencies.length === 0) return null;

  const topEmergency = emergencies[0];

  return (
    <div className="emergency-alert-container">
      <div className="emergency-summary-bar">
        <div className="emergency-alert-left">
          <div className="emergency-pulse-indicator">
            <span className="pulse-dot" />
            <span className="alert-type-badge">CRITICAL ALERT</span>
          </div>
          <div className="alert-headline">
            <span className="alert-count-pill">{emergencies.length} Active Incident{emergencies.length > 1 ? "s" : ""}</span>
            <span className="alert-text">
              <strong>{topEmergency.event_type.replace(/_/g, " ")}:</strong> {topEmergency.description}
            </span>
          </div>
        </div>

        <div className="emergency-alert-actions">
          {emergencies.length > 1 && (
            <button
              type="button"
              className="btn-alert-toggle"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? "Collapse Details ▲" : `View All (${emergencies.length}) ▼`}
            </button>
          )}

          {canResolve && emergencies.length > 1 && (
            <button
              type="button"
              className="btn-alert-resolve-all"
              onClick={handleResolveAll}
              disabled={resolving === "all"}
            >
              {resolving === "all" ? "Resolving All..." : "Resolve All"}
            </button>
          )}

          {canResolve && emergencies.length === 1 && (
            <button
              type="button"
              className="btn-alert-resolve"
              onClick={() => handleResolve(topEmergency.id)}
              disabled={resolving === topEmergency.id}
            >
              {resolving === topEmergency.id ? "Resolving..." : "Resolve Incident"}
            </button>
          )}
        </div>
      </div>

      {isExpanded && emergencies.length > 1 && (
        <div className="emergency-expanded-drawer">
          <div className="expanded-incident-list">
            {emergencies.map((em, idx) => (
              <div key={em.id} className="expanded-incident-row">
                <div className="incident-meta">
                  <span className="incident-index">#{idx + 1}</span>
                  <span className="incident-severity-tag">{em.severity}</span>
                  <span className="incident-desc">
                    <strong>{em.event_type.replace(/_/g, " ")}:</strong> {em.description}
                  </span>
                </div>
                {canResolve && (
                  <button
                    type="button"
                    className="btn-incident-resolve"
                    onClick={() => handleResolve(em.id)}
                    disabled={resolving === em.id}
                  >
                    {resolving === em.id ? "..." : "Resolve"}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default EmergencyBanner;
