import { useState } from 'react'
import { Download } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, BarList } from '../components/ui'
import api from '../api'

const SECTIONS = ['overview', 'financial-timeline', 'investment-metrics', 'collateral-overview',
  'ceo-profile', 'business-details', 'co-financing-summary', 'financial-indicators',
  'sustainability', 'equity-overview', 'requested-technical-assistance']
const TABS = ['Detailed information', 'Portfolio snapshot', 'Payments schedule', 'Aging analysis', 'Forex']

export default function Reports() {
  const { branch } = useAuth()
  const [tab, setTab] = useState(0)
  return (
    <div>
      <h2>Investment reporting pack</h2>
      <div className="tabs">
        {TABS.map((name, i) => (
          <button key={name} className={`tab ${tab === i ? 'active' : ''}`}
                  onClick={() => setTab(i)}>{name}</button>
        ))}
      </div>
      {tab === 0 && <DetailedInfo branchId={branch?.id} />}
      {tab === 1 && <Snapshot branchId={branch?.id} />}
      {tab === 2 && <Payments branchId={branch?.id} />}
      {tab === 3 && <Aging branchId={branch?.id} />}
      {tab === 4 && <ForexTab branchId={branch?.id} />}
    </div>
  )
}

function DetailedInfo({ branchId }) {
  const [section, setSection] = useState('overview')
  const [page, setPage] = useState(1)
  const rep = useFetch(branchId
    ? `/branch/${branchId}/reports/detailed-info/${section}/?page=${page}&page_size=15` : null)
  const d = rep.data

  async function exportSection() {
    const res = await api.get(
      `/branch/${branchId}/reports/detailed-info/${section}/export/`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${section}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="tabs sub-tabs wrap">
        {SECTIONS.map((s) => (
          <button key={s} className={`tab ${s === section ? 'active' : ''}`}
                  onClick={() => { setSection(s); setPage(1) }}>
            {s.replaceAll('-', ' ')}
          </button>
        ))}
      </div>
      <div className="toolbar row end">
        <button className="btn ghost sm" onClick={exportSection}>
          <Download size={14} /> Export to Excel
        </button>
      </div>
      {d && (
        <DataTable
          columns={d.headers.map((h) => ({ header: h, key: h }))}
          rows={d.results}
          footer={<Pager page={page} pageSize={15} count={d.count} onPage={setPage} />}
        />
      )}
    </>
  )
}

function Snapshot({ branchId }) {
  const snap = useFetch(branchId ? `/branch/${branchId}/reports/portfolio-snapshot/` : null)
  if (!snap.data) return null
  const s = snap.data
  return (
    <div>
      <div className="grid-3">
        <div className="card stat-tile"><div className="stat-value">{s.companies}</div>
          <div className="stat-label">Portfolio companies</div></div>
        <div className="card stat-tile"><div className="stat-value">
          ${s.total_invested.toLocaleString()}</div>
          <div className="stat-label">Total invested</div></div>
        <div className="card stat-tile"><div className="stat-value">
          ${s.avg_ticket.toLocaleString()}</div>
          <div className="stat-label">Average ticket</div></div>
      </div>
      <div className="card chart-card pad">
        <h3>Invested by industry</h3>
        <BarList items={s.by_industry.map((x) => ({ name: x.name,
                                                      value: Math.round(x.invested / 1000) }))} />
      </div>
    </div>
  )
}

function Payments({ branchId }) {
  const rep = useFetch(branchId ? `/branch/${branchId}/reports/payments-schedule/` : null)
  if (!rep.data) return null
  const cls = (s) => (s === 'paid' ? 'pill ok' : s === 'overdue' ? 'pill bad' : 'pill warn')
  return (
    <DataTable
      columns={[
        { header: 'Company', key: 'company' },
        { header: 'Due date', key: 'due_date' },
        { header: 'Amount', render: (r) => Number(r.amount).toLocaleString() },
        { header: 'Status', render: (r) => <span className={cls(r.status)}>{r.status}</span> },
      ]}
      rows={rep.data.results}
    />
  )
}

function Aging({ branchId }) {
  const rep = useFetch(branchId ? `/branch/${branchId}/reports/aging-analysis/` : null)
  if (!rep.data) return null
  return (
    <div className="card chart-card pad">
      <h3>Outstanding by aging bucket</h3>
      <BarList items={rep.data.map((x) => ({ name: x.bucket,
                                             value: Math.round(x.outstanding / 1000) }))} color="#d92d20" />
      <p className="muted sm">Values in $K</p>
    </div>
  )
}

function ForexTab({ branchId }) {
  const rep = useFetch(branchId ? `/branch/${branchId}/reports/forex/` : null)
  if (!rep.data) return null
  return (
    <DataTable
      columns={[
        { header: 'Company', key: 'company' },
        { header: 'Currency', key: 'currency' },
        { header: 'FX rate → USD', key: 'rate' },
        { header: 'Invested (USD)', render: (r) => r.invested_usd.toLocaleString() },
        { header: 'Requested (local)', render: (r) => r.requested_local.toLocaleString() },
      ]}
      rows={rep.data.results}
    />
  )
}
