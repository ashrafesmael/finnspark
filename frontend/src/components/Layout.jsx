import { Link, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Megaphone, KanbanSquare, FileInput, FolderKanban, GraduationCap,
  BookOpen, FileSignature, Workflow, Stamp, Briefcase, BarChart3, CalendarDays, Users,
  MessageSquare, UserCog, Building2, LifeBuoy, Bell, ChevronDown, LogOut,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import Logo from './Logo'
import { useAuth } from '../context/AuthContext'
import { t, getLang, setLang, LANGUAGES } from '../i18n'
import api from '../api'

const NAV = [
  { to: '/dashboard/analytics', icon: LayoutDashboard, key: 'dashboard' },
  { to: '/announcements', icon: Megaphone, key: 'announcements' },
  { to: '/selections/investment-board', icon: KanbanSquare, key: 'selections' },
  { to: '/forms', icon: FileInput, key: 'forms' },
  { to: '/programs', icon: FolderKanban, key: 'programs' },
  { to: '/courses', icon: GraduationCap, key: 'courses' },
  { to: '/library', icon: BookOpen, key: 'library' },
  { to: '/investment-forms', icon: FileSignature, key: 'investmentForms' },
  { to: '/deal-flow', icon: Workflow, key: 'dealflow' },
  { to: '/approval', icon: Stamp, key: 'approval' },
  { to: '/portfolio-management', icon: Briefcase, key: 'portfolio' },
  { to: '/reports', icon: BarChart3, key: 'reports' },
  { to: '/apps/calendar', icon: CalendarDays, key: 'calendar' },
  { to: '/directories', icon: Users, key: 'directories' },
  { to: '/apps/chat', icon: MessageSquare, key: 'chat' },
  { to: '/administration/roles-permissions/', icon: UserCog, key: 'users' },
  { to: '/administration/organizations', icon: Building2, key: 'organizations' },
  { to: '/help-center/', icon: LifeBuoy, key: 'help' },
]

function unreadCount(setUnread) {
  return api.get('/notifications/').then((r) => {
    const n = r.data.filter((x) => !x.read).length
    setUnread(n)
  }).catch(() => {})
}

export default function Layout({ children }) {
  const { user, branch, branches, switchBranch, logout } = useAuth()
  const [unread, setUnread] = useState(0)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifs, setNotifs] = useState([])
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!user) return
    const load = () => unreadCount(setUnread)
    load()
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [user])

  const openBell = async () => {
    setNotifOpen(!notifOpen)
    if (!notifOpen) {
      const r = await api.get('/notifications/')
      setNotifs(r.data.slice(0, 10))
    }
  }
  const markAllRead = async () => {
    await api.post('/notifications/read-all/')
    setUnread(0); setNotifs((n) => n.map((x) => ({ ...x, read: true })))
  }

  const changeLang = (code) => { setLang(code); window.location.reload() }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><Logo size={22} /><span className="wordmark">finn<span className="wm-accent">spark</span></span></div>
        <nav>
          {NAV.map(({ to, icon: Icon, key }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon size={17} /> <span>{t(key)}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="branch-switch">
            <Building2 size={16} />
            <select value={branch?.id || ''} onChange={(e) => {
              const b = branches.find((x) => x.id === Number(e.target.value))
              if (b) switchBranch(b)
            }}>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>{b.organization?.name} — {b.name}</option>
              ))}
            </select>
          </div>
          <div className="spacer" />
          <select className="lang-select" value={getLang()} onChange={(e) => changeLang(e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
          <button className="icon-btn bell" onClick={openBell}>
            <Bell size={18} />
            {unread > 0 && <span className="badge-dot">{unread}</span>}
          </button>
          {notifOpen && (
            <div className="notif-panel card">
              <div className="row spread">
                <b>Notifications</b>
                <button className="btn ghost sm" onClick={markAllRead}>Mark all read</button>
              </div>
              {notifs.length === 0 && <p className="muted">No notifications</p>}
              {notifs.map((n) => (
                <div key={n.id} className={`notif ${n.read ? '' : 'unseen'}`}>
                  {n.payload?.message || n.type}
                </div>
              ))}
            </div>
          )}
          <div className="avatar-menu">
            <button onClick={() => setMenuOpen(!menuOpen)} className="icon-btn">
              <span className="avatar">{(user?.first_name?.[0] || 'U').toUpperCase()}</span>
              <ChevronDown size={14} />
            </button>
            {menuOpen && (
              <div className="card menu-panel">
                <div><b>{user?.first_name} {user?.last_name}</b></div>
                <div className="muted sm">{user?.email}</div>
                <hr />
                <button className="btn ghost sm" onClick={() => { logout(); navigate('/login') }}>
                  <LogOut size={14} /> {t('logout')}
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
