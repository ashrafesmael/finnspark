import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, StatusPill, Modal } from '../components/ui'
import api from '../api'

export default function Approval() {
  const { branch, can } = useAuth()
  const [committee, setCommittee] = useState('')
  const [page, setPage] = useState(1)
  const [decideCase, setDecideCase] = useState(null)
  const pageSize = 12
  const { data: committees } = useFetch(branch ? `/committee-levels/${branch.id}/` : null)

  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (committee) qs.set('committee', committee)
  const list = useFetch(branch && can('approval.view')
    ? `/investment/${branch.id}/approval/investment-cases/?${qs}` : null)

  return (
    <div>
      <div className="tabs sub-tabs">
        <button className={`tab ${committee === '' ? 'active' : ''}`}
                onClick={() => { setCommittee(''); setPage(1) }}>All deals</button>
        {(committees || []).map((c) => (
          <button key={c.id} className={`tab ${String(committee) === String(c.id) ? 'active' : ''}`}
                  onClick={() => { setCommittee(c.id); setPage(1) }}>{c.name}</button>
        ))}
      </div>
      <DataTable
        columns={[
          { header: 'Company', key: 'company_name' },
          { header: 'Round', render: (r) => r.round?.name || '—' },
          { header: 'Tier', render: (r) => r.tier?.name || '—' },
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
          { header: 'Requested', render: (r) => `${r.amount_requested?.toLocaleString()} ${r.currency}` },
          { header: '', render: (r) => can('approval.decide') && (
            <button className="btn primary sm" onClick={() => setDecideCase(r)}>Decide</button>
          )},
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />
      {decideCase && (
        <DecisionModal branchId={branch.id} caseRow={decideCase}
                       onClose={() => setDecideCase(null)}
                       onDone={() => { setDecideCase(null); list.reload() }} />
      )}
    </div>
  )
}

function DecisionModal({ branchId, caseRow, onClose, onDone }) {
  const { data: levels } = useFetch(`/committee-levels/${branchId}/`)
  const [level, setLevel] = useState('')
  const [decision, setDecision] = useState('approved')
  const [notes, setNotes] = useState('')
  return (
    <Modal title={`Committee decision — ${caseRow.company_name}`} onClose={onClose}>
      <label className="stacked">Committee level
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">Choose…</option>
          {(levels || []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </label>
      <label className="stacked">Decision
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="approved">Approved</option>
          <option value="revision">Send back for revision</option>
          <option value="rejected">Rejected</option>
        </select>
      </label>
      <label className="stacked">Notes<textarea rows={3} value={notes}
                                                 onChange={(e) => setNotes(e.target.value)} /></label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!level} onClick={async () => {
          await api.post(`/investment/${branchId}/approval/${caseRow.id}/decide/`,
                         { committee_level_id: Number(level), decision, notes })
          onDone()
        }}>Submit decision</button>
      </div>
    </Modal>
  )
}

export function Portfolio() {
  const { branch, can } = useAuth()
  const [typeF, setTypeF] = useState('')
  const [detail, setDetail] = useState(null)
  const pageSize = 12
  const { data: types } = useFetch('/business-types/')
  const qs = typeF ? `?page=1&page_size=${pageSize}&type=${typeF}` :
                     `?page=1&page_size=${pageSize}`
  const list = useFetch(branch && can('portfolio.view')
    ? `/investment/${branch.id}/portfolio_management/investment-cases/${qs}` : null)

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Portfolio companies</h3>
        <select value={typeF} onChange={(e) => setTypeF(e.target.value)}>
          <option value="">All types</option>
          {(types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>
      <DataTable
        columns={[
          { header: 'Company', key: 'company_name' },
          { header: 'Invested', render: (r) =>
              `${(r.investment_amount || 0).toLocaleString()} ${r.currency}` },
          { header: 'Co-financing', render: (r) =>
              `${(r.co_financing_amount || 0).toLocaleString()} ${r.currency}` },
          { header: 'Equity %', render: (r) => r.equity_offered_pct ?? '—' },
          { header: '', render: (r) => (
            <span className="row gap">
              <button className="btn ghost sm" onClick={() => setDetail(r)}>Financials</button>
            </span>
          )},
        ]}
        rows={list.data?.results || []}
      />
      {detail && <PortfolioDetailModal branchId={branch.id} row={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

function PortfolioDetailModal({ branchId, row, onClose }) {
  const detail = useFetch(branchId ? `/investment/${branchId}/dealflow/investment-cases/${row.id}/` : null)
  const d = detail.data
  const [timeline, setTimeline] = useState({ entry_date: '', label: '', amount: 0, direction: 'in' })
  const [payment, setPayment] = useState({ due_date: '', amount: 0 })

  if (!d) return null
  return (
    <Modal title={`${d.company_name} — financials`} onClose={onClose} wide>
      <div className="grid-2 gap">
        <div>
          <h4>Finance timeline</h4>
          <table className="kv"><tbody>
            {d.timeline_entries.map((e) => (
              <tr key={e.id}><th>{e.entry_date} · {e.label}</th>
                  <td>{e.direction === 'in' ? '+' : '−'}{Number(e.amount).toLocaleString()}</td></tr>
            ))}
          </tbody></table>
          {can_edit() && (
            <div className="row gap">
              <input type="date" value={timeline.entry_date}
                     onChange={(e) => setTimeline({ ...timeline, entry_date: e.target.value })} />
              <input placeholder="Label" style={{ width: 120 }} value={timeline.label}
                     onChange={(e) => setTimeline({ ...timeline, label: e.target.value })} />
              <input type="number" style={{ width: 100 }} value={timeline.amount}
                     onChange={(e) => setTimeline({ ...timeline, amount: Number(e.target.value) })} />
              <select value={timeline.direction}
                      onChange={(e) => setTimeline({ ...timeline, direction: e.target.value })}>
                <option value="in">in</option><option value="out">out</option>
              </select>
              <button className="btn primary sm" onClick={async () => {
                await api.post(`/investment/${branchId}/${d.id}/timeline/`, timeline)
                detail.reload()
              }}>Add</button>
            </div>
          )}

          <h4>Payments schedule</h4>
          <table className="kv"><tbody>
            {d.payments.map((p) => (
              <tr key={p.id}><th>{p.due_date}</th>
                  <td>{Number(p.amount).toLocaleString()} — {p.paid ? 'paid ✓' : 'due'}</td></tr>
            ))}
          </tbody></table>
          <div className="row gap">
            <input type="date" value={payment.due_date}
                   onChange={(e) => setPayment({ ...payment, due_date: e.target.value })} />
            <input type="number" style={{ width: 110 }} value={payment.amount}
                   onChange={(e) => setPayment({ ...payment, amount: Number(e.target.value) })} />
            <button className="btn primary sm" onClick={async () => {
              await api.post(`/investment/${branchId}/${d.id}/payments/`, payment)
              detail.reload()
            }}>Add payment</button>
          </div>
        </div>

        <div>
          <h4>Investment overview</h4>
          <table className="kv"><tbody>
            <tr><th>Investment amount</th><td>{Number(d.investment_amount).toLocaleString()} {d.currency}</td></tr>
            <tr><th>Co-financing</th><td>{Number(d.co_financing_amount).toLocaleString()}</td></tr>
            <tr><th>Equity offered</th><td>{d.equity_offered_pct}%</td></tr>
            <tr><th>Collateral</th><td>{d.collateral_description || '—'}</td></tr>
            <tr><th>Sustainability</th><td>{d.sustainability_notes || '—'}</td></tr>
            <tr><th>Innovation</th><td>{d.innovation_notes || '—'}</td></tr>
            <tr><th>Technical assistance</th><td>{d.technical_assistance_request || '—'}</td></tr>
          </tbody></table>
          <h4>Committee decisions</h4>
          {(d.decisions || []).map((x) => (
            <div key={x.id} className="chip-row">
              {x.committee_level.name}: <b>{x.decision}</b> · {x.notes}
            </div>
          ))}
        </div>
      </div>
      <div className="row end modal-foot">
        <button className="btn ghost" onClick={onClose}>Close</button>
      </div>
    </Modal>
  )

  function can_edit() { return true }
}
