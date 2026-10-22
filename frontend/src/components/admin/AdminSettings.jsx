import { useState } from "react";
import { getHospitalSettings, saveHospitalSettings } from "../../api/admin.js";

function AdminSettings() {
  const [settings, setSettings] = useState(getHospitalSettings());
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setSettings((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSave = (e) => {
    e.preventDefault();
    saveHospitalSettings(settings);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">Facility Settings</h2>
          <p className="admin-subtitle">
            Configure hospital profile, time zones, emergency contacts, and automated refresh intervals.
          </p>
        </div>
      </div>

      {savedSuccess && (
        <div className="alert-banner alert-success" role="status">
          <span>Facility configuration saved successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="card admin-form-card">
        <h3 className="section-title">Facility Profile & Identity</h3>

        <div className="form-grid-2col" style={{ marginTop: "16px" }}>
          <div className="form-group">
            <label htmlFor="hospitalName">Hospital / Medical Center Name</label>
            <input
              id="hospitalName"
              type="text"
              name="hospitalName"
              className="form-input"
              value={settings.hospitalName}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="facilityCode">Institutional Facility Code</label>
            <input
              id="facilityCode"
              type="text"
              name="facilityCode"
              className="form-input font-mono"
              value={settings.facilityCode}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="timeZone">Operational Time Zone</label>
            <div className="custom-select-wrapper">
              <select
                id="timeZone"
                name="timeZone"
                className="form-select"
                value={settings.timeZone}
                onChange={handleChange}
              >
                <option value="Asia/Kolkata (IST)">Asia/Kolkata (IST, UTC+5:30)</option>
                <option value="America/New_York (EST)">America/New York (EST/EDT)</option>
                <option value="America/Los_Angeles (PST)">America/Los Angeles (PST/PDT)</option>
                <option value="Europe/London (GMT/BST)">Europe/London (GMT/BST)</option>
                <option value="UTC">Coordinated Universal Time (UTC)</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="emergencyContact">Emergency Operations Hotline</label>
            <input
              id="emergencyContact"
              type="tel"
              name="emergencyContact"
              className="form-input"
              value={settings.emergencyContact}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group form-group-full">
            <label htmlFor="notificationEmail">Clinical Dispatch Alert Email</label>
            <input
              id="notificationEmail"
              type="email"
              name="notificationEmail"
              className="form-input"
              value={settings.notificationEmail}
              onChange={handleChange}
              required
            />
          </div>
        </div>

        <div className="form-divider" style={{ margin: "24px 0" }} />

        <h3 className="section-title">System & Telemetry Sync</h3>

        <div className="form-grid-2col" style={{ marginTop: "16px" }}>
          <div className="form-group">
            <label htmlFor="autoRefreshIntervalSec">Telemetry Polling Interval (Seconds)</label>
            <input
              id="autoRefreshIntervalSec"
              type="number"
              name="autoRefreshIntervalSec"
              min="5"
              max="60"
              className="form-input"
              value={settings.autoRefreshIntervalSec}
              onChange={handleChange}
            />
            <span className="field-hint">Frequency for bed capacity and emergency triage status background polling.</span>
          </div>

          <div className="form-group" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <label className="checkbox-label">
              <input
                type="checkbox"
                name="enableAuditExport"
                checked={settings.enableAuditExport}
                onChange={handleChange}
              />
              <span>Enable One-Click CSV Export for External Regulators</span>
            </label>
          </div>
        </div>

        <div className="form-divider" style={{ margin: "24px 0" }} />

        <div className="form-actions-bar">
          <button type="submit" className="btn btn-primary">
            Save Institutional Settings
          </button>
        </div>
      </form>
    </div>
  );
}

export default AdminSettings;
