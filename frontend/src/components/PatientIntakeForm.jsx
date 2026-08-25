import React, { useState } from 'react';

export default function PatientIntakeForm({ onClose, onSubmit }) {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    age: 45,
    gender: 'M',
    blood_group: 'O+',
    contact_phone: '+919876543210',
    emergency_contact: '+919876543211',
    chief_complaint: 'Severe chest pain radiating to left arm with diaphoresis',
    heart_rate: 110,
    bp_systolic: 145,
    bp_diastolic: 95,
    spo2: 88,
    temperature_f: 99.1,
    pain_level: 8,
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="panel-title">
          <span>➕ New Patient Triage Intake</span>
          <button className="btn btn-secondary" style={{ padding: '0.2rem 0.5rem' }} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>First Name</label>
              <input className="form-control" name="first_name" value={formData.first_name} onChange={handleChange} required placeholder="Rajesh" />
            </div>
            <div className="form-group">
              <label>Last Name</label>
              <input className="form-control" name="last_name" value={formData.last_name} onChange={handleChange} required placeholder="Kumar" />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>Age</label>
              <input className="form-control" type="number" name="age" value={formData.age} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label>Gender</label>
              <select className="form-control" name="gender" value={formData.gender} onChange={handleChange}>
                <option value="M">Male</option>
                <option value="F">Female</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div className="form-group">
              <label>Blood Group</label>
              <input className="form-control" name="blood_group" value={formData.blood_group} onChange={handleChange} />
            </div>
          </div>

          <div className="form-group">
            <label>Chief Complaint (Clinical Presentation)</label>
            <textarea className="form-control" rows="2" name="chief_complaint" value={formData.chief_complaint} onChange={handleChange} required />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.5rem' }}>
            <div className="form-group">
              <label>Heart Rate</label>
              <input className="form-control" type="number" name="heart_rate" value={formData.heart_rate} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>SpO2 (%)</label>
              <input className="form-control" type="number" name="spo2" value={formData.spo2} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>BP Sys</label>
              <input className="form-control" type="number" name="bp_systolic" value={formData.bp_systolic} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>Pain (0-10)</label>
              <input className="form-control" type="number" name="pain_level" value={formData.pain_level} onChange={handleChange} />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Submit Triage Intake</button>
          </div>
        </form>
      </div>
    </div>
  );
}
