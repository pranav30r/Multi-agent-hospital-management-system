import { useState } from "react";
import { getAiApprovalSettings, saveAiApprovalSettings } from "../../api/admin.js";

function AdminAiSettings() {
  const [config, setConfig] = useState(getAiApprovalSettings());
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleToggle = (key) => {
    setConfig((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleChange = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = (e) => {
    e.preventDefault();
    saveAiApprovalSettings(config);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">AI Controls & Decision Policies</h2>
          <p className="admin-subtitle">
            Configure automated triage thresholds, physician escalation rules, and decision timeouts.
          </p>
        </div>
      </div>

      {savedSuccess && (
        <div className="alert-banner alert-success" role="status">
          <span>AI decision parameters updated successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="card admin-form-card">
        <h3 className="section-title">Human-in-the-Loop Barrier Enforcement</h3>
        <p className="section-help-text">
          Define clinical scenarios where autonomous multi-agent allocations are locked pending attending physician review.
        </p>

        <div className="toggle-list">
          <div className="toggle-item">
            <div>
              <div className="toggle-label">Require Physician Sign-Off for Intensive Care Unit (ICU) Allocations</div>
              <div className="toggle-desc">Any bed booking involving ICU ventilators or cardiac monitoring triggers an approval ticket.</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={config.requirePhysicianForIcu}
                onChange={() => handleToggle("requirePhysicianForIcu")}
              />
              <span className="slider round" />
            </label>
          </div>

          <div className="toggle-item">
            <div>
              <div className="toggle-label">Require Physician Sign-Off for Emergency Department Surge Protocols</div>
              <div className="toggle-desc">Lock auto-rerouting when ER department occupancy exceeds surge capacity levels.</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={config.requirePhysicianForEmergencySurge}
                onChange={() => handleToggle("requirePhysicianForEmergencySurge")}
              />
              <span className="slider round" />
            </label>
          </div>

          <div className="toggle-item">
            <div>
              <div className="toggle-label">Strict Ventilator Resource Verification</div>
              <div className="toggle-desc">Ensure invasive mechanical ventilators cannot be allocated without respiratory care signoff.</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={config.requirePhysicianForVentilator}
                onChange={() => handleToggle("requirePhysicianForVentilator")}
              />
              <span className="slider round" />
            </label>
          </div>
        </div>

        <div className="form-divider" style={{ margin: "24px 0" }} />

        <h3 className="section-title">Autonomy & Escalation Thresholds</h3>

        <div className="form-grid-2col" style={{ marginTop: "16px" }}>
          <div className="form-group">
            <label htmlFor="risk_threshold">High-Risk Escalation Cutoff (0.00 to 1.00)</label>
            <input
              id="risk_threshold"
              type="number"
              step="0.05"
              min="0.5"
              max="0.99"
              className="form-input"
              value={config.riskThresholdHigh}
              onChange={(e) => handleChange("riskThresholdHigh", parseFloat(e.target.value))}
            />
            <span className="field-hint">Any agent decision with risk score above this value requires human clinician review.</span>
          </div>

          <div className="form-group">
            <label htmlFor="timeout_mins">Approval Ticket Expiration (Minutes)</label>
            <input
              id="timeout_mins"
              type="number"
              min="5"
              max="120"
              className="form-input"
              value={config.approvalTimeoutMinutes}
              onChange={(e) => handleChange("approvalTimeoutMinutes", parseInt(e.target.value, 10))}
            />
            <span className="field-hint">Time allowed before unattended tickets trigger emergency escalation.</span>
          </div>

          <div className="form-group form-group-full">
            <label htmlFor="fallback_action">Emergency Fallback Action on Timeout</label>
            <div className="custom-select-wrapper">
              <select
                id="fallback_action"
                className="form-select"
                value={config.fallbackActionOnTimeout}
                onChange={(e) => handleChange("fallbackActionOnTimeout", e.target.value)}
              >
                <option value="ESCALATE_TO_CHIEF_RESIDENT">Escalate to Chief Medical Officer & On-Call Resident</option>
                <option value="AUTO_RESERVE_CONSERVATIVE">Auto-Reserve Most Conservative Available Bed</option>
                <option value="HOLD_IN_ER_QUEUE">Retain Patient in Supervised Emergency Holding Area</option>
              </select>
            </div>
          </div>
        </div>

        <div className="form-divider" style={{ margin: "24px 0" }} />

        <div className="form-actions-bar">
          <button type="submit" className="btn btn-primary">
            Save AI Governance Configuration
          </button>
        </div>
      </form>
    </div>
  );
}

export default AdminAiSettings;
