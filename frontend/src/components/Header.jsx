import { useState, useEffect, useCallback } from 'react';
import { getHealth } from '../api/dashboard.js';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { Icon } from './common/Icon.jsx';

const HEALTH_POLL_INTERVAL_MS = 30000;

function Header({ activeTab, onToggleMobile, onOpenCmdk, onSelectTab }) {
  const [time, setTime] = useState(new Date());
  const [healthData, setHealthData] = useState({
    status: 'unknown',
    redis: 'unknown',
    database: 'unknown',
  });
  const [unreadEscalations, setUnreadEscalations] = useState(0);
  const { isConnected, status, reconnectAttempts, isPolling, reconnect } = useEvents();
  const { demoMode, toggleDemoMode } = useDemo();

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealthData({
        status: data.status || 'unknown',
        redis: data.redis || 'unknown',
        database: data.database || 'unknown',
      });
    } catch {
      // Missing or failed health probe must be recorded as unknown/unavailable, NEVER assumed healthy
      setHealthData({
        status: 'unknown',
        redis: 'unknown',
        database: 'unknown',
      });
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const pollTimer = setInterval(fetchHealth, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(pollTimer);
  }, [fetchHealth]);

  // Listen to escalation events to dynamically increment notification bell count
  useEffect(() => {
    const handleNewEscalation = () => {
      setUnreadEscalations((prev) => prev + 1);
    };
    const handleAuthRefresh = () => {
      // Re-aligned with server state
    };

    window.addEventListener('escalation:new', handleNewEscalation);
    window.addEventListener('app:refresh-authoritative', handleAuthRefresh);
    return () => {
      window.removeEventListener('escalation:new', handleNewEscalation);
      window.removeEventListener('app:refresh-authoritative', handleAuthRefresh);
    };
  }, []);

  const tabTitles = {
    overview: 'Command Center',
    beds: 'Bed Capacity',
    patients: 'Emergency Triage',
    intake: 'Patient Intake',
    approvals: 'Approvals',
    admin_dashboard: 'Overview',
    admin_users: 'Users & Roles',
    admin_beds: 'Wards & Beds',
    admin_audit: 'Audit Log',
    admin_ai: 'AI Controls',
    admin_settings: 'Settings',
    privacy: 'Privacy Policy',
    terms: 'Terms of Service',
  };

  // Determine Event Stream / Redis health presentation
  const isRedisOnline = healthData.redis === 'connected';
  const isRedisDegraded = healthData.redis === 'unreachable';

  const eventStreamLabel = isRedisOnline
    ? 'Redis: Online'
    : isRedisDegraded
    ? 'Stream: Degraded (In-Memory Fallback)'
    : 'Stream: Unknown';

  const eventStreamClass = isRedisOnline
    ? 'event-bus-healthy'
    : isRedisDegraded
    ? 'event-bus-degraded'
    : 'event-bus-unavailable';

  const eventStreamTitle = isRedisOnline
    ? 'Distributed Redis Pub/Sub operational across all worker nodes.'
    : isRedisDegraded
    ? 'Redis unreachable. Multi-agent event delivery operating safely on local node in-memory fallback.'
    : 'Backend event-stream health probe unreachable or response missing.';

  return (
    <header className="app-header-epic">
      <div className="header-left">
        <button
          type="button"
          className="mobile-menu-btn"
          onClick={onToggleMobile}
          aria-label="Toggle navigation drawer"
        >
          <Icon name="command-center" size={18} strokeWidth={1.5} />
        </button>

        <div className="header-breadcrumbs-clean">
          <span className="crumb-root">MEDICENTER</span>
          <span className="crumb-sep">/</span>
          <span className="crumb-active">{tabTitles[activeTab] || 'Command Center'}</span>
        </div>
      </div>

      <div className="header-center">
        {/* Global Search Trigger */}
        <button
          type="button"
          className="global-search-trigger"
          onClick={onOpenCmdk}
          title="Search patients, beds, or actions (Ctrl+K / Cmd+K)"
        >
          <Icon name="search" size={14} strokeWidth={1.5} className="search-icon-dim" />
          <span className="search-placeholder">Search patients, beds, or actions...</span>
          <span className="search-kbd-shortcut">
            <kbd>Ctrl</kbd>
            <kbd>K</kbd>
          </span>
        </button>
      </div>

      <div className="header-right">
        {/* Realistic Demo Data Switch */}
        <button
          type="button"
          className={`demo-pill-btn ${demoMode ? 'demo-active' : ''}`}
          onClick={toggleDemoMode}
          title="Toggle clinical scenario data"
        >
          <span className="demo-dot" />
          <span className="demo-text">{demoMode ? 'Demo Data Active' : 'Load Demo Data'}</span>
        </button>

        {/* Real-Time WebSocket Transport Indicator */}
        <div
          className={`live-status-pill ${
            isConnected
              ? 'status-connected'
              : status === 'RECONNECTING'
              ? 'status-reconnecting'
              : 'status-disconnected'
          }`}
          title={
            isConnected
              ? 'Client WebSocket transport connected to server.'
              : `Connection status: ${status}. Fallback REST polling ${isPolling ? 'active (5s)' : 'inactive'}. Click to reconnect.`
          }
        >
          <span
            className={`pulse-indicator ${
              isConnected
                ? 'online'
                : status === 'RECONNECTING'
                ? 'reconnecting'
                : 'offline'
            }`}
          />
          <span className="status-text">
            {isConnected
              ? 'WebSocket: Live'
              : status === 'RECONNECTING'
              ? `Reconnecting (${reconnectAttempts})...`
              : 'Disconnected (REST 5s)'}
          </span>
          {!isConnected && (
            <button
              type="button"
              className="live-retry-btn"
              onClick={reconnect}
              aria-label="Retry connection"
              title="Manually reconnect to live event bus"
            >
              Retry
            </button>
          )}
        </div>

        {/* Backend Event Stream / Redis Health Signal */}
        <div
          className={`event-bus-indicator ${eventStreamClass}`}
          title={eventStreamTitle}
          role="status"
          aria-label={eventStreamTitle}
        >
          <Icon name="activity" size={12} strokeWidth={2} />
          <span>{eventStreamLabel}</span>
        </div>

        {/* Digital Clock */}
        <div className="header-clock tabular-nums">
          <Icon name="clock" size={13} strokeWidth={1.5} className="text-muted" />
          <span>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        </div>

        {/* Notification Bell */}
        <button
          type="button"
          className="notification-bell-wrap"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
          title={unreadEscalations > 0 ? `${unreadEscalations} new clinical escalation(s)` : 'No new notifications'}
          aria-label="View clinical approvals and escalations"
          onClick={() => {
            setUnreadEscalations(0);
            if (onSelectTab) onSelectTab('approvals');
          }}
        >
          <Icon name="bell" size={16} strokeWidth={1.5} />
          {unreadEscalations > 0 && (
            <span className="bell-badge-count">{unreadEscalations > 9 ? '9+' : unreadEscalations}</span>
          )}
        </button>
      </div>
    </header>
  );
}

export default Header;
