import { useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo'
import api from '../api'

/** Open self-registration (DevX pattern): creates a PENDING account — no
 *  password yet — and emails a confirmation. An administrator then approves it. */
export default function Signup() {
  const [f, setF] = useState({ first_name: '', last_name: '', email: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.post('/auth/public-register/', f)
      setDone(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big"><Logo size={30} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        {done ? (
          <>
            <h3>Create your account</h3>
            <div className="alert" style={{ background: 'rgba(82,188,126,0.12)' }}>
              ✓ Registration received. A confirmation email has been sent — your account
              will be activated as soon as an administrator approves it, and you'll
              receive a link to set your password.
            </div>
            <Link className="btn primary" to="/login" style={{ textAlign: 'center' }}>Back to sign in</Link>
          </>
        ) : (
          <>
            <h3>Create your account</h3>
            <p className="muted sm">Register for the finnspark programme — an administrator
              will approve your account, then you'll get an email to set your password.</p>
            {error && <div className="alert">{error}</div>}
            <label>First name
              <input value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} autoFocus />
            </label>
            <label>Last name
              <input value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
            </label>
            <label>Email
              <input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required />
            </label>
            <button className="btn primary" disabled={busy || !f.email}>
              {busy ? 'Registering…' : 'Register'}
            </button>
            <p className="sm muted" style={{ textAlign: 'center', marginTop: 10 }}>
              Already have an account? <Link to="/login">Sign in</Link>
            </p>
          </>
        )}
      </form>
    </div>
  )
}
