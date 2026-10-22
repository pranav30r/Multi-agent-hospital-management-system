import { useAuth } from "../context/AuthContext.jsx";
import { Icon } from "./common/Icon.jsx";

function Sidebar({ activeTab, onSelectTab, isOpen, onCloseMobile, isCollapsed }) {
  const { user, logout } = useAuth();
  const isAdmin = user && user.role === "ADMINISTRATOR";

  const mainNavItems = [
    { id: "overview", label: "Command Center", icon: "command-center" },
    { id: "beds", label: "Bed Capacity", icon: "bed-capacity" },
    { id: "patients", label: "Emergency Triage", icon: "emergency-triage" },
    { id: "intake", label: "Patient Intake", icon: "patient-intake" },
    { id: "approvals", label: "Approvals", icon: "approvals" },
  ];

  const adminNavItems = [
    { id: "admin_dashboard", label: "Overview", icon: "admin-overview" },
    { id: "admin_users", label: "Users & Roles", icon: "users-roles" },
    { id: "admin_beds", label: "Wards & Beds", icon: "wards-beds" },
    { id: "admin_audit", label: "Audit Log", icon: "audit-log" },
    { id: "admin_ai", label: "AI Controls", icon: "ai-controls" },
    { id: "admin_settings", label: "Settings", icon: "settings" },
  ];

  const handleNav = (tabId) => {
    onSelectTab(tabId);
    if (onCloseMobile) onCloseMobile();
  };

  return (
    <aside className={`app-sidebar ${isOpen ? "open" : ""} ${isCollapsed ? "collapsed" : ""}`}>
      {/* Brand Header with Clean Monogram */}
      <div className="sidebar-brand">
        <div className="brand-monogram">
          <span>MC</span>
        </div>
        {!isCollapsed && (
          <div className="brand-text">
            <span className="brand-title">MEDICENTER</span>
            <span className="brand-subtitle">Clinical Operations</span>
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {!isCollapsed && <div className="nav-section-label">OPERATIONS</div>}
        {mainNavItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${activeTab === item.id ? "active" : ""}`}
            onClick={() => handleNav(item.id)}
            title={isCollapsed ? item.label : undefined}
          >
            <span className="nav-icon"><Icon name={item.icon} size={18} strokeWidth={1.5} /></span>
            {!isCollapsed && <span className="nav-label">{item.label}</span>}
          </button>
        ))}

        {isAdmin && (
          <>
            {!isCollapsed && <div className="nav-section-label">ADMINISTRATION</div>}
            {adminNavItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => handleNav(item.id)}
                title={isCollapsed ? item.label : undefined}
              >
                <span className="nav-icon"><Icon name={item.icon} size={18} strokeWidth={1.5} /></span>
                {!isCollapsed && <span className="nav-label">{item.label}</span>}
              </button>
            ))}
          </>
        )}

        {!isCollapsed && <div className="nav-section-label secondary">GOVERNANCE</div>}
        <button
          type="button"
          className={`nav-item ${activeTab === "privacy" ? "active" : ""}`}
          onClick={() => handleNav("privacy")}
          title={isCollapsed ? "Privacy Policy" : undefined}
        >
          <span className="nav-icon"><Icon name="privacy" size={18} strokeWidth={1.5} /></span>
          {!isCollapsed && <span className="nav-label">Privacy Policy</span>}
        </button>
        <button
          type="button"
          className={`nav-item ${activeTab === "terms" ? "active" : ""}`}
          onClick={() => handleNav("terms")}
          title={isCollapsed ? "Terms of Service" : undefined}
        >
          <span className="nav-icon"><Icon name="terms" size={18} strokeWidth={1.5} /></span>
          {!isCollapsed && <span className="nav-label">Terms of Service</span>}
        </button>
      </nav>

      {user && (
        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="user-avatar" title={user.role}>
              <Icon name="users-roles" size={16} strokeWidth={1.5} />
            </div>
            {!isCollapsed && (
              <div className="user-details">
                <span className="user-name">{user.first_name} {user.last_name}</span>
                <span className="user-role-badge">
                  {user.role === "ADMINISTRATOR"
                    ? "Administrator"
                    : user.role === "DOCTOR"
                    ? "Doctor"
                    : user.role === "CHARGE_NURSE"
                    ? "Charge Nurse"
                    : user.role.replace(/_/g, " ")}
                </span>
              </div>
            )}
          </div>
          <button type="button" className="btn-logout" onClick={logout} title="Sign Out">
            <Icon name="log-out" size={15} strokeWidth={1.5} />
            {!isCollapsed && <span>Sign Out</span>}
          </button>
        </div>
      )}
    </aside>
  );
}

export default Sidebar;
