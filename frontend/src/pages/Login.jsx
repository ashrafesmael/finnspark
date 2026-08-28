import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('admin@finnpact.jo')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand big"><Logo size={30} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        <p className="muted">Igniting startups — accelerator &amp; investment programme management</p>
        {error && <div className="alert">{error}</div>}
        <label>Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button className="btn primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="muted sm">Demo: admin@finnpact.jo / Admin123! · investments@finnpact.jo / Admin123!</p>
      </form>
    </div>
  )
}
