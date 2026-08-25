import React, { useState } from 'react';

export default function AddDiseaseModal({ onClose, onSubmit }) {
  const [formData, setFormData] = useState({
    name: '',
    icd_code: '',
    category: 'Respiratory',
    is_communicable: false,
    requires_isolation: false,
    added_by: 'REC-001'
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="panel-title">
          <span>🦠 Add New Disease to Registry</span>
          <button className="btn btn-secondary" style={{ padding: '0.2rem 0.5rem' }} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="form-group">
            <label>Disease Name</label>
            <input className="form-control" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required placeholder="e.g. Acute Viral Myocarditis" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label>ICD-10 Code (Optional)</label>
              <input className="form-control" value={formData.icd_code} onChange={(e) => setFormData({ ...formData, icd_code: e.target.value })} placeholder="e.g. I40.9" />
            </div>

            <div className="form-group">
              <label>Medical Category</label>
              <select className="form-control" value={formData.category} onChange={(e) => setFormData({ ...formData, category: e.target.value })}>
                <option value="Cardiovascular">Cardiovascular</option>
                <option value="Respiratory">Respiratory</option>
                <option value="Infectious">Infectious</option>
                <option value="Endocrine">Endocrine</option>
                <option value="Neurology">Neurology</option>
                <option value="Gastrointestinal">Gastrointestinal</option>
                <option value="General">General</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', background: '#0f172a', padding: '0.8rem', borderRadius: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: '600' }}>Clinical Context Flags</label>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
              <input type="checkbox" checked={formData.is_communicable} onChange={(e) => setFormData({ ...formData, is_communicable: e.target.checked })} />
              Infectious / Communicable Disease
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
              <input type="checkbox" checked={formData.requires_isolation} onChange={(e) => setFormData({ ...formData, requires_isolation: e.target.checked })} />
              Requires Isolation Bed (Negative Pressure)
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">➕ Register Disease</button>
          </div>
        </form>
      </div>
    </div>
  );
}
