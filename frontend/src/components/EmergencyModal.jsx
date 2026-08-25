import React, { useState } from 'react';

export default function EmergencyModal({ onClose, onSubmit }) {
  const [formData, setFormData] = useState({
    event_type: 'MASS_CASUALTY',
    severity: 'HIGH',
    description: 'Major multi-vehicle highway accident; expecting 8 critical trauma arrivals within 15 minutes',
    expected_patient_surge: 8,
    declared_by: 'ADM-001'
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ borderColor: '#ef4444' }}>
        <div className="panel-title" style={{ color: '#f87171' }}>
          <span>🆘 DECLARE HOSPITAL EMERGENCY</span>
          <button className="btn btn-secondary" style={{ padding: '0.2rem 0.5rem' }} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="form-group">
            <label>Emergency Surge Type</label>
            <select className="form-control" value={formData.event_type} onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}>
              <option value="MASS_CASUALTY">Mass Casualty Incident (Trauma / Accidents)</option>
              <option value="PANDEMIC_SURGE">Pandemic / Outbreak Surge</option>
              <option value="INFRASTRUCTURE_FAILURE">Facility / Power Failure</option>
              <option value="STAFF_CRISIS">Severe Staffing Shortage</option>
            </select>
          </div>

          <div className="form-group">
            <label>Severity Level</label>
            <select className="form-control" value={formData.severity} onChange={(e) => setFormData({ ...formData, severity: e.target.value })}>
              <option value="HIGH">HIGH (Activate Surge Staffing & Bed Reserve)</option>
              <option value="CRITICAL">CRITICAL (System-Wide Priority Emergency Override)</option>
            </select>
          </div>

          <div className="form-group">
            <label>Expected Patient Surge Count</label>
            <input className="form-control" type="number" value={formData.expected_patient_surge} onChange={(e) => setFormData({ ...formData, expected_patient_surge: parseInt(e.target.value) })} />
          </div>

          <div className="form-group">
            <label>Emergency Situation Description</label>
            <textarea className="form-control" rows="3" value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} required />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-danger">🚨 DECLARE EMERGENCY NOW</button>
          </div>
        </form>
      </div>
    </div>
  );
}
