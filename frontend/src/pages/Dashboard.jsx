import { useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { StatTile, BarList } from '../components/ui'

const TABS = ['Program', 'Businesses/Projects', 'Investment', 'Learning', 'Team',
              'Program Reports', 'Entrepreneur Learning Insights']
const COLORS = ['#174950', '#52bc7e', '#8cd2a9', '#1c5b63', '#e08a00', '#5c6f6c', '#2f7d51']

export default function Dashboard() {
  const { branch } = useAuth()
  const [tab, setTab] = useState(0)
  const [program, setProgram] = useState('')
  const [year, setYear] = useState('')

  const qs = new URLSearchParams()
  if (branch?.id) qs.set('branch_id', branch.id)
  if (program) qs.set('program', program)
  if (year) qs.set('year', year)
  const q = qs.toString()

  const { data: progList } = useFetch(branch ? '/program-list/?branch_id=' + branch.id : null)
  const { data: years } = useFetch(
    branch ? `/applicants/application-years/${branch.id}/` : null)
  const { data: prog } = useFetch(`/dashboard-program/?${q}`)
  const { data: biz } = useFetch(`/dashboard-businesses/?${q}`)

  const funnel = useMemo(() => prog && [
    { name: 'Applied', value: prog.funnel.applied },
    { name: 'Selected', value: prog.funnel.selected },
    { name: 'Graduated', value: prog.funnel.graduated },
  ], [prog])

  return (
    <div>
      <div className="greeting card">
        <h2>Welcome back 👋</h2>
        <p className="muted">Program & portfolio analytics for <b>{branch?.name}</b></p>
      </div>

      <div className="filters row">
        <select value={program} onChange={(e) => setProgram(e.target.value)}>
          <option value="">All programs</option>
          {(progList || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={year} onChange={(e) => setYear(e.target.value)}>
          <option value="">All years</option>
          {(years || []).map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>

      <div className="tabs">
        {TABS.map((name, i) => (
          <button key={name} className={`tab ${i === tab ? 'active' : ''}`}
                  onClick={() => setTab(i)}>{name}</button>
        ))}
      </div>

      {tab === 0 && prog && funnel && (
        <>
          <div className="grid-3 tiles-row">
            <StatTile label="Graduation rate" value={`${prog.tiles.graduation_rate}%`} />
            <StatTile label="Selected businesses" value={prog.tiles.selected_businesses} />
            <StatTile label="Graduated businesses" value={prog.tiles.graduated_businesses} />
          </div>
          <div className="grid-2">
            <div className="card chart-card">
              <h3>Funnel — Applied / Selected / Graduated</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={funnel}>
                  <XAxis dataKey="name" /><YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#52bc7e" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="card chart-card">
              <h3>Gender distribution</h3>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={prog.distributions.gender} dataKey="count" nameKey="name"
                       innerRadius={55} outerRadius={85} paddingAngle={2}>
                    {prog.distributions.gender.map((_, i) =>
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Legend /><Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="grid-3">
            <DistCard title="Stage of business" items={
              (prog.distributions.stage_of_business || []).map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="Industry" items={
              (prog.distributions.industry || []).slice(0, 8).map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="Age band" items={
              (prog.distributions.age || []).map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="Country" items={
              (prog.distributions.country || []).map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="Province" items={
              (prog.distributions.province || []).map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="District" items={
              (prog.distributions.district || []).slice(0, 10).map((x) => ({ name: x.name, value: x.count }))} />
          </div>
        </>
      )}

      {[1, 4, 5, 6].includes(tab) && biz && (
        <div className="grid-3">
          <StatTile label="Businesses / Projects" value={biz.businesses.total}
                    sub={`${biz.businesses.graduated} graduated`} />
          <StatTile label="Avg course progress" value={`${biz.businesses.avg_course_progress}%`} />
          <StatTile label="Avg evaluator score" value={`${biz.businesses.avg_evaluator_score}%`} />
        </div>
      )}

      {tab === 2 && biz && (
        <>
          <div className="grid-3">
            <StatTile label="Investment cases" value={biz.investment.total_cases}
                      sub={`${biz.investment.approved} approved`} />
            <StatTile label="Total invested" value={`$${biz.investment.total_invested.toLocaleString()}`} />
            <StatTile label="Learning completion" value={`${biz.learning.completion_rate}%`}
                      sub={`${biz.learning.enrollments} enrollments`} />
          </div>
          <div className="grid-2">
            <DistCard title="By stage" items={biz.investment.by_stage.map((x) => ({ name: x.name, value: x.count }))} />
            <DistCard title="By round" items={biz.investment.by_round.map((x) => ({ name: x.name, value: x.count }))} />
          </div>
        </>
      )}

      {tab === 3 && biz && (
        <div className="grid-3">
          <StatTile label="Courses" value={biz.learning.courses} />
          <StatTile label="Enrollments" value={biz.learning.enrollments} />
          <StatTile label="Completions" value={biz.learning.completions}
                    sub={`${biz.learning.completion_rate}% completion rate`} />
        </div>
      )}
    </div>
  )
}

function DistCard({ title, items }) {
  return (
    <div className="card chart-card">
      <h3>{title}</h3>
      <BarList items={items} />
    </div>
  )
}
