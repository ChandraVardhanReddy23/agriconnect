import React, { useState } from 'react';
import { api } from '../api';

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'farmer', location: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try { onLogin(await api(`/auth/${mode === 'login' ? 'login' : 'signup'}`, { method: 'POST', body: JSON.stringify(form) })); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return <main className="auth-shell">
    <section className="auth-card">
      <div className="brand-mark">🌱</div>
      <h1>AgriConnect</h1>
      <p className="muted">Fair prices. Fresh produce. Stronger farms.</p>
      <div className="tabs"><button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Log in</button><button className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Create account</button></div>
      <form onSubmit={submit}>
        {mode === 'signup' && <input name="name" placeholder="Full name / business" value={form.name} onChange={change} required />}
        <input name="email" type="email" autoComplete="email" placeholder="Email" value={form.email} onChange={change} required />
        <input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="Password" value={form.password} onChange={change} required />
        {mode === 'signup' && <><select name="role" value={form.role} onChange={change}><option value="farmer">I am a farmer</option><option value="buyer">I am a buyer</option></select><input name="location" placeholder="City / district" value={form.location} onChange={change} /></>}
        {error && <div className="error">{error}</div>}
        <button className="primary wide" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Enter AgriConnect' : 'Join AgriConnect'}</button>
      </form>
      <p className="hint">Try demo: ravi@agri.demo / ravi123 or freshmart@agri.demo / fresh123</p>
    </section>
  </main>;
}
