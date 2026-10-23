import { useState } from 'react';
import { useAuth } from '../context/AuthContext.jsx';
import { Icon } from './common/Icon.jsx';

function Login() {
  const { login, error: authError } = useAuth();
  const [staffId, setStaffId] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!staffId || !password) {
      setLocalError('Staff ID and password are required');
      return;
    }
    setLocalError(null);
    setSubmitting(true);
    try {
      await login(staffId.trim(), password);
    } catch (err) {
      setLocalError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const displayError = localError || authError;

  return (
    <div className="login-screen">
      <div className="login-panel">
        <div className="login-brand">
          <div className="brand-logo large">
            <Icon name="shield" size={32} color="#ffffff" />
          </div>
          <h2>CITY HOSPITAL</h2>
          <p className="login-subtitle">Multi-Agent Resource Management & Clinical Triage</p>
        </div>

        {displayError && (
          <div className="alert-banner alert-error" role="alert">
            <Icon name="alert-triangle" size={16} />
            <span>{displayError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="login_staff_id">Staff Identifier</label>
            <input
              id="login_staff_id"
              type="text"
              className="form-input"
              value={staffId}
              onChange={(e) => setStaffId(e.target.value)}
              placeholder="e.g. ADM-001 or DOC-001"
              disabled={submitting}
              autoFocus
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="login_password">Access Password</label>
            <input
              id="login_password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter institutional password"
              disabled={submitting}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={submitting}
          >
            {submitting ? "Authenticating Session..." : "Sign In to Operations Portal"}
          </button>
        </form>

      </div>
    </div>
  );
}

export default Login;
