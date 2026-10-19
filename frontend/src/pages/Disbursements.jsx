import { useState, useEffect } from 'react'
import {
  Banknote, Plus, Download, CheckCircle2, Lock, Unlock, AlertCircle,
  RefreshCw, Trash2, Eye, Calendar, DollarSign, Building2, User,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal, StatTile, StatusPill } from '../components/ui'
import api from '../api'

const CURRENCIES = ['USD', 'EUR', 'JOD']
const PERCENTAGE_PRESETS = [100, 50, 0]

export default function Disbursements() {
  const { branch, can, user } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [programFilter, setProgramFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [currencyFilter, setCurrencyFilter] = useState('')
  const pageSize = 10

  const [activeBatchId, setActiveBatchId] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)

  // Fetch summary metrics — mirrors the list filters so the headline tiles
  // follow whatever the toolbar has selected
  const summaryQuery = new URLSearchParams()
  if (search) summaryQuery.append('search', search)
  if (programFilter) summaryQuery.append('program_id', programFilter)
  if (statusFilter) summaryQuery.append('status', statusFilter)
  if (currencyFilter) summaryQuery.append('currency', currencyFilter)
  const summaryQs = summaryQuery.toString()
  const summaryRes = useFetch(branch ? `/disbursements/${branch.id}/summary/${summaryQs ? `?${summaryQs}` : ''}` : null)
  
  // Fetch programs for filter and creator
  const programsRes = useFetch(branch ? `/programs/${branch.id}/?page=1&page_size=100` : null)
  const programs = programsRes.data?.results || []

  // Fetch batches list
  const queryParams = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  })
  if (search) queryParams.append('search', search)
  if (programFilter) queryParams.append('program_id', programFilter)
  if (statusFilter) queryParams.append('status', statusFilter)
  if (currencyFilter) queryParams.append('currency', currencyFilter)

  const listRes = useFetch(branch ? `/disbursements/${branch.id}/?${queryParams.toString()}` : null)

  const reloadAll = () => {
    listRes.reload && listRes.reload()
    summaryRes.reload && summaryRes.reload()
  }

  const formatMoney = (amount, curr = 'EUR') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: curr,
      minimumFractionDigits: curr === 'JOD' ? 3 : 2,
    }).format(amount || 0)
  }

  const exportBatch = async (batchId, batchTitle, format = 'excel') => {
    try {
      const ext = format === 'csv' ? 'csv' : 'xlsx'
      const res = await api.get(`/disbursements/${branch.id}/${batchId}/export/?format=${format}`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${batchTitle || 'disbursement'}.${ext}`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert('Failed to export disbursement batch: ' + (err.response?.data?.detail || err.message))
    }
  }

  const exportAllDisbursements = async (format = 'excel') => {
    try {
      const ext = format === 'csv' ? 'csv' : 'xlsx'
      const res = await api.get(`/disbursements/${branch.id}/export/?format=${format}`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `all_cohort_disbursements_report.${ext}`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert('Failed to export all disbursements: ' + (err.response?.data?.detail || err.message))
    }
  }

  const summary = summaryRes.data || {
    total_batches: 0,
    draft_batches: 0,
    processed_batches: 0,
    totals_by_currency: { USD: 0, EUR: 0, JOD: 0 },
    pending_by_currency: { USD: 0, EUR: 0, JOD: 0 },
  }

  return (
    <div>
      <div className="row spread greeting">
        <div>
          <h2>Cohort Disbursements</h2>
          <p className="muted">
            Manage, process, and audit stipends, milestone vouchers, and loans in Base EUR and Disbursed JOD.
          </p>
        </div>
        <div className="row gap">
          <button className="btn ghost" onClick={() => exportAllDisbursements('excel')} title="Export all branch disbursements">
            <Download size={15} /> Export All (Excel)
          </button>
          <button className="btn ghost" onClick={() => exportAllDisbursements('csv')} title="Export all branch disbursements to CSV">
            <Download size={15} /> Export All (CSV)
          </button>
          {can('disbursements.create') && (
            <button className="btn primary" onClick={() => setShowCreateModal(true)}>
              <Plus size={16} /> New Disbursement Batch
            </button>
          )}
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className="card pad filters" style={{ margin: '14px 0' }}>
        <div className="row spread wrap gap">
          <div className="row gap wrap">
            <input
              placeholder="Search batches…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              style={{ width: '220px' }}
            />
            <select
              value={programFilter}
              onChange={(e) => { setProgramFilter(e.target.value); setPage(1) }}
              style={{ width: '220px' }}
            >
              <option value="">All Cohorts / Programmes</option>
              {programs.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
              style={{ width: '150px' }}
            >
              <option value="">All Statuses</option>
              <option value="draft">Draft / Pending</option>
              <option value="processed">Confirmed & Processed</option>
            </select>
            <select
              value={currencyFilter}
              onChange={(e) => { setCurrencyFilter(e.target.value); setPage(1) }}
              style={{ width: '130px' }}
            >
              <option value="">All Currencies</option>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <button className="btn ghost sm" onClick={reloadAll} title="Refresh">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI Stats */}
      <div className="grid-3 tiles-row">
        <StatTile
          label="Total Base Processed (EUR)"
          value={`€${(summary.totals_by_currency?.EUR || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${summary.processed_batches || 0} processed batches${(search || programFilter || statusFilter || currencyFilter) ? ' (filtered)' : ' across all cohorts'}`}
        />
        <StatTile
          label="Total Equivalent Disbursed (JOD)"
          value={`${((summary.jod_actual || 0) || ((summary.totals_by_currency?.JOD || 0) || ((summary.totals_by_currency?.EUR || 0) * 0.76))).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD`}
          sub={summary.jod_actual ? 'Per-batch items at their own exchange rates' : 'Disbursed at ~0.7600 JOD / EUR exchange rate'}
        />
        <StatTile
          label="Pending / Draft Batches"
          value={`${summary.draft_batches || 0}`}
          sub="Awaiting final confirmation"
        />
      </div>

      {/* Track breakdown */}
      <div className="grid-3 tiles-row" style={{ marginTop: 12 }}>
        <StatTile
          label="Track I — Grants"
          value={`€${(summary.by_track?.grant_I?.eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${(summary.by_track?.grant_I?.jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD · stipends & vouchers, not repayable`}
        />
        <StatTile
          label="Track II — Loans"
          value={`€${(summary.by_track?.loan_II?.eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${(summary.by_track?.loan_II?.jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD · repayable principal`}
        />
        <StatTile
          label="Track II — Grants"
          value={`€${(summary.by_track?.grant_II?.eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${(summary.by_track?.grant_II?.jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD · co-financing halves, not repayable`}
        />
      </div>

      {/* Batches Table */}
      <DataTable
        columns={[
          {
            header: 'Disbursement Title',
            render: (r) => (
              <div>
                <b>{r.title}</b>
                {r.notes && <div className="muted sm">{r.notes}</div>}
              </div>
            ),
          },
          {
            header: 'Cohort / Programme',
            render: (r) => r.program_name || '—',
          },
          {
            header: 'Payment Date',
            render: (r) => (
              <span className="row gap sm">
                <Calendar size={13} className="muted" />
                {r.payment_date || '—'}
              </span>
            ),
          },
          {
            header: 'Payout (EUR / JOD)',
            render: (r) => {
              const eurAmt = r.total_amount_eur != null ? r.total_amount_eur : (r.total_amount || 0)
              const rate = Number(r.effective_rate || r.exchange_rate || 0.76)
              const jodAmt = r.total_amount_jod != null ? r.total_amount_jod : (eurAmt * rate)
              return (
                <div>
                  <b style={{ color: 'var(--text)' }}>
                    €{eurAmt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </b>
                  <div className="muted sm" style={{ fontSize: '11.5px', marginTop: '1px' }}>
                    <span style={{ color: '#0284c7', fontWeight: 600 }}>
                      {jodAmt.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD
                    </span>
                    <span style={{ opacity: 0.75 }}> · @{rate.toFixed(4)}</span>
                  </div>
                </div>
              )
            },
          },
          {
            header: 'Startups',
            render: (r) => `${r.received_count ?? r.items_count} received`,
          },
          {
            header: 'Status',
            render: (r) => (
              <span className={`pill ${r.status === 'processed' ? 'ok' : 'warn'}`}>
                {r.status === 'processed' ? '✓ Processed' : 'Draft'}
              </span>
            ),
          },
          {
            header: 'Confirmed By',
            render: (r) => (
              r.confirmed_by ? (
                <span className="sm muted" title={r.confirmed_at}>
                  {r.confirmed_by.name} ({r.confirmed_at?.slice(0, 10)})
                </span>
              ) : '—'
            ),
          },
          {
            header: 'Actions',
            render: (r) => (
              <span className="row gap">
                <button
                  className="btn primary sm"
                  onClick={() => setActiveBatchId(r.id)}
                >
                  <Eye size={13} /> {r.status === 'draft' ? 'Review & Edit' : 'View Batch'}
                </button>
                <button
                  className="btn ghost sm"
                  onClick={() => exportBatch(r.id, r.title, 'excel')}
                  title="Export to Excel"
                >
                  <Download size={13} />
                </button>
                {r.status === 'draft' && can('disbursements.edit') && (
                  <button
                    className="btn ghost sm danger"
                    onClick={async () => {
                      if (confirm(`Delete draft batch "${r.title}"?`)) {
                        await api.delete(`/disbursements/${branch.id}/${r.id}/`)
                        reloadAll()
                      }
                    }}
                    title="Delete Draft"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </span>
            ),
          },
        ]}
        rows={listRes.data?.results || []}
        empty="No disbursement batches found. Click '+ New Disbursement Batch' to create one."
        footer={
          <Pager
            page={page}
            pageSize={pageSize}
            count={listRes.data?.count || 0}
            onPage={setPage}
          />
        }
      />

      {/* Modal: Create New Batch Wizard */}
      {showCreateModal && (
        <CreateBatchModal
          branchId={branch.id}
          programs={programs}
          onClose={() => setShowCreateModal(false)}
          onCreated={(newBatch) => {
            setShowCreateModal(false)
            reloadAll()
            setActiveBatchId(newBatch.id)
          }}
        />
      )}

      {/* Modal: Review & Manage Batch */}
      {activeBatchId && (
        <BatchDetailModal
          branchId={branch.id}
          batchId={activeBatchId}
          onClose={() => setActiveBatchId(null)}
          onUpdated={reloadAll}
          onExport={exportBatch}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Create Batch Modal

// ---------------------------------------------------------------- Create Batch Modal

function CreateBatchModal({ branchId, programs, onClose, onCreated }) {
  const [programId, setProgramId] = useState(programs[0]?.id || '')
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10))
  const [currency, setCurrency] = useState('EUR')
  const [disbursementCurrency, setDisbursementCurrency] = useState('JOD')
  const [exchangeRate, setExchangeRate] = useState(0.76)
  const [baseAmount, setBaseAmount] = useState(250)
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [startups, setStartups] = useState([])
  const [loadingStartups, setLoadingStartups] = useState(false)

  // Fetch businesses for selected program to preview
  useEffect(() => {
    if (!programId) {
      setStartups([])
      return
    }
    setLoadingStartups(true)
    api.get(`/v2/programs/${branchId}/${programId}/businesses/?page=1&page_size=100`)
      .then((res) => {
        const rows = res.data?.results || []
        setStartups(rows.map((b) => ({
          business_id: b.id,
          name: b.name,
          founders: b.founders || [],
          percentage: 100,
          is_included: true,
          disbursement_date: paymentDate,
          exchange_rate: exchangeRate,
          notes: '',
        })))
      })
      .catch((err) => {
        console.error('Failed to load cohort businesses', err)
      })
      .finally(() => setLoadingStartups(false))
  }, [programId, branchId])

  const handleGlobalDateChange = (newDate) => {
    setPaymentDate(newDate)
    setStartups((prev) => prev.map((s) => ({ ...s, disbursement_date: newDate })))
  }

  const handleGlobalRateChange = (newRate) => {
    setExchangeRate(newRate)
    setStartups((prev) => prev.map((s) => ({ ...s, exchange_rate: newRate })))
  }

  const setAllPercentages = (pct) => {
    setStartups((prev) => prev.map((s) => ({ ...s, percentage: pct })))
  }

  const setAllIncluded = (inc) => {
    setStartups((prev) => prev.map((s) => ({ ...s, is_included: inc })))
  }

  const updateStartup = (idx, field, value) => {
    setStartups((prev) => {
      const next = [...prev]
      next[idx] = { ...next[idx], [field]: value }
      return next
    })
  }

  // Calculate live totals in Base (EUR) and Disbursed (JOD)
  const calculatedTotalEur = startups.reduce((acc, s) => {
    if (!s.is_included) return acc
    const amt = Number(baseAmount || 0) * (Number(s.percentage || 0) / 100)
    return acc + amt
  }, 0)

  const calculatedTotalJod = startups.reduce((acc, s) => {
    if (!s.is_included) return acc
    const amtEur = Number(baseAmount || 0) * (Number(s.percentage || 0) / 100)
    const rate = Number(s.exchange_rate || exchangeRate || 0.76)
    return acc + (amtEur * rate)
  }, 0)

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!programId) {
      alert('Please select a Cohort / Programme.')
      return
    }
    setLoading(true)
    try {
      const itemsPayload = startups.map((s) => {
        const eur = Math.round(Number(baseAmount || 0) * (Number(s.percentage || 0) / 100) * 100) / 100
        const rate = Number(s.exchange_rate || exchangeRate || 0.76)
        const jod = Math.round(eur * rate * 1000) / 1000
        return {
          business_id: s.business_id,
          percentage: Number(s.percentage),
          is_included: Boolean(s.is_included),
          amount: eur,
          amount_jod: jod,
          disbursement_date: s.disbursement_date || paymentDate,
          exchange_rate: rate,
          notes: s.notes || '',
        }
      })

      const payload = {
        program_id: Number(programId),
        title: title.trim() || undefined,
        payment_date: paymentDate,
        currency,
        disbursement_currency: disbursementCurrency,
        exchange_rate: Number(exchangeRate),
        base_amount: Number(baseAmount),
        notes,
        items: itemsPayload,
      }

      const res = await api.post(`/disbursements/${branchId}/`, payload)
      onCreated(res.data)
    } catch (err) {
      alert('Failed to create disbursement batch: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="Create New Disbursement Batch" onClose={onClose} wide>
      <form onSubmit={handleCreate}>
        <div className="grid-2 gap">
          <label className="stacked">
            <b>Cohort / Programme *</b>
            <select
              value={programId}
              onChange={(e) => setProgramId(e.target.value)}
              required
            >
              <option value="">Select Programme</option>
              {programs.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>

          <label className="stacked">
            <b>Payment / Value Date *</b>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => handleGlobalDateChange(e.target.value)}
              required
            />
          </label>
        </div>

        <div className="grid-3 gap">
          <label className="stacked">
            <b>Base Currency *</b>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              required
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>

          <label className="stacked">
            <b>Disbursement Currency *</b>
            <select
              value={disbursementCurrency}
              onChange={(e) => setDisbursementCurrency(e.target.value)}
              required
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>

          <label className="stacked">
            <b>Exchange Rate (1 {currency} = X {disbursementCurrency}) *</b>
            <input
              type="number"
              step="0.0001"
              min="0.0001"
              value={exchangeRate}
              onChange={(e) => handleGlobalRateChange(e.target.value)}
              required
            />
          </label>
        </div>

        <div className="grid-2 gap">
          <label className="stacked">
            <b>Base Monthly Rate per Startup ({currency}) *</b>
            <input
              type="number"
              step="0.01"
              min="0"
              value={baseAmount}
              onChange={(e) => setBaseAmount(e.target.value)}
              required
            />
          </label>

          <label className="stacked">
            <span>Batch Title (Optional — auto-generated if left blank)</span>
            <input
              placeholder="e.g. OCIF Cohort 3 — August 2026 Monthly Disbursement"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
        </div>

        <label className="stacked" style={{ marginTop: '6px' }}>
          <span>Notes / Remarks</span>
          <input
            placeholder="e.g. Regular monthly stipend disbursed in JOD equivalent"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        <hr style={{ margin: '16px 0' }} />

        {/* Startups selection & percentage breakdown */}
        <div className="row spread wrap gap">
          <div>
            <h4>Startups in this Cohort ({startups.length})</h4>
            <p className="muted sm">
              All startups default to 100% payout. You can customize payment percentage, exact disbursement date, and FX rate per startup.
            </p>
          </div>
          <div className="row gap wrap">
            <span className="sm muted">Quick Presets:</span>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setAllPercentages(100)}
            >
              All 100%
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setAllPercentages(50)}
            >
              All 50%
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setAllPercentages(0)}
            >
              All 0%
            </button>
          </div>
        </div>

        {loadingStartups ? (
          <p className="muted center pad">Loading startups in cohort…</p>
        ) : startups.length === 0 ? (
          <div className="card pad center muted" style={{ margin: '12px 0' }}>
            No enrolled startups found in this programme.
          </div>
        ) : (
          <div className="table-wrap card" style={{ marginTop: '10px', maxHeight: '320px', overflowY: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: '38px' }}>
                    <input
                      type="checkbox"
                      checked={startups.every((s) => s.is_included)}
                      onChange={(e) => setAllIncluded(e.target.checked)}
                      title="Select / Deselect all"
                    />
                  </th>
                  <th>Startup Name</th>
                  <th>Founders</th>
                  <th>Disbursement Date</th>
                  <th>Payment %</th>
                  <th>Base ({currency})</th>
                  <th>FX Rate</th>
                  <th>Disbursed ({disbursementCurrency})</th>
                  <th>Remarks</th>
                </tr>
              </thead>
              <tbody>
                {startups.map((s, idx) => {
                  const itemEur = Number(baseAmount || 0) * (Number(s.percentage || 0) / 100)
                  const itemRate = Number(s.exchange_rate || exchangeRate || 0.76)
                  const itemJod = itemEur * itemRate

                  return (
                    <tr key={s.business_id} style={{ opacity: s.is_included ? 1 : 0.45 }}>
                      <td>
                        <input
                          type="checkbox"
                          checked={s.is_included}
                          onChange={(e) => updateStartup(idx, 'is_included', e.target.checked)}
                        />
                      </td>
                      <td>
                        <b>{s.name}</b>
                      </td>
                      <td className="sm muted">
                        {s.founders?.map((f) => `${f.first_name || ''} ${f.last_name || ''}`).join(', ') || '—'}
                      </td>
                      <td>
                        <input
                          type="date"
                          value={s.disbursement_date || paymentDate}
                          onChange={(e) => updateStartup(idx, 'disbursement_date', e.target.value)}
                          style={{ width: '130px', padding: '2px 4px', fontSize: '12px' }}
                        />
                      </td>
                      <td>
                        <div className="row gap">
                          {PERCENTAGE_PRESETS.map((p) => (
                            <button
                              key={p}
                              type="button"
                              className={`btn sm ${Number(s.percentage) === p ? 'primary' : 'ghost'}`}
                              style={{ padding: '2px 6px', fontSize: '11px' }}
                              onClick={() => updateStartup(idx, 'percentage', p)}
                            >
                              {p}%
                            </button>
                          ))}
                          <input
                            type="number"
                            min="0"
                            max="200"
                            value={s.percentage}
                            onChange={(e) => updateStartup(idx, 'percentage', e.target.value)}
                            style={{ width: '54px', padding: '3px 4px', fontSize: '12px' }}
                          />
                        </div>
                      </td>
                      <td>
                        <b>{s.is_included ? itemEur.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}</b>
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.0001"
                          min="0.0001"
                          value={s.exchange_rate || exchangeRate}
                          onChange={(e) => updateStartup(idx, 'exchange_rate', e.target.value)}
                          style={{ width: '70px', padding: '3px 4px', fontSize: '12px' }}
                        />
                      </td>
                      <td>
                        <span style={{ color: '#0284c7', fontWeight: 600 }}>
                          {s.is_included ? itemJod.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 }) : '0.000'}
                        </span>
                      </td>
                      <td>
                        <input
                          placeholder="Notes…"
                          value={s.notes}
                          onChange={(e) => updateStartup(idx, 'notes', e.target.value)}
                          style={{ minWidth: '120px', padding: '4px 6px', fontSize: '12px' }}
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Live Cohort Total Summary Banner */}
        <div className="card pad row spread" style={{ marginTop: '16px', background: 'var(--accent-soft)', borderColor: 'var(--secondary)' }}>
          <div>
            <b>Cohort Total Payment:</b>
            <div className="muted sm">
              {startups.filter((s) => s.is_included).length} of {startups.length} startups included · Rate: 1 {currency} = {Number(exchangeRate).toFixed(4)} {disbursementCurrency}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--accent-strong)' }}>
              €{calculatedTotalEur.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
            </div>
            <div style={{ fontSize: '14.5px', fontWeight: '700', color: '#0284c7' }}>
              {calculatedTotalJod.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} {disbursementCurrency}
            </div>
          </div>
        </div>

        <div className="row end gap modal-foot">
          <button type="button" className="btn ghost" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={loading || startups.length === 0}>
            {loading ? 'Creating Batch…' : 'Create Disbursement Batch'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------- Batch Detail & Review Modal

function BatchDetailModal({ branchId, batchId, onClose, onUpdated, onExport }) {
  const { can, user } = useAuth()
  const { data: batch, loading, reload } = useFetch(`/disbursements/${branchId}/${batchId}/`)
  
  const [isEditing, setIsEditing] = useState(false)
  const [items, setItems] = useState([])
  const [baseAmount, setBaseAmount] = useState(0)
  const [exchangeRate, setExchangeRate] = useState(0.76)
  const [disbursementCurrency, setDisbursementCurrency] = useState('JOD')
  const [title, setTitle] = useState('')
  const [paymentDate, setPaymentDate] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  // Sync state when batch data loads
  useEffect(() => {
    if (batch) {
      setItems((batch.items || []).map((it) => ({
        ...it,
        orig_amount: it.amount_eur != null ? it.amount_eur : (it.amount || 0),
      })))
      setBaseAmount(batch.base_amount || 0)
      setExchangeRate(batch.exchange_rate || 0.76)
      setDisbursementCurrency(batch.disbursement_currency || 'JOD')
      setTitle(batch.title || '')
      setPaymentDate(batch.payment_date || '')
      setNotes(batch.notes || '')
    }
  }, [batch])

  const isProcessed = batch?.status === 'processed'
  const isAdmin = can('disbursements.reopen') || user?.roles?.some((r) => ['branch_admin', 'organization_admin', '*'].includes(r))

  const updateItem = (idx, field, value) => {
    setItems((prev) => {
      const next = [...prev]
      next[idx] = { ...next[idx], [field]: value }
      return next
    })
  }

  const setAllPercentages = (pct) => {
    setItems((prev) => prev.map((s) => ({ ...s, percentage: pct })))
  }

  const setAllRates = (rate) => {
    setExchangeRate(rate)
    setItems((prev) => prev.map((s) => ({ ...s, exchange_rate: rate })))
  }

  const setAllDates = (d) => {
    setPaymentDate(d)
    setItems((prev) => prev.map((s) => ({ ...s, disbursement_date: d })))
  }

  const currentTotalEur = items.reduce((acc, s) => {
    if (!s.is_included) return acc
    let amt = 0
    if (isEditing) {
      if (Number(baseAmount) > 0) {
        amt = Number(baseAmount) * (Number(s.percentage || 0) / 100)
      } else {
        const itemBase = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : s.orig_amount || 0))
        amt = itemBase * (Number(s.percentage || 0) / 100)
      }
    } else {
      amt = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : 0))
    }
    return acc + amt
  }, 0)

  const currentTotalJod = items.reduce((acc, s) => {
    if (!s.is_included) return acc
    let amtEur = 0
    const rate = Number(s.exchange_rate || exchangeRate || 0.76)
    if (isEditing) {
      if (Number(baseAmount) > 0) {
        amtEur = Number(baseAmount) * (Number(s.percentage || 0) / 100)
      } else {
        const itemBase = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : s.orig_amount || 0))
        amtEur = itemBase * (Number(s.percentage || 0) / 100)
      }
      return acc + (amtEur * rate)
    } else {
      if (s.amount_jod != null) {
        return acc + Number(s.amount_jod)
      }
      amtEur = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : 0))
      return acc + (amtEur * rate)
    }
  }, 0)

  const handleSaveDraft = async () => {
    setSaving(true)
    try {
      const payload = {
        title,
        payment_date: paymentDate,
        base_amount: Number(baseAmount),
        exchange_rate: Number(exchangeRate),
        disbursement_currency: disbursementCurrency,
        notes,
        items: items.map((it) => {
          const itemBase = Number(baseAmount) > 0 ? Number(baseAmount) : Number(it.amount_eur != null ? it.amount_eur : (it.amount != null ? it.amount : it.orig_amount || 0))
          const eur = Math.round(itemBase * (Number(it.percentage) / 100) * 100) / 100
          const rate = Number(it.exchange_rate || exchangeRate || 0.76)
          const jod = Math.round(eur * rate * 1000) / 1000
          return {
            id: it.id,
            business_id: it.business_id,
            percentage: Number(it.percentage),
            is_included: Boolean(it.is_included),
            amount: eur,
            amount_jod: jod,
            disbursement_date: it.disbursement_date || paymentDate,
            exchange_rate: rate,
            notes: it.notes || '',
          }
        }),
      }
      await api.put(`/disbursements/${branchId}/${batchId}/`, payload)
      setIsEditing(false)
      reload()
      onUpdated()
    } catch (err) {
      alert('Failed to save changes: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  const handleConfirmBatch = async () => {
    const eurFormatted = `€${currentTotalEur.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    const jodFormatted = `${currentTotalJod.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD`
    const confirmMsg = `Are you sure you want to confirm and process this disbursement batch of ${eurFormatted} (${jodFormatted}) for ${batch.program_name}?\n\nOnce processed, the batch will be locked and no further changes are allowed unless an administrator reopens it.`
    if (!confirm(confirmMsg)) return

    setSaving(true)
    try {
      if (isEditing) {
        await handleSaveDraft()
      }
      await api.post(`/disbursements/${branchId}/${batchId}/confirm/`)
      reload()
      onUpdated()
    } catch (err) {
      alert('Failed to confirm batch: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  const handleReopenBatch = async () => {
    const confirmMsg = `Reopen this batch for editing?\n\nThis will return the batch to Draft status so percentages, rates, and remarks can be modified.`
    if (!confirm(confirmMsg)) return

    setSaving(true)
    try {
      await api.post(`/disbursements/${branchId}/${batchId}/reopen/`)
      reload()
      onUpdated()
    } catch (err) {
      alert('Failed to reopen batch: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  if (loading || !batch) {
    return (
      <Modal title="Disbursement Batch Details" onClose={onClose} wide>
        <p className="pad center muted">Loading batch details…</p>
      </Modal>
    )
  }

  return (
    <Modal title={batch.title} onClose={onClose} wide>
      {/* Status & Security Banner */}
      {isProcessed ? (
        <div className="card pad row spread" style={{ marginBottom: '14px', background: 'var(--ok-bg)', borderColor: 'var(--ok)' }}>
          <div className="row gap">
            <CheckCircle2 size={20} color="var(--ok)" />
            <div>
              <b style={{ color: 'var(--ok-fg)' }}>Batch Confirmed & Processed</b>
              <div className="sm muted">
                Confirmed by <b>{batch.confirmed_by?.name || 'Administrator'}</b> on {batch.confirmed_at ? new Date(batch.confirmed_at).toLocaleString() : '—'}. Locked against editing.
              </div>
            </div>
          </div>
          {isAdmin && (
            <button className="btn ghost sm" onClick={handleReopenBatch} disabled={saving}>
              <Unlock size={14} /> Reopen Batch (Admin)
            </button>
          )}
        </div>
      ) : (
        <div className="card pad row spread" style={{ marginBottom: '14px', background: 'var(--warn-bg)', borderColor: 'var(--warn)' }}>
          <div className="row gap">
            <AlertCircle size={20} color="var(--warn)" />
            <div>
              <b style={{ color: 'var(--warn-fg)' }}>Draft Status — Review Required</b>
              <div className="sm muted">
                Review and modify individual startup percentages, dates, and FX rates before confirming payment.
              </div>
            </div>
          </div>
          <div className="row gap">
            {!isEditing ? (
              <button className="btn ghost sm" onClick={() => setIsEditing(true)}>
                Edit Rates & Dates
              </button>
            ) : (
              <button className="btn primary sm" onClick={handleSaveDraft} disabled={saving}>
                Save Draft
              </button>
            )}
            <button className="btn primary sm" onClick={handleConfirmBatch} disabled={saving} style={{ background: '#35915d' }}>
              <CheckCircle2 size={14} /> Confirm & Process
            </button>
          </div>
        </div>
      )}

      {/* Meta Information Cards */}
      <div className="grid-4 gap card pad-top" style={{ padding: '14px', marginBottom: '16px' }}>
        <div>
          <span className="muted sm">Cohort / Programme</span>
          <div><b>{batch.program_name || '—'}</b></div>
        </div>
        <div>
          <span className="muted sm">Payment / Value Date</span>
          {isEditing ? (
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setAllDates(e.target.value)}
              style={{ marginTop: '3px' }}
            />
          ) : (
            <div><b>{batch.payment_date}</b></div>
          )}
        </div>
        <div>
          <span className="muted sm">Base Monthly Rate</span>
          {isEditing ? (
            <input
              type="number"
              value={baseAmount}
              onChange={(e) => setBaseAmount(e.target.value)}
              placeholder="0 for custom tranches"
              style={{ marginTop: '3px' }}
            />
          ) : (
            <div>
              <b>
                {batch.base_amount > 0
                  ? `€${batch.base_amount?.toLocaleString()} ${batch.currency}`
                  : `Custom / Blended Amounts (${batch.currency})`}
              </b>
            </div>
          )}
        </div>
        <div>
          <span className="muted sm">Exchange Rate ({batch.currency} / {batch.disbursement_currency})</span>
          {isEditing ? (
            <input
              type="number"
              step="0.0001"
              value={exchangeRate}
              onChange={(e) => setAllRates(e.target.value)}
              style={{ marginTop: '3px' }}
            />
          ) : (
            <div>
              <b>1 {batch.currency} = {Number(batch.exchange_rate || 0.76).toFixed(4)} {batch.disbursement_currency}</b>
            </div>
          )}
        </div>
      </div>

      {/* Startup Breakdown Table */}
      <div className="row spread wrap gap" style={{ marginBottom: '8px' }}>
        <h4>Disbursement Breakdown ({items.length} Startups)</h4>
        <div className="row gap wrap">
          {isEditing && (
            <>
              <span className="sm muted">Quick Presets:</span>
              <button type="button" className="btn ghost sm" onClick={() => setAllPercentages(100)}>
                All 100%
              </button>
              <button type="button" className="btn ghost sm" onClick={() => setAllPercentages(50)}>
                All 50%
              </button>
              <button type="button" className="btn ghost sm" onClick={() => setAllPercentages(0)}>
                All 0%
              </button>
            </>
          )}
          <button className="btn ghost sm" onClick={() => onExport(batch.id, batch.title, 'excel')} title="Download as Excel spreadsheet">
            <Download size={14} /> Export (Excel)
          </button>
          <button className="btn ghost sm" onClick={() => onExport(batch.id, batch.title, 'csv')} title="Download as CSV">
            <Download size={14} /> Export (CSV)
          </button>
        </div>
      </div>

      <div className="table-wrap card" style={{ maxHeight: '340px', overflowY: 'auto' }}>
        <table>
          <thead>
            <tr>
              {isEditing && <th style={{ width: '38px' }}>Inc.</th>}
              <th>Startup Name</th>
              <th>Founders</th>
              <th>Disbursement Date</th>
              <th>Payment Rate</th>
              <th>Base ({batch.currency})</th>
              <th>FX Rate</th>
              <th>Disbursed ({batch.disbursement_currency})</th>
              <th>Remarks / Notes</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s, idx) => {
              let itemAmtEur = 0
              if (isEditing) {
                if (Number(baseAmount) > 0) {
                  itemAmtEur = Number(baseAmount) * (Number(s.percentage || 0) / 100)
                } else {
                  const itemBase = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : s.orig_amount || 0))
                  itemAmtEur = itemBase * (Number(s.percentage || 0) / 100)
                }
              } else {
                itemAmtEur = Number(s.amount_eur != null ? s.amount_eur : (s.amount != null ? s.amount : 0))
              }
              const itemRate = Number(s.exchange_rate || exchangeRate || 0.76)
              const itemAmtJod = (!isEditing && s.amount_jod != null)
                ? Number(s.amount_jod)
                : (itemAmtEur * itemRate)

              return (
                <tr key={s.id || s.business_id} style={{ opacity: s.is_included ? 1 : 0.45 }}>
                  {isEditing && (
                    <td>
                      <input
                        type="checkbox"
                        checked={s.is_included}
                        onChange={(e) => updateItem(idx, 'is_included', e.target.checked)}
                      />
                    </td>
                  )}
                  <td>
                    <b>{s.business_name || s.name}</b>
                  </td>
                  <td className="sm muted">
                    {s.founders?.map((f) => f.name || `${f.first_name || ''} ${f.last_name || ''}`).join(', ') || '—'}
                  </td>
                  <td>
                    {isEditing ? (
                      <input
                        type="date"
                        value={s.disbursement_date || paymentDate}
                        onChange={(e) => updateItem(idx, 'disbursement_date', e.target.value)}
                        style={{ width: '130px', padding: '2px 4px', fontSize: '12px' }}
                      />
                    ) : (
                      <span className="sm muted">{s.disbursement_date || batch.payment_date || '—'}</span>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <div className="row gap">
                        {PERCENTAGE_PRESETS.map((p) => (
                          <button
                            key={p}
                            type="button"
                            className={`btn sm ${Number(s.percentage) === p ? 'primary' : 'ghost'}`}
                            style={{ padding: '2px 6px', fontSize: '11px' }}
                            onClick={() => updateItem(idx, 'percentage', p)}
                          >
                            {p}%
                          </button>
                        ))}
                        <input
                          type="number"
                          min="0"
                          max="200"
                          value={s.percentage}
                          onChange={(e) => updateItem(idx, 'percentage', e.target.value)}
                          style={{ width: '54px', padding: '3px 4px', fontSize: '12px' }}
                        />
                      </div>
                    ) : (
                      <span className={`pill ${s.percentage === 100 ? 'ok' : s.percentage > 0 ? 'warn' : 'bad'}`}>
                        {s.percentage}%
                      </span>
                    )}
                  </td>
                  <td>
                    {isEditing && Number(baseAmount) === 0 ? (
                      <input
                        type="number"
                        step="0.01"
                        value={s.amount_eur != null ? s.amount_eur : (s.amount || 0)}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) || 0
                          updateItem(idx, 'amount', val)
                          updateItem(idx, 'amount_eur', val)
                          updateItem(idx, 'orig_amount', val)
                        }}
                        style={{ width: '85px', padding: '3px 4px', fontSize: '12px' }}
                      />
                    ) : (
                      <b>
                        {s.is_included
                          ? `€${itemAmtEur.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : '€0.00'}
                      </b>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <input
                        type="number"
                        step="0.0001"
                        min="0.0001"
                        value={s.exchange_rate || exchangeRate}
                        onChange={(e) => updateItem(idx, 'exchange_rate', e.target.value)}
                        style={{ width: '70px', padding: '3px 4px', fontSize: '12px' }}
                      />
                    ) : (
                      <span className="sm muted">{itemRate.toFixed(4)}</span>
                    )}
                  </td>
                  <td>
                    <span style={{ color: '#0284c7', fontWeight: 600 }}>
                      {s.is_included
                        ? `${itemAmtJod.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} ${batch.disbursement_currency}`
                        : `0.000 ${batch.disbursement_currency}`}
                    </span>
                  </td>
                  <td>
                    {isEditing ? (
                      <input
                        value={s.notes || ''}
                        onChange={(e) => updateItem(idx, 'notes', e.target.value)}
                        placeholder="Remarks…"
                        style={{ minWidth: '130px', padding: '4px 6px', fontSize: '12px' }}
                      />
                    ) : (
                      <span className="sm muted">{s.notes || '—'}</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Cohort Total Summary Banner */}
      <div className="card pad row spread" style={{ marginTop: '16px', background: 'var(--accent-soft)', borderColor: 'var(--secondary)' }}>
        <div>
          <b>Total Cohort Payout:</b>
          <div className="muted sm">
            {items.filter((s) => s.is_included).length} of {items.length} startups included · Rate: 1 {batch.currency} = {Number(exchangeRate).toFixed(4)} {batch.disbursement_currency}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '22px', fontWeight: '800', color: 'var(--accent-strong)' }}>
            €{currentTotalEur.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {batch.currency}
          </div>
          <div style={{ fontSize: '15px', fontWeight: '700', color: '#0284c7' }}>
            {currentTotalJod.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} {batch.disbursement_currency}
          </div>
        </div>
      </div>

      <div className="row spread modal-foot">
        <div>
          {!isProcessed && can('disbursements.edit') && (
            <button
              type="button"
              className="btn ghost sm danger"
              onClick={async () => {
                if (confirm('Permanently delete this draft batch?')) {
                  await api.delete(`/disbursements/${branchId}/${batchId}/`)
                  onClose()
                  onUpdated()
                }
              }}
            >
              <Trash2 size={14} /> Delete Batch
            </button>
          )}
        </div>
        <div className="row gap">
          <button type="button" className="btn ghost" onClick={onClose}>
            Close
          </button>
          {!isProcessed && (
            <button
              type="button"
              className="btn primary"
              onClick={handleConfirmBatch}
              disabled={saving}
              style={{ background: '#35915d' }}
            >
              <CheckCircle2 size={16} /> Confirm & Process Batch
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}
