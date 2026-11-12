import { useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo'
import api from '../api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      // deliberately email-agnostic: never reveals whether an account exists
      await api.post('/auth/forgot-password/', { email })
    } catch { /* the response is the same either way */ }
    setDone(true); setBusy(false)
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big"><Logo size={30} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        {done ? (
          <>
            <h3>Check your email</h3>
            <div className="alert" style={{ background: 'rgba(82,188,126,0.12)' }}>
              If an active account exists with this email address, a password reset
              link has been sent (valid for 24 hours).
            </div>
            <Link className="btn primary" to="/login" style={{ textAlign: 'center' }}>Back to sign in</Link>
          </>
        ) : (
          <>
            <h3>Forgot password</h3>
            <p className="muted sm">Enter your account email and we'll send you a link
              to choose a new password.</p>
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </label>
            <button className="btn primary" disabled={busy || !email}>
              {busy ? 'Sending…' : 'Send reset link'}
            </button>
            <p className="sm muted" style={{ textAlign: 'center', marginTop: 10 }}>
              <Link to="/login">Back to sign in</Link>
            </p>
          </>
        )}
      </form>
    </div>
  )
}
