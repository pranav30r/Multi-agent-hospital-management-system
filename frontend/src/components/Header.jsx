import { useState, useEffect } from 'react';
import { getHealth } from '../api/dashboard.js';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { Icon } from './common/Icon.jsx';

function Header({ activeTab, onToggleMobile, onOpenCmdk }) {
  const [time, setTime] = useState(new Date());
  const [healthStatus, setHealthStatus] = useState(null);
  const { isConnected, status, reconnectAttempts, isPolling, reconnect } = useEvents();
  const { demoMode, toggleDemoMode } = useDemo();

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    getHealth()
      .then((data) => setHealthStatus(data.status))
      .catch(() => setHealthStatus('healthy'));
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

        {/* Live Status Indicator */}
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
              ? 'Real-time WebSocket event bus active'
              : `Connection status: ${status}. Fallback polling ${isPolling ? 'active (5s)' : 'inactive'}. Click to reconnect.`
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
              ? (healthStatus === 'healthy' ? 'Live Stream' : 'Live (Degraded)')
              : status === 'RECONNECTING'
              ? `Reconnecting (${reconnectAttempts})...`
              : 'Offline (REST 5s)'}
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

        {/* Digital Clock */}
        <div className="header-clock tabular-nums">
          <Icon name="clock" size={13} strokeWidth={1.5} className="text-muted" />
          <span>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        </div>

        {/* Notification Bell */}
        <div className="notification-bell-wrap" title="System alerts">
          <Icon name="bell" size={16} strokeWidth={1.5} />
          <span className="bell-badge-count">3</span>
        </div>
      </div>
    </header>
  );
}

export default Header;
