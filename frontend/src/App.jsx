import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import SelectionBoard from './pages/SelectionBoard'
import Forms from './pages/Forms'
import Programs from './pages/Programs'
import ProgramDetail from './pages/ProgramDetail'
import Disbursements from './pages/Disbursements'
import Courses, { CourseDetail } from './pages/Courses'
import Announcements from './pages/Announcements'
import Dealflow from './pages/Dealflow'
import Approval, { Portfolio } from './pages/Approval'
import Reports from './pages/Reports'
import CalendarPage from './pages/CalendarPage'
import ChatPage from './pages/ChatPage'
import { Directories } from './pages/Directories'
import { UsersAdmin, OrganizationsAdmin, HelpCenter, PublicApply, SystemResetAdmin } from './pages/Admin'

function Shell() {
  const { user, loading } = useAuth()
  if (loading) return <p className="center pad muted">Loading…</p>
  if (!user) return (
    <Routes>
      <Route path="/apply/:formId" element={<PublicApply />} />
      <Route path="/register" element={<Register />} />
      <Route path="*" element={<Login />} />
    </Routes>
  )
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard/analytics" replace />} />
        <Route path="/apply/:formId" element={<PublicApply />} />
        <Route path="/register" element={<Navigate to="/" replace />} />
        <Route path="/dashboard/analytics" element={<Dashboard />} />
        <Route path="/announcements" element={<Announcements />} />
        <Route path="/selections/investment-board" element={<SelectionBoard />} />
        <Route path="/forms" element={<Forms />} />
        <Route path="/programs" element={<Programs />} />
        <Route path="/programs-courses/:id" element={<ProgramDetail />} />
        <Route path="/disbursements" element={<Disbursements />} />
        <Route path="/courses" element={<Courses />} />
        <Route path="/courses/view/:id" element={<CourseDetail />} />
        <Route path="/library" element={<Library />} />
        <Route path="/investment-forms" element={<InvestmentFormsPage />} />
        <Route path="/deal-flow" element={<Dealflow />} />
        <Route path="/approval" element={<Approval />} />
        <Route path="/portfolio-management" element={<Portfolio />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/apps/calendar" element={<CalendarPage />} />
        <Route path="/directories" element={<Directories />} />
        <Route path="/apps/chat" element={<ChatPage />} />
        <Route path="/administration/roles-permissions/" element={<UsersAdmin />} />
        <Route path="/administration/organizations" element={<OrganizationsAdmin />} />
        <Route path="/administration/system-maintenance" element={<SystemResetAdmin />} />
        <Route path="/help-center/" element={<HelpCenter />} />
        <Route path="*" element={<p className="muted pad">404 — page not found</p>} />
      </Routes>
    </Layout>
  )
}

import ApplicationForms from './pages/Forms'
function InvestmentFormsPage() {
  return (
    <div>
      <h2>Investment forms</h2>
      <ApplicationForms kind="investment" />
    </div>
  )
}

import Library from './pages/Library'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  )
}
