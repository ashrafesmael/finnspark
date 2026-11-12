import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Logo from '../components/Logo'
import api from '../api'
import { useAuth } from '../context/AuthContext'

/** One-stop activation screen (DevX pattern): verifies a single-use token from an
 *  admin invitation / approval email or a password-reset email, then sets the
 *  password and logs the user straight in. */
export default function SetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const navigate = useNavigate()
  const { login: _login } = useAuth()
  const [info, setInfo] = useState(null)   // { email, displayName, isReset }
  const [error, setError] = useState(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) { setError('This link is missing its token.'); return }
    api.get(`/auth/verify-token/?token=${encodeURIComponent(token)}`)
      .then((res) => setInfo(res.data))
      .catch((err) => setError(err.response?.data?.detail || 'This link is invalid or has expired.'))
  }, [token])

  const submit = async (e) => {
    e.preventDefault()
    if (password.length < 8) { setError('Password must be at least 8 characters long.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setBusy(true); setError(null)
    try {
      const res = await api.post('/auth/set-password/', { token, password })
      // auto-login: the backend issues both the access token and the refresh cookie
      if (res.data.access_token) {
        localStorage.setItem('auth_token', res.data.access_token)
        window.location.href = '/'
        return
      }
      navigate('/login')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to set password')
    } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big"><Logo size={30} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        {error && <div className="alert">{error}</div>}
        {error && !info && <Link className="btn primary" to="/login" style={{ textAlign: 'center' }}>Back to sign in</Link>}
        {info && (
          <>
            <h3>{info.isReset ? 'Choose a new password' : 'Set your password'}</h3>
            <p className="muted sm">
              {info.isReset ? 'Choose a new password for' : 'Welcome'} <b>{info.email}</b>
              {info.displayName ? ` (${info.displayName})` : ''}
            </p>
            <label>New password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus minLength={8} />
            </label>
            <label>Confirm password
              <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} />
            </label>
            <button className="btn primary" disabled={busy || password.length < 8}>
              {busy ? 'Saving…' : (info.isReset ? 'Reset password' : 'Set password & sign in')}
            </button>
          </>
        )}
      </form>
    </div>
  )
}
