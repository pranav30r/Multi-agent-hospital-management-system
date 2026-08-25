import React from 'react';

export default function EmergencyQueue({ encounters = [] }) {
  const getEsiBadge = (esi) => {
    switch (esi) {
      case 1: return <span className="badge badge-esi1">ESI-1 Critical</span>;
      case 2: return <span className="badge badge-esi2">ESI-2 Emergent</span>;
      case 3: return <span className="badge badge-esi3">ESI-3 Urgent</span>;
      case 4: return <span className="badge badge-esi4">ESI-4 Less Urgent</span>;
      default: return <span className="badge badge-esi5">ESI-5 Non-Urgent</span>;
    }
  };

  return (
    <div className="panel-card">
      <div className="panel-title">
        <span>🚨 Active Emergency Queue ({encounters.length})</span>
      </div>

      {encounters.length === 0 ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: '#64748b', fontSize: '0.9rem' }}>
          No active emergency patients in queue.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Encounter ID</th>
                <th>Patient ID</th>
                <th>ESI Level</th>
                <th>Chief Complaint</th>
                <th>Vitals (SpO2 / HR / BP)</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {encounters.map(enc => (
                <tr key={enc.id}>
                  <td style={{ fontWeight: '700' }}>{enc.id}</td>
                  <td>{enc.patient_id}</td>
                  <td>{getEsiBadge(enc.esi_level)}</td>
                  <td style={{ maxWidth: '250px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {enc.chief_complaint}
                  </td>
                  <td>
                    {enc.spo2 ? `${enc.spo2}%` : '--'} / {enc.heart_rate ? `${enc.heart_rate}bpm` : '--'} / {enc.bp_systolic ? `${enc.bp_systolic}/${enc.bp_diastolic}` : '--'}
                  </td>
                  <td>
                    <span style={{ color: '#38bdf8', fontWeight: '600', fontSize: '0.8rem' }}>
                      {enc.patient_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
