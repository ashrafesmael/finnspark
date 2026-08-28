import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, StatusPill, Modal } from '../components/ui'
import api from '../api'

function useInvestRefs(branch) {
  const stages = useFetch(branch ? `/investment-stages/${branch.id}/` : null)
  const statuses = useFetch('/investment-statuses/')
  const tiers = useFetch('/investment-tiers/')
  const rounds = useFetch('/investment-rounds/')
  const types = useFetch('/business-types/')
  const industries = useFetch('/business-industries/')
  return { stages: stages.data || [], statuses: statuses.data || [], tiers: tiers.data || [],
           rounds: rounds.data || [], types: types.data || [], industries: industries.data || [] }
}

const refName = (list, id) => list.find((x) => x.id === id)?.name || '—'

function ApprovalLink() {
  const navigate = useNavigate()
  return <button className="btn ghost sm" onClick={() => navigate('/approval')}>Approval →</button>
}

export default function Dealflow() {
  const { branch, can } = useAuth()
  const refs = useInvestRefs(branch)
  const [stage, setStage] = useState('')
  const [page, setPage] = useState(1)
  const [tierF, setTierF] = useState('')
  const [roundF, setRoundF] = useState('')
  const [industryF, setIndustryF] = useState('')
  const [edit, setEdit] = useState(null)
  const pageSize = 12

  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (stage) qs.set('stage', stage)
  if (tierF) qs.set('tier', tierF)
  if (roundF) qs.set('round', roundF)
  if (industryF) qs.set('industry', industryF)

  const list = useFetch(branch && can('dealflow.view')
    ? `/investment/${branch.id}/dealflow/investment-cases/?${qs}` : null)

  return (
    <div>
      <div className="tabs sub-tabs">
        <button className={`tab ${stage === '' ? 'active' : ''}`} onClick={() => { setStage(''); setPage(1) }}>
          All deals
        </button>
        {refs.stages.map((s) => (
          <button key={s.id} className={`tab ${String(stage) === String(s.id) ? 'active' : ''}`}
                  onClick={() => { setStage(s.id); setPage(1) }}>{s.name}</button>
        ))}
      </div>

      <div className="filters row wrap">
        <select value={tierF} onChange={(e) => setTierF(e.target.value)}>
          <option value="">All tiers</option>
          {refs.tiers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={roundF} onChange={(e) => setRoundF(e.target.value)}>
          <option value="">All rounds</option>
          {refs.rounds.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <select value={industryF} onChange={(e) => setIndustryF(e.target.value)}>
          <option value="">All industries</option>
          {refs.industries.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
        {can('dealflow.edit') && (
          <button className="btn primary sm" onClick={() => setEdit({})}>+ Add investment case</button>
        )}
      </div>

      <DataTable
        columns={[
          { header: 'Company', key: 'company_name' },
          { header: 'Programme', render: (r) => r.program_name || '—' },
          { header: 'Round', render: (r) => r.round?.name || '—' },
          { header: 'Tier', render: (r) => r.tier?.name || '—' },
          { header: 'Stage', render: (r) => r.stage?.name || '—' },
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
          { header: 'Requested', render: (r) =>
              `${r.amount_requested?.toLocaleString()} ${r.currency}` },
          { header: '', render: () => <ApprovalLink /> },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />

      {edit !== null && (
        <CaseEditor branchId={branch.id} refs={refs} initial={edit}
                    onClose={() => setEdit(null)}
                    onSaved={() => { setEdit(null); list.reload() }} />
      )}
    </div>
  )
}

export function CaseEditor({ branchId, refs, initial, onClose, onSaved }) {
  const [f, setF] = useState({
    company_name: initial?.company_name || '',
    tier_id: '', round_id: '', type_id: '', industry_id: '',
    amount_requested: 0, currency: 'USD',
  })
  const [businessId, setBusinessId] = useState('')
  const progs = useFetch(branchId ? `/programs/${branchId}/?page_size=100` : null)
  const [progId, setProgId] = useState('')
  const bizs = useFetch(progId ? `/v2/programs/${branchId}/${progId}/businesses/?page_size=200` : null)

  const save = async () => {
    await api.post(`/investment/${branchId}/dealflow/investment-cases/`, {
      business_id: businessId ? Number(businessId) : null,
      ...Object.fromEntries(Object.entries(f).map(([k, v]) =>
        [k, ['tier_id', 'round_id', 'type_id', 'industry_id'].includes(k) ? (v ? Number(v) : null)
                                                             : v])),
    })
    onSaved()
  }

  return (
    <Modal title="New investment case" onClose={onClose}>
      <label className="stacked">Programme
        <select value={progId} onChange={(e) => setProgId(e.target.value)}>
          <option value="">Choose programme…</option>
          {(progs.data?.results || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label className="stacked">Business
        <select value={businessId} onChange={(e) => setBusinessId(e.target.value)}>
          <option value="">— manual entry —</option>
          {(bizs.data?.results || []).map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>))}
        </select>
      </label>
      <label className="stacked">Company name
        <input value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} />
      </label>
      <div className="grid-2 gap">
        <label className="stacked">Tier
          <select value={f.tier_id} onChange={(e) => setF({ ...f, tier_id: e.target.value })}>
            <option value="">—</option>
            {refs.tiers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label className="stacked">Round
          <select value={f.round_id} onChange={(e) => setF({ ...f, round_id: e.target.value })}>
            <option value="">—</option>
            {refs.rounds.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <label className="stacked">Type
          <select value={f.type_id} onChange={(e) => setF({ ...f, type_id: e.target.value })}>
            <option value="">—</option>
            {refs.types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label className="stacked">Industry
          <select value={f.industry_id} onChange={(e) => setF({ ...f, industry_id: e.target.value })}>
            <option value="">—</option>
            {refs.industries.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
        </label>
        <label className="stacked">Amount requested
          <input type="number" value={f.amount_requested}
                 onChange={(e) => setF({ ...f, amount_requested: Number(e.target.value) })} />
        </label>
        <label className="stacked">Currency
          <select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>
            {['USD', 'JOD', 'EUR'].map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
      </div>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save}
                disabled={!f.company_name && !businessId}>Create case</button>
      </div>
    </Modal>
  )
}
