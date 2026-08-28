import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import api, { setAccessToken, setCurrentBranchId, currentBranchId, setRefreshFailHandler } from '../api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [branch, setBranch] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setRefreshFailHandler(() => {
      setAccessToken(null)
      setUser(null)
      setBranch(null)
      setCurrentBranchId(null)
    })
    axios.post('/auth/refresh/', {}, { withCredentials: true })
      .then((res) => {
        setAccessToken(res.data.access_token)
        return api.get('/auth/me/')
      })
      .then((res) => {
        setUser(res.data)
        const saved = localStorage.getItem('currentBranchId')
        const b = res.data.branches.find((x) => String(x.id) === saved) || res.data.branches[0]
        if (b) { setBranch(b); setCurrentBranchId(b.id) }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await axios.post('/auth/login/', { email, password }, { withCredentials: true })
    setAccessToken(res.data.access_token)
    setUser(res.data.user)
    const b = res.data.user.branches[0]
    if (b) { setBranch(b); setCurrentBranchId(b.id) }
    return res.data.user
  }, [])

  const register = useCallback(async (payload) => {
    const res = await axios.post('/auth/register', payload, { withCredentials: true })
    setAccessToken(res.data.access_token)
    setUser(res.data.user)
    const b = res.data.user.branches[0]
    if (b) { setBranch(b); setCurrentBranchId(b.id) }
    return res.data.user
  }, [])

  const switchBranch = useCallback((b) => {
    setBranch(b)
    setCurrentBranchId(b.id)
  }, [])

  const logout = useCallback(async () => {
    try { await axios.post('/auth/logout/') } catch { /* ignore */ }
    setAccessToken(null)
    setUser(null)
    setBranch(null)
    setCurrentBranchId(null)
  }, [])

  const roleCodes = branch?.roles || []
  const can = (perm) => {
    if (!roleCodes.length) return false
    if (roleCodes.includes('branch_admin') || roleCodes.includes('organization_admin')) return true
    const map = {
      investment_manager: ['dashboard.view', 'dealflow.view', 'dealflow.edit', 'approval.view',
        'approval.decide', 'portfolio.view', 'portfolio.edit', 'reports.view', 'programs.view',
        'selections.view', 'courses.view', 'announcements.view', 'calendar.view', 'chat.use'],
      mentor: ['dashboard.view', 'programs.view', 'courses.view', 'announcements.view',
        'calendar.view', 'chat.use', 'applicants.score'],
      entrepreneur: ['courses.view', 'announcements.view', 'calendar.view', 'chat.use'],
    }
    return roleCodes.some((r) => map[r]?.includes(perm))
  }

  return (
    <AuthCtx.Provider value={{ user, branch, branches: user?.branches || [], loading, login, register, logout,
                               switchBranch, can, roleCodes }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
