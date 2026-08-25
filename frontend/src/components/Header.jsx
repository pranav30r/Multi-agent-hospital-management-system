import React, { useState, useEffect } from 'react';

export default function Header({ onOpenEmergency, onOpenIntake, onOpenAddDisease }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="header-bar">
      <div className="header-brand">
        <span className="header-logo">🏥</span>
        <div className="header-title">
          <h1>City General Hospital — Command Center</h1>
          <p>Enterprise Multi-Agent Healthcare Operations • Mode: Active Simulation</p>
        </div>
      </div>

      <div className="header-actions">
        <div style={{ textAlign: 'right', fontSize: '0.8rem', color: '#94a3b8' }}>
          <div>🟢 Live Sync</div>
          <div style={{ fontWeight: '700', color: '#f8fafc' }}>{time.toLocaleTimeString()}</div>
        </div>

        <button className="btn btn-secondary" onClick={onOpenAddDisease}>
          🦠 Add Disease
        </button>

        <button className="btn btn-primary" onClick={onOpenIntake}>
          ➕ Patient Intake
        </button>

        <button className="btn btn-danger" onClick={onOpenEmergency}>
          🆘 Declare Emergency
        </button>
      </div>
    </header>
  );
}
