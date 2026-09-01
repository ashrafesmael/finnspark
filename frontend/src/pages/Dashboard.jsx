import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'
import { Download, ExternalLink, Calendar, ChevronRight, Eye, CheckCircle2, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { StatTile, BarList, Modal, DataTable } from '../components/ui'
import api from '../api'

const TABS = ['Program', 'Businesses/Projects', 'Investment', 'Learning', 'Team',
              'Program Reports', 'Entrepreneur Learning Insights']
const COLORS = ['#174950', '#52bc7e', '#8cd2a9', '#1c5b63', '#e08a00', '#5c6f6c', '#2f7d51']

export default function Dashboard() {
  const { branch } = useAuth()
  const [tab, setTab] = useState(0)
  const [program, setProgram] = useState('')
  const [year, setYear] = useState('')
  const [drillDown, setDrillDown] = useState(null)

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
    { name: 'Applied', value: prog.funnel.applied, stage: 'applied' },
    { name: 'Selected', value: prog.funnel.selected, stage: 'selected' },
    { name: 'Graduated', value: prog.funnel.graduated, stage: 'graduated' },
  ], [prog])

  const handleDisbursementClick = (data) => {
    if (!data) return
    const cohort = data.activePayload?.[0]?.payload || data
    if (cohort) {
      setDrillDown({ type: 'disbursements', data: cohort })
    }
  }

  const handleFunnelClick = (data) => {
    if (!data) return
    const entry = data.activePayload?.[0]?.payload || data
    if (entry) {
      setDrillDown({ type: 'funnel', stage: entry.name, data: entry })
    }
  }

  const handleDistClick = (type, item) => {
    setDrillDown({ type: 'distribution', category: type, data: item })
  }

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
          <div className="grid-3 tiles-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <StatTile label="Graduation rate" value={`${prog.tiles.graduation_rate}%`} />
            <StatTile label="Selected businesses" value={prog.tiles.selected_businesses} />
            <StatTile label="Graduated businesses" value={prog.tiles.graduated_businesses} />
            <StatTile
              label="Total Cohort Disbursements"
              value={`$${(prog.tiles.total_disbursed || 0).toLocaleString()}`}
              sub="Across all cohorts"
            />
          </div>

          <div className="grid-2">
            <div className="card chart-card">
              <div className="row spread wrap gap">
                <h3>Funnel — Applied / Selected / Graduated</h3>
                <div className="row gap wrap">
                  {funnel.map((fn) => (
                    <button
                      key={fn.name}
                      type="button"
                      className="btn ghost sm"
                      onClick={() => setDrillDown({ type: 'funnel', stage: fn.name, data: fn })}
                      style={{ padding: '2px 7px', fontSize: '11px', cursor: 'pointer' }}
                    >
                      {fn.name} ({fn.value}) 🔍
                    </button>
                  ))}
                </div>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={funnel} style={{ cursor: 'pointer' }}>
                  <XAxis dataKey="name" /><YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar
                    dataKey="value"
                    fill="#52bc7e"
                    radius={[6, 6, 0, 0]}
                    onClick={(entry) => setDrillDown({ type: 'funnel', stage: entry.name, data: entry })}
                  >
                    {funnel.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        cursor="pointer"
                        fill={entry.name === 'Graduated' ? '#2f7d51' : entry.name === 'Selected' ? '#52bc7e' : '#174950'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card chart-card">
              <div className="row spread">
                <h3>Disbursements per Programme / Cohort</h3>
                <span className="muted sm">Click bars for batch details 🔍</span>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={prog.disbursements || []}
                  onClick={handleDisbursementClick}
                  margin={{ top: 10, right: 10, left: 20, bottom: 25 }}
                  style={{ cursor: 'pointer' }}
                >
                  <XAxis
                    dataKey="short_name"
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis
                    tickFormatter={(v) => `$${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
                  />
                  <Tooltip
                    formatter={(value, name) => [`$${Number(value).toLocaleString()}`, name]}
                    labelFormatter={(label, payload) => payload?.[0]?.payload?.name || label}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Bar dataKey="processed_amount" name="Processed" fill="#52bc7e" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="draft_amount" name="Draft / Pending" fill="#e08a00" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid-2" style={{ marginTop: '14px' }}>
            <div className="card chart-card">
              <div className="row spread">
                <h3>Gender distribution</h3>
                <span className="muted sm">Click for details</span>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={prog.distributions.gender}
                    dataKey="count"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={2}
                    style={{ cursor: 'pointer' }}
                    onClick={(entry) => handleDistClick('Gender', entry)}
                  >
                    {prog.distributions.gender.map((_, i) =>
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Legend /><Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <DistCard
              title="Stage of business"
              items={(prog.distributions.stage_of_business || []).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('Stage of business', it)}
            />
          </div>

          <div className="grid-3" style={{ marginTop: '14px' }}>
            <DistCard
              title="Industry"
              items={(prog.distributions.industry || []).slice(0, 8).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('Industry', it)}
            />
            <DistCard
              title="Age band"
              items={(prog.distributions.age || []).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('Age band', it)}
            />
            <DistCard
              title="Country"
              items={(prog.distributions.country || []).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('Country', it)}
            />
            <DistCard
              title="Province"
              items={(prog.distributions.province || []).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('Province', it)}
            />
            <DistCard
              title="District"
              items={(prog.distributions.district || []).slice(0, 10).map((x) => ({ name: x.name, value: x.count, raw: x }))}
              onClick={(it) => handleDistClick('District', it)}
            />
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

      {/* Drill-down Modals */}
      {drillDown?.type === 'disbursements' && (
        <DisbursementsDrillDownModal
          branchId={branch?.id}
          cohort={drillDown.data}
          onClose={() => setDrillDown(null)}
        />
      )}

      {drillDown?.type === 'funnel' && (
        <FunnelDrillDownModal
          branchId={branch?.id}
          stage={drillDown.stage}
          programId={program}
          onClose={() => setDrillDown(null)}
        />
      )}

      {drillDown?.type === 'distribution' && (
        <DistributionDrillDownModal
          branchId={branch?.id}
          category={drillDown.category}
          item={drillDown.data}
          programId={program}
          onClose={() => setDrillDown(null)}
        />
      )}
    </div>
  )
}

function DistCard({ title, items, onClick }) {
  return (
    <div className="card chart-card">
      <div className="row spread">
        <h3>{title}</h3>
        {onClick && items?.length > 0 && (
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => onClick(items[0])}
            style={{ padding: '2px 8px', fontSize: '11px', cursor: 'pointer' }}
            title="Click to view details"
          >
            Details 🔍
          </button>
        )}
      </div>
      <BarList items={items} onItemClick={onClick} />
    </div>
  )
}

// ---------------------------------------------------------------- Disbursements Drill Down Modal

function DisbursementsDrillDownModal({ branchId, cohort, onClose }) {
  const { data: batchesRes, loading } = useFetch(
    branchId && cohort?.program_id
      ? `/disbursements/${branchId}/?program_id=${cohort.program_id}&page=1&page_size=50`
      : null
  )
  const [selectedBatch, setSelectedBatch] = useState(null)

  const batches = batchesRes?.results || []

  const exportBatch = async (batchId, title) => {
    try {
      const res = await api.get(`/disbursements/${branchId}/${batchId}/export/`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${title || 'disbursement'}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert('Export failed: ' + err.message)
    }
  }

  return (
    <Modal title={`Disbursements Breakdown — ${cohort.name}`} onClose={onClose} wide>
      {/* Overview Cards */}
      <div className="grid-3 gap" style={{ marginBottom: '14px' }}>
        <div className="card pad">
          <span className="muted sm">Total Disbursed</span>
          <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--accent)' }}>
            ${(cohort.total_amount || 0).toLocaleString()} {cohort.currency}
          </div>
        </div>
        <div className="card pad">
          <span className="muted sm">Confirmed & Processed</span>
          <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--ok-fg)' }}>
            ${(cohort.processed_amount || 0).toLocaleString()} {cohort.currency}
          </div>
        </div>
        <div className="card pad">
          <span className="muted sm">Draft / Pending Batches</span>
          <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--warn-fg)' }}>
            ${(cohort.draft_amount || 0).toLocaleString()} {cohort.currency}
          </div>
        </div>
      </div>

      <div className="row spread" style={{ margin: '10px 0 6px' }}>
        <h4>Disbursement Batches ({batches.length})</h4>
        <Link to="/disbursements" className="btn ghost sm" onClick={onClose}>
          Open Disbursements Module <ExternalLink size={13} />
        </Link>
      </div>

      {loading ? (
        <p className="pad center muted">Loading batches for this cohort…</p>
      ) : batches.length === 0 ? (
        <div className="card pad center muted">
          No disbursement batches created yet for this cohort.
        </div>
      ) : (
        <div className="table-wrap card">
          <table>
            <thead>
              <tr>
                <th>Batch Title</th>
                <th>Payment Date</th>
                <th>Status</th>
                <th>Startups</th>
                <th>Total Payout</th>
                <th>Confirmed By</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td>
                    <b>{b.title}</b>
                    {b.notes && <div className="sm muted">{b.notes}</div>}
                  </td>
                  <td>
                    <span className="row gap sm">
                      <Calendar size={13} className="muted" />
                      {b.payment_date}
                    </span>
                  </td>
                  <td>
                    <span className={`pill ${b.status === 'processed' ? 'ok' : 'warn'}`}>
                      {b.status === 'processed' ? '✓ Processed' : 'Draft'}
                    </span>
                  </td>
                  <td>{b.items_count} startups</td>
                  <td>
                    <b>{b.total_amount?.toLocaleString()} {b.currency}</b>
                  </td>
                  <td className="sm muted">
                    {b.confirmed_by ? `${b.confirmed_by.name} (${b.confirmed_at?.slice(0, 10)})` : '—'}
                  </td>
                  <td>
                    <span className="row gap">
                      <button
                        className="btn ghost sm"
                        onClick={() => setSelectedBatch(selectedBatch === b.id ? null : b.id)}
                        title="View Startups Breakdown"
                      >
                        <Eye size={13} /> {selectedBatch === b.id ? 'Hide' : 'Details'}
                      </button>
                      <button
                        className="btn ghost sm"
                        onClick={() => exportBatch(b.id, b.title)}
                        title="Export Excel"
                      >
                        <Download size={13} />
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Expanded Single Batch Breakdown */}
      {selectedBatch && (
        <BatchItemsInlineView
          branchId={branchId}
          batchId={selectedBatch}
          onClose={() => setSelectedBatch(null)}
        />
      )}

      <div className="row end modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  )
}

function BatchItemsInlineView({ branchId, batchId, onClose }) {
  const { data: batch, loading } = useFetch(`/disbursements/${branchId}/${batchId}/`)

  if (loading || !batch) return <p className="pad center muted">Loading batch breakdown…</p>

  return (
    <div className="card pad" style={{ marginTop: '14px', background: '#fafbfd' }}>
      <div className="row spread" style={{ marginBottom: '8px' }}>
        <div>
          <b>Startup Breakdown: {batch.title}</b>
          <span className="sm muted"> ({batch.items?.length || 0} startups · Base Rate: ${batch.base_amount} {batch.currency})</span>
        </div>
        <button className="btn ghost sm" onClick={onClose}>✕</button>
      </div>
      <div className="table-wrap card" style={{ maxHeight: '240px', overflowY: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Startup</th>
              <th>Founders</th>
              <th>Payment %</th>
              <th>Disbursed ({batch.currency})</th>
              <th>Remarks</th>
            </tr>
          </thead>
          <tbody>
            {(batch.items || []).map((it) => (
              <tr key={it.id}>
                <td><b>{it.business_name}</b></td>
                <td className="sm muted">{it.founders?.map((f) => f.name).join(', ') || '—'}</td>
                <td>
                  <span className={`pill ${it.percentage === 100 ? 'ok' : it.percentage > 0 ? 'warn' : 'bad'}`}>
                    {it.percentage}%
                  </span>
                </td>
                <td><b>{it.amount?.toLocaleString()}</b></td>
                <td className="sm muted">{it.notes || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Funnel Drill Down Modal

function FunnelDrillDownModal({ branchId, stage: initialStage = 'Applied', programId, onClose }) {
  const [activeStage, setActiveStage] = useState(initialStage || 'Applied')
  const url = `/dashboard-funnel-drilldown/?branch_id=${branchId}&stage=${activeStage.toLowerCase()}${programId ? `&program=${programId}` : ''}`
  const { data: res, loading } = useFetch(branchId ? url : null)
  const rows = res?.results || []

  return (
    <Modal title={`Funnel Details — ${activeStage} (${res?.count ?? rows.length})`} onClose={onClose} wide>
      {/* Quick Switch Tabs */}
      <div className="row gap" style={{ marginBottom: '14px', borderBottom: '1px solid var(--border)', paddingBottom: '10px' }}>
        <span className="sm muted" style={{ marginRight: '6px' }}>Funnel Stage:</span>
        {['Applied', 'Selected', 'Graduated'].map((st) => (
          <button
            key={st}
            type="button"
            className={`btn sm ${activeStage === st ? 'primary' : 'ghost'}`}
            onClick={() => setActiveStage(st)}
            style={{ padding: '4px 12px' }}
          >
            {st}
          </button>
        ))}
      </div>

      <div className="row spread card pad" style={{ marginBottom: '14px', background: 'var(--accent-soft)', borderColor: 'var(--secondary)' }}>
        <div>
          <b>Funnel Stage: {activeStage}</b>
          <div className="sm muted">
            {activeStage === 'Applied' && 'All applicants who submitted initial intake applications'}
            {activeStage === 'Selected' && 'Startups accepted and currently enrolled in acceleration cohorts'}
            {activeStage === 'Graduated' && 'Startups that successfully graduated from the acceleration programme'}
          </div>
        </div>
        <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--accent-strong)' }}>
          {res?.count ?? rows.length} Startups
        </div>
      </div>

      {loading ? (
        <p className="pad center muted">Loading records…</p>
      ) : rows.length === 0 ? (
        <p className="pad center muted">No records found for this stage.</p>
      ) : (
        <div className="table-wrap card" style={{ maxHeight: '400px', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Startup / Business Name</th>
                <th>Founders / Email</th>
                <th>Cohort / Programme</th>
                <th>{activeStage === 'Applied' ? 'Intake Status' : 'Graduation Status'}</th>
                {activeStage !== 'Applied' && <th>Course Progress</th>}
                <th>Score</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id || i}>
                  <td><b>{r.business_name}</b></td>
                  <td className="sm muted">
                    {r.email ? `${r.founders?.[0] || ''} (${r.email})` : (r.founders || []).join(', ') || '—'}
                  </td>
                  <td>{r.program_name || '—'}</td>
                  <td>
                    <span className={`pill ${activeStage === 'Graduated' ? 'ok' : activeStage === 'Selected' ? 'ok' : 'warn'}`}>
                      {r.graduation_status || r.status || 'Enrolled'}
                    </span>
                  </td>
                  {activeStage !== 'Applied' && (
                    <td>
                      <span className="sm"><b>{r.course_progress ?? 0}%</b></span>
                    </td>
                  )}
                  <td><b>{r.average_score ?? '—'}</b></td>
                  <td className="sm muted">{r.created_at || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="row end modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Close</button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------- Distribution Drill Down Modal

function DistributionDrillDownModal({ branchId, category, item, programId, onClose }) {
  const catParam = encodeURIComponent(category || '')
  const valParam = encodeURIComponent(item?.name || '')
  const url = branchId && item?.name
    ? `/dashboard-drilldown/?branch_id=${branchId}&category=${catParam}&value=${valParam}${programId ? `&program=${programId}` : ''}`
    : null

  const { data: drillData, loading } = useFetch(url)
  const rows = drillData?.results || []

  return (
    <Modal title={`${category} Breakdown — ${item?.name || 'All'} (${drillData?.count ?? rows.length})`} onClose={onClose} wide>
      <div className="row spread card pad" style={{ marginBottom: '14px', background: 'var(--accent-soft)', borderColor: 'var(--secondary)' }}>
        <div>
          <b>{category}: {item?.name}</b>
          <div className="sm muted">Detailed applicant and startup records</div>
        </div>
        <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--accent-strong)' }}>
          {drillData?.count ?? rows.length} Records
        </div>
      </div>

      {loading ? (
        <p className="pad center muted">Loading detailed records…</p>
      ) : rows.length === 0 ? (
        <p className="pad center muted">No records found matching this criterion.</p>
      ) : (
        <div className="table-wrap card" style={{ maxHeight: '400px', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Startup / Applicant Name</th>
                <th>Contact / Founders</th>
                <th>Cohort / Programme</th>
                <th>Stage / Status</th>
                <th>Score</th>
                <th>Date / Age</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id || i}>
                  <td><b>{r.business_name}</b></td>
                  <td className="sm muted">
                    {r.contact_name ? `${r.contact_name} (${r.email})` : (r.founders || []).join(', ') || '—'}
                  </td>
                  <td>{r.program_name || '—'}</td>
                  <td>
                    <span className="pill ok">{r.type_name || r.status || r.graduation_status || 'Enrolled'}</span>
                  </td>
                  <td><b>{r.average_score ?? '—'}</b></td>
                  <td className="sm muted">{r.application_date || (r.age ? `Age: ${r.age}` : '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="row end modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Close</button>
      </div>
    </Modal>
  )
}

