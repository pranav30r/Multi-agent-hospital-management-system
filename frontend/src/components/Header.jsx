import { useEffect, useState, useCallback } from "react";
import { getHealth } from "../api/dashboard.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useEvents } from "../context/EventContext.jsx";

function Header() {
  const [time, setTime] = useState(new Date());
  const [healthStatus, setHealthStatus] = useState(null);
  const { user, logout } = useAuth();
  const { isConnected } = useEvents();

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealthStatus(data.status);
    } catch {
      setHealthStatus("unreachable");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  const statusText = healthStatus === "healthy" ? "System Active" : healthStatus === "degraded" ? "System Degraded" : "System Unreachable";
  const statusClass = healthStatus === "healthy" ? "status-ok" : "status-error";

  return (
    <header className="header">
      <div>
        <h1>Hospital Command Center</h1>
        <p>Multi-Agent Resource Management System</p>
      </div>

      <div className="header-right">
        {user && (
          <span className="user-info">
            {user.first_name} {user.last_name} ({user.role})
          </span>
        )}

        <span className={`status ${statusClass}`}>
          {statusText}
        </span>

        <span
          className={`ws-indicator ${isConnected ? "live" : "reconnecting"}`}
          title={isConnected ? "Real-time WebSocket event stream connected" : "Reconnecting to real-time event stream..."}
        >
          {isConnected ? "● LIVE" : "○ RECONNECTING"}
        </span>

        <span className="time">
          {time.toLocaleTimeString()}
        </span>

        {user && (
          <button onClick={logout} className="logout-btn">
            Logout
          </button>
        )}
      </div>
    </header>
  );
}

export default Header;