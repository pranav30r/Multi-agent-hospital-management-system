import { useState, useEffect } from 'react';
import { Icon } from './common/Icon.jsx';

export const CommandPalette = ({ isOpen, onClose, onNavigate }) => {
  const [query, setQuery] = useState('');

  const commands = [
    { id: 'overview', title: 'Command Center Overview', category: 'Operations', icon: 'activity' },
    { id: 'beds', title: 'Bed Capacity & Ward Matrix', category: 'Operations', icon: 'bed' },
    { id: 'patients', title: 'Emergency Triage Queue', category: 'Operations', icon: 'users' },
    { id: 'intake', title: 'New Patient Intake & Vitals', category: 'Operations', icon: 'user-plus' },
    { id: 'approvals', title: 'Clinical AI Approvals Queue', category: 'Operations', icon: 'check-circle' },
    { id: 'admin_dashboard', title: 'Executive Operations Telemetry', category: 'Administration', icon: 'cpu' },
    { id: 'admin_users', title: 'Personnel & Role Management', category: 'Administration', icon: 'users' },
    { id: 'admin_beds', title: 'Ward & Bed Capacity Config', category: 'Administration', icon: 'settings' },
    { id: 'admin_audit', title: 'Regulatory Audit Trail Ledger', category: 'Administration', icon: 'file-text' },
    { id: 'admin_ai', title: 'AI Multi-Agent Governance', category: 'Administration', icon: 'sparkles' },
    { id: 'admin_settings', title: 'Institutional Facility Profile', category: 'Administration', icon: 'settings' },
  ];

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else window.dispatchEvent(new CustomEvent('cmdk:open'));
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filtered = commands.filter((c) =>
    `${c.title} ${c.category}`.toLowerCase().includes(query.toLowerCase().trim())
  );

  return (
    <div className="cmd-palette-backdrop" onClick={onClose}>
      <div className="cmd-palette-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cmd-palette-input-box">
          <Icon name="search" size={18} className="cmd-search-icon" />
          <input
            type="text"
            className="cmd-input"
            placeholder="Type a command or jump to view..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <span className="cmd-esc-badge">ESC</span>
        </div>

        <div className="cmd-results-list">
          {filtered.length === 0 ? (
            <div className="cmd-empty">No matching operational actions found.</div>
          ) : (
            filtered.map((cmd) => (
              <div
                key={cmd.id}
                className="cmd-result-item"
                onClick={() => {
                  onNavigate(cmd.id);
                  onClose();
                }}
              >
                <Icon name={cmd.icon} size={16} className="cmd-item-icon" />
                <span className="cmd-item-title">{cmd.title}</span>
                <span className="cmd-item-category">{cmd.category}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
