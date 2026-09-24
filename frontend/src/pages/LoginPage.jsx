import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

export default function LoginPage({ onAuthenticated }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api(`/auth/login`, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      onAuthenticated(result.user);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-mark">A</div>
        <p className="eyebrow">Ask My Docs</p>
        <h1>Welcome Back</h1>
        <p className="muted">Sign in to your account.</p>
        
        <form onSubmit={submit} className="stack" style={{ marginTop: '2rem' }}>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" required /></label>
          {error && <p className="error">{error}</p>}
          <button className="primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <p className="muted">Don't have an account? <Link to="/register">Create one</Link></p>
        </div>
      </section>
    </main>
  );
}
