import React, { useState } from 'react';

export default function BedGrid({ beds = [], departments = [], onConfirmInBed }) {
  const [selectedDept, setSelectedDept] = useState('ALL');

  const filteredBeds = selectedDept === 'ALL'
    ? beds
    : beds.filter(b => b.department_id === selectedDept);

  return (
    <div className="panel-card">
      <div className="panel-title">
        <span>🛏️ Hospital Bed Grid</span>
        <select 
          className="form-control" 
          value={selectedDept} 
          onChange={(e) => setSelectedDept(e.target.value)}
          style={{ width: 'auto', padding: '0.3rem 0.6rem', fontSize: '0.8rem' }}
        >
          <option value="ALL">All Departments ({beds.length} beds)</option>
          {departments.map(d => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      <div className="bed-grid">
        {filteredBeds.map(bed => {
          const statusClass = `bed-status-${bed.status.toLowerCase()}`;
          return (
            <div 
              key={bed.id} 
              className={`bed-box ${statusClass}`}
              onClick={() => {
                if (bed.status === 'RESERVED') {
                  onConfirmInBed(bed.id);
                }
              }}
              title={bed.status === 'RESERVED' ? 'Click to confirm patient physical arrival' : `Status: ${bed.status}`}
            >
              <div className="bed-id">{bed.id.replace('BED-', '')}</div>
              <div className="bed-label">{bed.status}</div>
              {bed.has_ventilator && <span style={{ fontSize: '0.65rem' }}>🫁 Vent</span>}
            </div>
          );
        })}
      </div>

      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.5rem' }}>
        <div><span style={{ color: '#34d399' }}>●</span> Available</div>
        <div><span style={{ color: '#fbbf24' }}>●</span> Reserved (Patient In-Transit)</div>
        <div><span style={{ color: '#f87171' }}>●</span> Occupied</div>
        <div><span style={{ color: '#cbd5e1' }}>●</span> Cleaning</div>
      </div>
    </div>
  );
}
