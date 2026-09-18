import { useState } from 'react';
import { useAuth } from '../context/AuthContext.jsx';

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
    <div className="login-container">
      <div className="login-card">
        <h1>Hospital Command Center</h1>
        <p className="login-subtitle">Staff Authentication</p>

        {displayError && (
          <div className="error-message">{displayError}</div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <label>
            Staff ID
            <input
              type="text"
              value={staffId}
              onChange={(e) => setStaffId(e.target.value)}
              placeholder="DOC-001"
              disabled={submitting}
              autoFocus
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={submitting}
            />
          </label>

          <button type="submit" disabled={submitting} className="login-button">
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;
