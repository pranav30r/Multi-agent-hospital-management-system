import { Icon } from './Icon.jsx';

export const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  loading = false,
  disabled = false,
  className = '',
  ...props
}) => {
  return (
    <button
      className={`btn btn-${variant} btn-${size} ${loading ? 'loading' : ''} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className="spinner-mini" />
      ) : icon ? (
        <span className="btn-icon">{icon}</span>
      ) : null}
      <span className="btn-text">{children}</span>
      {!loading && iconRight ? <span className="btn-icon-right">{iconRight}</span> : null}
    </button>
  );
};

export const StatusPill = ({ status, variant, label, children }) => {
  const norm = (variant || status || 'neutral').toLowerCase();
  return (
    <span className={`status-pill status-${norm}`}>
      <span className="pill-dot" />
      <span>{label || children || status}</span>
    </span>
  );
};

export const Card = ({ title, subtitle, action, children, className = '', headerClass = '', ...props }) => {
  return (
    <div className={`card ${className}`} {...props}>
      {(title || subtitle || action) && (
        <div className={`card-header-clean ${headerClass}`}>
          <div>
            {title && <h3 className="card-title-clean">{title}</h3>}
            {subtitle && <p className="card-subtitle-clean">{subtitle}</p>}
          </div>
          {action && <div className="card-action-clean">{action}</div>}
        </div>
      )}
      <div className="card-content-clean">{children}</div>
    </div>
  );
};

export const StatCard = ({ title, value, unit, trend, trendValue, sparkline = [40, 48, 55, 52, 60, 68, 64], icon, caption }) => {
  const isUp = trend === 'up';
  return (
    <div className="stat-card">
      <div className="stat-card-top">
        <span className="stat-card-title">{title}</span>
        {icon && <span className="stat-card-icon">{icon}</span>}
      </div>

      <div className="stat-card-mid">
        <span className="stat-card-value">{value}</span>
        {unit && <span className="stat-card-unit">{unit}</span>}
        {trendValue && (
          <span className={`stat-trend-tag ${isUp ? 'trend-up' : 'trend-down'}`}>
            <Icon name={isUp ? 'trending-up' : 'trending-down'} size={12} />
            {trendValue}
          </span>
        )}
      </div>

      {sparkline && (
        <div className="stat-sparkline-row">
          <svg className="sparkline-svg" viewBox="0 0 100 24" preserveAspectRatio="none">
            <polyline
              fill="none"
              stroke="var(--color-primary)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={sparkline.map((val, idx) => `${(idx / (sparkline.length - 1)) * 100},${24 - (val / 100) * 20}`).join(' ')}
            />
          </svg>
        </div>
      )}

      {caption && <span className="stat-card-caption">{caption}</span>}
    </div>
  );
};

export const CustomSelect = ({ label, id, value, onChange, options = [], error, className = '', ...props }) => {
  return (
    <div className={`form-group ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      <div className="custom-select-wrapper">
        <select id={id} className={`form-select ${error ? 'has-error' : ''}`} value={value} onChange={onChange} {...props}>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {error && <span className="field-error-text">{error}</span>}
    </div>
  );
};

export const EmptyState = ({ icon = 'check-circle', title, description, action }) => {
  return (
    <div className="empty-state-card">
      <div className="empty-state-icon-circle">
        <Icon name={icon} size={28} />
      </div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-description">{description}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
};

export const Skeleton = ({ width = '100%', height = '16px', radius = '4px', className = '' }) => {
  return (
    <div
      className={`skeleton-shimmer ${className}`}
      style={{ width, height, borderRadius: radius }}
    />
  );
};

export const Drawer = ({ isOpen, onClose, title, subtitle, children }) => {
  if (!isOpen) return null;
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h3 className="drawer-title">{title}</h3>
            {subtitle && <p className="drawer-subtitle">{subtitle}</p>}
          </div>
          <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Close drawer">
            <Icon name="x" size={18} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  );
};
