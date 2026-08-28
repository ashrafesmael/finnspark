import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import Logo from '../components/Logo'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { register } = useAuth()
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const navigate = useNavigate()

  const [info, setInfo] = useState(null)
  const [error, setError] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) { setError('This invitation link is missing its token. Please ask the program team for a new link.'); return }
    axios.get(`/api/auth/invite-info?token=${encodeURIComponent(token)}`)
      .then((r) => {
        setInfo(r.data)
        setFirstName(r.data.first_name || '')
        setLastName(r.data.last_name || '')
      })
      .catch((e) => setError(e.response?.data?.detail || 'Invitation link is invalid or has expired.'))
  }, [token])

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setBusy(true)
    try {
      await register({ token, password, first_name: firstName, last_name: lastName })
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big"><Logo size={30} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        <p className="muted">Create your founder account</p>
        {error && <div className="alert">{error}</div>}
        {info ? (
          <>
            {info.business_name && <p className="muted sm">Application on file: <b>{info.business_name}</b></p>}
            <label>Email (from your invitation)
              <input value={info.email} disabled />
            </label>
            <label>First name
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} autoFocus />
            </label>
            <label>Last name
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </label>
            <label>Password (min. 8 characters)
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label>Confirm password
              <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
            <button className="btn primary" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
          </>
        ) : !error && <p className="muted">Checking your invitation…</p>}
      </form>
    </div>
  )
}
