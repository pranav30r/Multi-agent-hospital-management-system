import { useState, useEffect, useRef, useCallback } from 'react';
import { useEvents } from '../../context/EventContext.jsx';
import { useAuth } from '../../context/AuthContext.jsx';
import { Icon } from './Icon.jsx';
import {
  extractEscalationData,
  MAX_TOASTS,
  AUTO_DISMISS_STANDARD_MS,
  AUTO_DISMISS_CRITICAL_MS
} from '../../utils/escalationNotification.js';

export { extractEscalationData };

export function EscalationToast({ onNavigate }) {
  const { lastEvent } = useEvents();
  const { user } = useAuth();
  const [toasts, setToasts] = useState([]);
  const seenIdsRef = useRef(new Set());
  const timersRef = useRef(new Map());
  const isHoveredRef = useRef(false);

  const dismissToast = useCallback((id) => {
    // Clear dismissal timer if exists
    if (timersRef.current.has(id)) {
      clearTimeout(timersRef.current.get(id));
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const scheduleDismissal = useCallback((id, isCritical) => {
    if (timersRef.current.has(id)) {
      clearTimeout(timersRef.current.get(id));
    }
    const delay = isCritical ? AUTO_DISMISS_CRITICAL_MS : AUTO_DISMISS_STANDARD_MS;
    const timer = setTimeout(() => {
      if (!isHoveredRef.current) {
        dismissToast(id);
      }
    }, delay);
    timersRef.current.set(id, timer);
  }, [dismissToast]);

  // Handle incoming events from EventContext
  useEffect(() => {
    if (!lastEvent) return;

    // Check duplicate event_id to prevent double rendering
    if (lastEvent.event_id && seenIdsRef.current.has(lastEvent.event_id)) {
      return;
    }

    const toastData = extractEscalationData(lastEvent, user);
    if (!toastData) return;

    if (toastData.eventId) {
      seenIdsRef.current.add(toastData.eventId);
    }

    setToasts((prev) => {
      const updated = [toastData, ...prev.filter((t) => t.id !== toastData.id)].slice(0, MAX_TOASTS);
      return updated;
    });

    scheduleDismissal(toastData.id, toastData.isCritical);

    // Also dispatch a custom event for Header notification badge count tracking
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('escalation:new', { detail: toastData }));
    }
  }, [lastEvent, user, scheduleDismissal]);

  // Keyboard accessibility: ESC key dismisses newest toast
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && toasts.length > 0) {
        dismissToast(toasts[0].id);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toasts, dismissToast]);

  // Cleanup timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      className="escalation-toast-container"
      role="region"
      aria-label="Clinical Escalation Notifications"
      onMouseEnter={() => { isHoveredRef.current = true; }}
      onMouseLeave={() => { isHoveredRef.current = false; }}
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`escalation-toast-card ${toast.isCritical ? 'toast-critical' : 'toast-urgent'}`}
          role="alert"
          aria-live={toast.isCritical ? 'assertive' : 'polite'}
        >
          <div className="toast-header-row">
            <div className="toast-title-group">
              <span className={`toast-pulse-dot ${toast.isCritical ? 'pulse-critical' : 'pulse-urgent'}`} />
              <span className="toast-category">{toast.category}</span>
              <span className={`toast-urgency-badge urgency-${toast.urgency.toLowerCase()}`}>
                {toast.urgency}
              </span>
            </div>
            <button
              type="button"
              className="toast-close-btn"
              onClick={() => dismissToast(toast.id)}
              aria-label={`Dismiss ${toast.category} alert`}
            >
              <Icon name="x" size={14} />
            </button>
          </div>

          <div className="toast-body">
            <p className="toast-reason">{toast.reason}</p>
            <div className="toast-meta-row">
              {toast.encounterRef && (
                <span className="toast-meta-tag">
                  <Icon name="file" size={11} />
                  {toast.encounterRef}
                </span>
              )}
              {toast.deptRef && (
                <span className="toast-meta-tag">
                  <Icon name="map-pin" size={11} />
                  {toast.deptRef}
                </span>
              )}
              <span className="toast-time">
                {new Date(toast.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </div>
          </div>

          <div className="toast-actions">
            <button
              type="button"
              className="toast-btn-action"
              onClick={() => {
                dismissToast(toast.id);
                if (onNavigate) {
                  onNavigate(toast.eventType === 'APPROVAL_REQUIRED' ? 'approvals' : 'patients');
                }
              }}
            >
              {toast.eventType === 'APPROVAL_REQUIRED' ? 'Review Approval' : 'View in Queue'} &rarr;
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default EscalationToast;
