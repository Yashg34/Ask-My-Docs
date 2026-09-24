import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const navigate = useNavigate();

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      await api(`/auth/register`, {
        method: 'POST',
        body: JSON.stringify({ name, email, password }),
      });
      setSuccess('Account created. Redirecting to sign in...');
      setTimeout(() => navigate('/login'), 2000);
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
        <h1>Create an Account</h1>
        <p className="muted">Upload a PDF and get grounded answers with citations in seconds.</p>
        
        <form onSubmit={submit} className="stack" style={{ marginTop: '2rem' }}>
          <label>Name<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your Name" required /></label>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" required /></label>
          {error && <p className="error">{error}</p>}
          {success && <p className="notice">{success}</p>}
          <button className="primary full" disabled={busy}>{busy ? 'Please wait…' : 'Create account'}</button>
        </form>
        <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <p className="muted">Already have an account? <Link to="/login">Sign in</Link></p>
        </div>
      </section>
    </main>
  );
}
