import { useState, useMemo } from 'react'
import {
  Receipt, Plus, Download, Upload, CheckCircle2, Clock, XCircle,
  FileText, Search, Building2, User, DollarSign, Lock,
  TrendingUp, CreditCard, Calendar, ChevronRight, AlertCircle, Edit, Trash2,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import api from '../api'
import { DataTable, Pager, Modal, StatTile } from '../components/ui'

function MoneyTile({ label, eur, jod, sub }) {
  const fE = (v) => `€${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
  const fJ = (v) => `${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 0 })} JOD`
  return (
    <div className="card stat-tile money-tile">
      <div className="stat-label">{label}</div>
      <div className="money-pair">
        <span className="stat-value">{fE(eur)}</span>
        <span className="money-jod">{fJ(jod)}</span>
      </div>
      {sub && <div className="muted xs">{sub}</div>}
    </div>
  )
}

export default function LoanRepayments() {
  const { branch, user } = useAuth()
  const branchId = branch?.id || user?.branch_id || 1

  const [activeTab, setActiveTab] = useState('ledger') // 'ledger' | 'borrowers' | 'batches'
  const [page, setPage] = useState(1)
  const pageSize = 15
  const [search, setSearch] = useState('')
  const [selectedProgram, setSelectedProgram] = useState('')
  const [selectedStartup, setSelectedStartup] = useState('')
  const [selectedMethod, setSelectedMethod] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')

  // Modals state
  const [showRecordModal, setShowRecordModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showStatementModal, setShowStatementModal] = useState(false)
  const [selectedBusinessId, setSelectedBusinessId] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [editingRepayment, setEditingRepayment] = useState(null)

  // API endpoints
  const filterParams = new URLSearchParams()
  if (selectedProgram) filterParams.set('program_id', selectedProgram)
  if (selectedStartup) filterParams.set('business_id', selectedStartup)
  const filterQs = filterParams.toString()
  const summaryUrl = branchId ? `/repayments/${branchId}/summary/${filterQs ? `?${filterQs}` : ''}` : null
  const overviewUrl = branchId ? `/repayments/${branchId}/loans-overview/${filterQs ? `?${filterQs}` : ''}` : null
  const programsUrl = branchId ? `/programs/${branchId}/?page=1&page_size={100}` : null
  const batchesUrl = branchId ? `/repayments/${branchId}/batches/` : null

  const ledgerQueryParams = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
    ...(search && { search }),
    ...(selectedProgram && { program_id: selectedProgram }),
    ...(selectedStartup && { business_id: selectedStartup }),
    ...(selectedMethod && { payment_method: selectedMethod }),
    ...(selectedStatus && { status: selectedStatus }),
  }).toString()

  const ledgerUrl = branchId ? `/repayments/${branchId}/?${ledgerQueryParams}` : null

  const summaryRes = useFetch(summaryUrl)
  const overviewRes = useFetch(overviewUrl)
  const ledgerRes = useFetch(ledgerUrl)
  const programsRes = useFetch(programsUrl)
  const batchesRes = useFetch(batchesUrl)

  const summary = summaryRes.data || {
    total_approved_eur: 0,
    total_approved_jod: 0,
    total_repaid_eur: 0,
    total_repaid_jod: 0,
    outstanding_eur: 0,
    outstanding_jod: 0,
    recovery_rate_pct: 0,
    total_repayments_count: 0,
    active_borrowers_count: 0,
  }

  const programs = programsRes.data?.results || []
  const repaymentsList = ledgerRes.data?.results || []
  const totalCount = ledgerRes.data?.count || 0
  const borrowers = overviewRes.data?.results || []
  const batches = batchesRes.data?.results || []

  const reloadAll = () => {
    ledgerRes.reload && ledgerRes.reload()
    summaryRes.reload && summaryRes.reload()
    overviewRes.reload && overviewRes.reload()
    batchesRes.reload && batchesRes.reload()
  }

  // Handle Export
  const handleExport = async (format) => {
    try {
      const ext = format === 'csv' ? 'csv' : 'xlsx'
      const res = await api.get(`/repayments/${branchId}/export/?format=${format}`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `loan_repayments_${branchId}_${new Date().toISOString().split('T')[0]}.${ext}`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert('Failed to export repayments: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div className="stack-lg">
      {/* Header */}
      <div className="card pad row spread wrap gap">
        <div>
          <div className="row gap">
            <div className="page-ic">
              <Receipt size={24} />
            </div>
            <div>
              <h2 style={{margin: 0}}>Loan Repayments &amp; Recoveries</h2>
              <p className="muted sm">
                Track startup loan repayments, record payment receipts, and monitor loan balance recovery schedules.
              </p>
            </div>
          </div>
        </div>

        <div className="row gap wrap">
          <div className="btn-group">
            <button
              onClick={() => handleExport('excel')}
              className="btn ghost sm"
            >
              <Download size={14} /> Export Excel
            </button>
            <button
              onClick={() => handleExport('csv')}
              className="btn ghost sm"
            >
              <FileText size={14} /> CSV
            </button>
          </div>

          <button
            onClick={() => setShowImportModal(true)}
            className="btn ghost"
          >
            <Upload size={16} /> Import Excel
          </button>

          <button
            onClick={() => { setSelectedBusinessId(null); setShowRecordModal(true); }}
            className="btn primary"
          >
            <Plus size={16} /> Record Payment
          </button>
        </div>
      </div>

      {/* KPI Stats Section */}
      <div className="tiles-row grid-4">
        <MoneyTile
          label="Loans Approved (EUR) / Disbursed (JOD)"
          eur={summary.total_approved_eur}
          jod={summary.total_disbursed_jod}
          sub={`approved per grant letters · disbursed in JOD at each loan's rate`}
        />
        <MoneyTile
          label="Collected to Date"
          eur={summary.total_repaid_eur}
          jod={summary.total_repaid_jod}
          sub={`principal ${(summary.principal_collected_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 0 })} · interest/fees ${(summary.charges_collected_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 0 })} (EUR)`}
        />
        <MoneyTile
          label="Outstanding — Principal"
          eur={summary.outstanding_principal_eur}
          jod={summary.outstanding_principal_jod}
          sub={`principal disbursed not yet repaid (${summary.recovery_rate_pct || 0}% recovered)`}
        />
        <MoneyTile
          label="Outstanding — Incl. Interest/Fees"
          eur={summary.outstanding_incl_charges_eur}
          jod={summary.outstanding_incl_charges_jod}
          sub={`full repayable per schedule: principal + remaining interest/fees`}
        />
        <StatTile
          label="Active Borrowers & Payments"
          value={`${summary.active_borrowers_count || 0} Startups`}
          sub={`${summary.total_repayments_count || 0} recorded payment transactions`}
        />
      </div>

      {/* Main Navigation Tabs */}
      <div className="tabs">
        <button
          onClick={() => setActiveTab('ledger')}
          className={`tab ${activeTab === "ledger" ? "active" : ""}`}
        >
          Repayment Ledger ({totalCount})
        </button>
        <button
          onClick={() => setActiveTab('borrowers')}
          className={`tab ${activeTab === "borrowers" ? "active" : ""}`}
        >
          Borrowers & Loan Accounts ({borrowers.length})
        </button>
        <button
          onClick={() => setActiveTab('batches')}
          className={`tab ${activeTab === "batches" ? "active" : ""}`}
        >
          Monthly Batches ({batches.length})
        </button>
      </div>

      {/* TAB 3: MONTHLY BATCHES */}
      {activeTab === 'batches' && (
        <BatchesTab branchId={branchId} batches={batches} reload={() => batchesRes.reload && batchesRes.reload()} onChanged={reloadAll} />
      )}

      {/* TAB 1: REPAYMENT LEDGER */}
      {activeTab === 'ledger' && (
        <div className="stack">
          {/* Filter Toolbar */}
          <div className="filters card row spread wrap gap">
            <div className="search-box grow">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search by startup, reference #, notes…"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                className="search-input"
              />
            </div>

            <div className="row gap wrap">
              <select
                value={selectedStartup}
                onChange={(e) => { setSelectedStartup(e.target.value); setPage(1); }}
                className="filter-select"
              >
                <option value="">All Startups</option>
                {borrowers.map((b) => (
                  <option key={b.business_id} value={b.business_id}>
                    {b.company_name_en || b.company_name}
                  </option>
                ))}
              </select>
              <select
                value={selectedProgram}
                onChange={(e) => { setSelectedProgram(e.target.value); setPage(1); }}
                className="filter-select"
              >
                <option value="">All Cohorts / Programs</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>

              <select
                value={selectedMethod}
                onChange={(e) => { setSelectedMethod(e.target.value); setPage(1); }}
                className="filter-select"
              >
                <option value="">All Payment Methods</option>
                <option value="Bank Transfer">Bank Transfer</option>
                <option value="Cheque">Cheque</option>
                <option value="Cash">Cash</option>
                <option value="Deposit Slip">Deposit Slip</option>
                <option value="Mobile Wallet">Mobile Wallet</option>
                <option value="Other">Other</option>
              </select>

              <select
                value={selectedStatus}
                onChange={(e) => { setSelectedStatus(e.target.value); setPage(1); }}
                className="filter-select"
              >
                <option value="">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="pending">Pending</option>
                <option value="cancelled">Cancelled</option>
              </select>
              {(selectedStartup || selectedProgram || selectedMethod || selectedStatus || search) && (
                <button className="btn ghost sm" onClick={() => {
                  setSelectedStartup(''); setSelectedProgram(''); setSelectedMethod('')
                  setSelectedStatus(''); setSearch(''); setPage(1)
                }}>
                  Clear filters
                </button>
              )}
            </div>
          </div>

          {/* Transactions Table */}
          <div className="table-wrap card">
            <DataTable
              columns={[
                {
                  header: 'Payment Date',
                  render: (r) => (
                    <div className="row gap sm nowrap">
                      <Calendar size={14} />
                      {r.payment_date || '—'}
                    </div>
                  ),
                },
                {
                  header: 'Startup / Borrower',
                  render: (r) => (
                    <div className="name-stack">
                      <button
                        onClick={() => { setSelectedBusinessId(r.business_id); setShowStatementModal(true); }}
                        className="link-strong"
                      >
                        {r.business_name_en || r.business_name}
                      </button>
                      {r.entrepreneur && (
                        <span className="muted xs nowrap" title={r.entrepreneur}>
                          Entrepreneur: {r.entrepreneur}
                        </span>
                      )}
                    </div>
                  ),
                },
                {
                  header: 'Cohort',
                  render: (r) => <span className="muted xs">{r.program_name || '—'}</span>,
                },
                {
                  header: 'Base Amount (EUR)',
                  render: (r) => (
                    <span className="strong">
                      €{(r.amount_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </span>
                  ),
                },
                {
                  header: 'JOD Equivalent',
                  render: (r) => (
                    <div>
                      <span className="ok-text" style={{display: "block", fontWeight: 600}}>
                        {(r.amount_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                      <span className="muted xs">Rate: {r.exchange_rate}</span>
                    </div>
                  ),
                },
                {
                  header: 'Method & Ref',
                  render: (r) => (
                    <div className="sm">
                      <span className="sm" style={{display:"block"}}>{r.payment_method}</span>
                      <span className="muted xs mono">{r.reference_number || 'No Ref'}</span>
                    </div>
                  ),
                },
                {
                  header: 'Status',
                  render: (r) => (
                    <span className={`pill ${r.status === "completed" ? "ok" : r.status === "pending" ? "warn" : "bad"}`}>
                      {r.status === 'completed' && <CheckCircle2 size={12} />}
                      {r.status === 'pending' && <Clock size={12} />}
                      {r.status === 'cancelled' && <XCircle size={12} />}
                      {(r.status || 'completed').toUpperCase()}
                    </span>
                  ),
                },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="row end">
                      <button
                        onClick={() => { setSelectedBusinessId(r.business_id); setShowStatementModal(true); }}
                        title="View Startup Statement"
                        className="icon-btn"
                      >
                        <FileText size={16} />
                      </button>
                      <button
                        onClick={() => { setEditingRepayment(r); setShowEditModal(true); }}
                        title="Edit Payment"
                        className="icon-btn"
                      >
                        <Edit size={16} />
                      </button>
                      <button
                        onClick={async () => {
                          if (window.confirm(`Are you sure you want to void repayment #${r.id} for ${r.business_name}?`)) {
                            await api.delete(`/repayments/${branchId}/${r.id}/`)
                            reloadAll()
                          }
                        }}
                        title="Void / Delete Payment"
                        className="icon-btn"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ),
                },
              ]}
              rows={repaymentsList}
              empty="No repayment transactions found."
              footer={
                <div className="row spread" style={{borderTop: "1px solid var(--border)", paddingTop: 12}}>
                  <span className="muted xs">
                    Showing {repaymentsList.length} of {totalCount} repayment transactions
                  </span>
                  <Pager page={page} pageSize={pageSize} count={totalCount} onPage={setPage} />
                </div>
              }
            />
          </div>
        </div>
      )}

      {/* TAB 2: BORROWERS & LOAN ACCOUNTS */}
      {activeTab === 'borrowers' && (
        <div className="stack">
          <div className="table-wrap card">
            <DataTable
              columns={[
                {
                  header: 'Startup Borrower',
                  render: (b) => (
                    <div className="name-stack">
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowStatementModal(true); }}
                        className="link-strong"
                      >
                        {b.company_name_en || b.company_name}
                      </button>
                      {(b.entrepreneur || b.ceo_name) && (
                        <span className="muted xs nowrap" title={b.entrepreneur || b.ceo_name}>
                          Entrepreneur: {b.entrepreneur || b.ceo_name}
                        </span>
                      )}
                    </div>
                  ),
                },
                {
                  header: 'Cohort',
                  render: (b) => <span className="muted xs">{b.program_name}</span>,
                },
                {
                  header: 'Approved Loan Facility',
                  render: (b) => (
                    <div>
                      <span className="link-strong" style={{display:"block"}}>
                        €{(b.loan_approved_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="muted xs">
                        {(b.loan_approved_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Total Repaid',
                  render: (b) => (
                    <div>
                      <span className="ok-text strong" style={{display: "block"}}>
                        €{(b.total_repaid_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="ok-text xs">
                        {(b.total_repaid_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Outstanding Balance',
                  render: (b) => (
                    <div>
                      <span className="warn-text strong" style={{display: "block"}}>
                        €{(b.outstanding_balance_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="warn-text xs">
                        {(b.outstanding_balance_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Recovery Progress',
                  render: (b) => (
                    <div className="stack-sm" style={{width: 150}}>
                      <div className="row spread xs strong">
                        <span className="muted">{b.pct_repaid}%</span>
                        <span className="muted xs">{b.repayments_count} pymts</span>
                      </div>
                      <div className="track">
                        <div
                          className={`fill ${
                            b.pct_repaid >= 100 ? 'var(--ok)' : b.pct_repaid > 50 ? 'var(--secondary)' : 'var(--warn)'
                          }`}
                          style={{ width: `${Math.min(100, b.pct_repaid)}%` }}
                        />
                      </div>
                    </div>
                  ),
                },
                {
                  header: 'Actions',
                  render: (b) => (
                    <div className="row gap end">
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowRecordModal(true); }}
                        className="btn ghost sm"
                      >
                        <Plus size={12} /> Record Pay
                      </button>
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowStatementModal(true); }}
                        className="btn ghost sm"
                      >
                        Statement <ChevronRight size={14} />
                      </button>
                    </div>
                  ),
                },
              ]}
              rows={borrowers}
              empty="No loan borrowers found."
            />
          </div>
        </div>
      )}

      {/* RECORD PAYMENT MODAL */}
      {showRecordModal && (
        <RecordPaymentModal
          branchId={branchId}
          borrowers={borrowers}
          preselectedBusinessId={selectedBusinessId}
          onClose={() => { setShowRecordModal(false); setSelectedBusinessId(null); }}
          onSuccess={() => {
            setShowRecordModal(false)
            setSelectedBusinessId(null)
            reloadAll()
          }}
        />
      )}

      {/* IMPORT EXCEL MODAL */}
      {showImportModal && (
        <ImportRepaymentsModal
          branchId={branchId}
          onClose={() => setShowImportModal(false)}
          onSuccess={() => {
            setShowImportModal(false)
            reloadAll()
          }}
        />
      )}

      {/* STARTUP LOAN STATEMENT MODAL */}
      {showStatementModal && selectedBusinessId && (
        <StartupStatementModal
          branchId={branchId}
          businessId={selectedBusinessId}
          onClose={() => { setShowStatementModal(false); setSelectedBusinessId(null); }}
          onRecordPay={() => {
            setShowStatementModal(false)
            setShowRecordModal(true)
          }}
        />
      )}

      {/* EDIT PAYMENT MODAL */}
      {showEditModal && editingRepayment && (
        <EditPaymentModal
          branchId={branchId}
          repayment={editingRepayment}
          onClose={() => { setShowEditModal(false); setEditingRepayment(null); }}
          onSuccess={() => {
            setShowEditModal(false)
            setEditingRepayment(null)
            reloadAll()
          }}
        />
      )}
    </div>
  )
}


// Sub-component: Record Payment Modal
function RecordPaymentModal({ branchId, borrowers, preselectedBusinessId, onClose, onSuccess }) {
  const [businessId, setBusinessId] = useState(preselectedBusinessId || (borrowers[0]?.business_id || ''))
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split('T')[0])
  const [amountEur, setAmountEur] = useState('')
  const [exchangeRate, setExchangeRate] = useState(0.76)
  const [paymentMethod, setPaymentMethod] = useState('Bank Transfer')
  const [referenceNumber, setReferenceNumber] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const selectedBorrower = useMemo(() => {
    return borrowers.find((b) => b.business_id === Number(businessId))
  }, [borrowers, businessId])

  const calculatedJod = useMemo(() => {
    const amt = parseFloat(amountEur) || 0
    const rate = parseFloat(exchangeRate) || 0.76
    return (amt * rate).toFixed(3)
  }, [amountEur, exchangeRate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!businessId) {
      setError('Please select a startup borrower.')
      return
    }
    if (!amountEur || parseFloat(amountEur) <= 0) {
      setError('Repayment amount must be greater than zero.')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      await api.post(`/repayments/${branchId}/`, {
        business_id: Number(businessId),
        payment_date: paymentDate,
        amount: parseFloat(amountEur),
        currency: 'EUR',
        disbursement_currency: 'JOD',
        exchange_rate: parseFloat(exchangeRate),
        payment_method: paymentMethod,
        reference_number: referenceNumber,
        notes,
        status: 'completed',
      })
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to record repayment.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title="Record Startup Loan Repayment" onClose={onClose}>
      <form onSubmit={handleSubmit} className="stack">
        {error && (
          <div className="alert row gap" style={{fontSize: 12}}>
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        <div>
          <label className="xs strong" style={{display: "block", marginBottom: 4}}>Startup Borrower *</label>
          <select
            value={businessId}
            onChange={(e) => setBusinessId(e.target.value)}
            className="input"
            required
          >
            <option value="">Select Startup</option>
            {borrowers.map((b) => (
              <option key={b.business_id} value={b.business_id}>
                {b.company_name_en || b.company_name} (Outstanding: €{(b.outstanding_balance_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} / {(b.outstanding_balance_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD)
              </option>
            ))}
          </select>
        </div>

        {selectedBorrower && (
          <div className="note-box">
            <div className="row spread">
              <span>Approved Facility:</span>
              <span className="font-bold">€{(selectedBorrower.loan_approved_eur || 0).toLocaleString()} ({(selectedBorrower.loan_approved_jod || 0).toLocaleString()} JOD)</span>
            </div>
            <div className="row spread" style={{color: "var(--accent)"}}>
              <span>Total Repaid to Date:</span>
              <span className="font-semibold">€{(selectedBorrower.total_repaid_eur || 0).toLocaleString()}</span>
            </div>
            <div className="row spread strong" style={{borderTop: "1px solid var(--accent-soft)", paddingTop: 4, color: "var(--accent-strong)"}}>
              <span>Outstanding Balance:</span>
              <span>€{(selectedBorrower.outstanding_balance_eur || 0).toLocaleString()} ({(selectedBorrower.outstanding_balance_jod || 0).toLocaleString()} JOD)</span>
            </div>
          </div>
        )}

        <div className="grid-2">
          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Payment Date *</label>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="input"
              required
            />
          </div>

          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Payment Method</label>
            <select
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
              className="input"
            >
              <option value="Bank Transfer">Bank Transfer</option>
              <option value="Cheque">Cheque</option>
              <option value="Cash">Cash</option>
              <option value="Deposit Slip">Deposit Slip</option>
              <option value="Mobile Wallet">Mobile Wallet</option>
              <option value="Other">Other</option>
            </select>
          </div>
        </div>

        <div className="grid-3">
          <div >
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Amount (EUR) *</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              placeholder="e.g. 1000.00"
              value={amountEur}
              onChange={(e) => setAmountEur(e.target.value)}
              className="input strong"
              required
            />
          </div>

          <div >
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>FX Rate (EUR➔JOD)</label>
            <input
              type="number"
              step="0.0001"
              value={exchangeRate}
              onChange={(e) => setExchangeRate(e.target.value)}
              className="input"
            />
          </div>

          <div >
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Equivalent (JOD)</label>
            <div className="calc-out">
              {calculatedJod} JOD
            </div>
          </div>
        </div>

        <div>
          <label className="xs strong" style={{display: "block", marginBottom: 4}}>Bank Reference / Receipt #</label>
          <input
            type="text"
            placeholder="e.g. TRX-987654321"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            className="input mono"
          />
        </div>

        <div>
          <label className="xs strong" style={{display: "block", marginBottom: 4}}>Notes / Description</label>
          <textarea
            rows={2}
            placeholder="Additional details regarding this repayment tranche..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="input"
          />
        </div>

        <div className="row end gap modal-foot">
          <button
            type="button"
            onClick={onClose}
            className="btn ghost sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="btn primary sm"
          >
            {submitting ? 'Recording...' : 'Record Payment Receipt'}
          </button>
        </div>
      </form>
    </Modal>
  )
}


// Sub-component: Startup Statement Modal
function HeroStat({ label, eur, jod, tone, note }) {
  const fE = (v) => `€${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
  const fJ = (v) => `${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} JOD`
  return (
    <div className="hero-stat">
      <span className="hero-stat-label">{label}</span>
      <div className="hero-stat-pair">
        <span className="hero-stat-eur" style={{ color: tone }}>{fE(eur)}</span>
        <span className="hero-stat-jod">{fJ(jod)}</span>
      </div>
      {note && <span className="hero-stat-note">{note}</span>}
    </div>
  )
}

function StartupStatementModal({ branchId, businessId, onClose, onRecordPay }) {
  const { data: ledger, loading } = useFetch(branchId && businessId ? `/repayments/${branchId}/startup/${businessId}/ledger/` : null)

  // running repayable balance across the merged ledger: Track II loan
  // disbursements raise it, instalments and refinancing lower it; grants,
  // fees and draft-batch rows never touch it
  const lines = useMemo(() => {
    if (!ledger) return []
    let balEur = 0, balJod = 0
    return (ledger.lines || []).map((l) => {
      const counts = l.source === 'disbursement'
        ? l.kind === 'loan'
        : l.status === 'completed' && ['installment', 'refinanced'].includes(l.entry_type)
      if (counts) {
        balEur += l.source === 'disbursement' ? l.amount_eur : -l.amount_eur
        balJod += l.source === 'disbursement' ? l.amount_jod : -l.amount_jod
      }
      return { ...l, balance_eur: Math.max(0, balEur), balance_jod: Math.max(0, balJod) }
    })
  }, [ledger])

  if (loading || !ledger) {
    return (
      <Modal title="Startup Loan Account Statement" onClose={onClose} wide>
        <div className="muted center" style={{padding: 32}}>Loading statement details...</div>
      </Modal>
    )
  }

  const fmtEur = (v) => `€${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
  const fmtJod = (v) => `${(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} JOD`
  const g1 = ledger.disbursed_grant_I_eur || 0
  const g2 = ledger.disbursed_grant_II_eur || 0
  const grantNote = !ledger.disbursed_grant_eur ? undefined
    : (g1 > 0 && g2 > 0
        ? `+ ${fmtEur(ledger.disbursed_grant_eur)} grants received — Track I ${fmtEur(g1)} · Track II co-financing ${fmtEur(g2)} (not repayable)`
        : g2 > 0
          ? `+ ${fmtEur(g2)} Track II co-financing grant (not repayable)`
          : `+ ${fmtEur(g1)} Track I grant (not repayable)`)

  return (
    <Modal title={`Loan Account: ${ledger.business_name_en || ledger.business_name || 'Startup'}`} onClose={onClose} wide>
      <div className="stack-lg">
        {/* Startup Overview Header */}
        <div className="hero-dark stack">
          <div className="row spread" style={{alignItems: "flex-start"}}>
            <div>
              <span className="xs strong" style={{color: "#8cd2a9", textTransform: "uppercase", letterSpacing: ".07em"}}>{ledger.program_name}</span>
              <h2 className="text-xl font-bold">{ledger.business_name}</h2>
            </div>
            <button
              onClick={onRecordPay}
              className="btn primary sm"
            >
              <Plus size={14} /> Record Payment
            </button>
          </div>

          <div className="grid-3 stat-strip">
            <HeroStat label="Loan approved (EUR)" eur={ledger.loan_approved_eur}
                      jod={ledger.loan_approved_jod} tone="#ffffff" />
            <HeroStat label="Principal disbursed (Track II)" eur={ledger.disbursed_loan_eur}
                      jod={ledger.disbursed_loan_jod} tone="#7cc3e8"
                      note={grantNote} />
            <HeroStat label="Collected to date" eur={ledger.total_repaid_eur}
                      jod={ledger.total_repaid_jod} tone="#6fd39a"
                      note={ledger.principal_collected_eur != null
                        ? `principal ${fmtEur(ledger.principal_collected_eur)} · int/fees ${fmtEur(ledger.charges_collected_eur)}`
                        : undefined} />
          </div>
          <div className="grid-2 stat-strip">
            <HeroStat label="Outstanding — principal only" eur={ledger.outstanding_eur}
                      jod={ledger.outstanding_jod} tone="#ffc46b"
                      note="principal disbursed not yet repaid" />
            <HeroStat label="Outstanding — incl. interest/fees" eur={ledger.outstanding_incl_charges_eur}
                      jod={ledger.outstanding_incl_charges_jod} tone="#ffd9a0"
                      note="full repayable per schedule: principal + remaining interest/fees" />
          </div>
        </div>

        {/* Loan schedule & arrears (from the Loandisk loan book) */}
        {(ledger.loans || []).length > 0 && (
          <div>
            <h3 className="strong" style={{marginBottom: 8}}>Loan schedule &amp; arrears</h3>
            <div className="stack-sm">
              {ledger.loans.map((l) => (
                <div key={l.loan_number} className={`loan-tile ${l.fully_settled ? "ok" : l.arrears > 0 ? "warn" : ""}`}>
                  <div className="row spread">
                    <b className="strong">Loan {l.loan_number} <span className="muted xs">({l.currency})</span></b>
                    {l.fully_settled
                      ? <span className="pill ok">Settled</span>
                      : l.arrears > 0
                        ? <span className="pill warn">Arrears {(l.arrears || 0).toLocaleString()} {l.currency}</span>
                        : <span className="pill neutral">Current</span>}
                  </div>
                  <div className="grid-4 xs" style={{fontSize: 11}}>
                    <div><span className="muted xs">Instalments paid</span><b>{l.instalments_paid}/{l.instalments_scheduled}</b></div>
                    <div><span className="muted xs">Due to date</span><b>{(l.scheduled_due_to_date || 0).toLocaleString()} {l.currency}</b></div>
                    <div><span className="muted xs">Paid to date</span><b className="ok-text">{(l.paid_to_date || 0).toLocaleString()} {l.currency}</b></div>
                    <div><span className="muted xs">Next instalment</span><b>{l.next_due_date ? `${(l.next_amount || 0).toLocaleString()} on ${l.next_due_date}` : '—'}</b></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Month-by-month outstanding */}
        <div>
          <h3 className="strong" style={{marginBottom: 8}}>Month-by-month balance</h3>
          <div className="scroll-table">
            <table className="modal-table">
              <thead className="sticky-head">
                <tr>
                  <th >Month</th>
                  <th >Loan received</th>
                  <th >Grant received</th>
                  <th >Repaid</th>
                  <th className=" r">Principal still owed</th>
                  <th className=" r">Incl. int/fees</th>
                </tr>
              </thead>
              <tbody >
                {(ledger.monthly || []).map((m) => (
                  <tr key={m.month} >
                    <td className="strong">{m.month}</td>
                    <td className="" style={{color: "#2f6f9c"}}>{m.loan_in_eur ? fmtEur(m.loan_in_eur) : '—'}</td>
                    <td className="" style={{color: "var(--accent)"}}>{m.grant_in_eur ? fmtEur(m.grant_in_eur) : '—'}</td>
                    <td className="ok-text">{m.repaid_eur ? fmtEur(m.repaid_eur) : '—'}</td>
                    <td className="r warn-text strong">{fmtEur(m.closing_outstanding_eur)}</td>
                    <td className="r muted">{m.closing_incl_charges_eur ? fmtEur(m.closing_incl_charges_eur) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Full movement ledger */}
        <div>
          <h3 className="strong" style={{marginBottom: 8}}>Every payment line by line</h3>
          {lines.length === 0 ? (
            <div className="card-flat muted center sm">
              No movements recorded for this startup yet.
            </div>
          ) : (
            <div className="scroll-table">
              <table className="modal-table">
                <thead className="sticky-head">
                  <tr>
                    <th >Date</th>
                    <th >Type</th>
                    <th >Detail</th>
                    <th className=" r">In (EUR)</th>
                    <th className=" r">Out (EUR)</th>
                    <th className=" r">Balance (EUR)</th>
                  </tr>
                </thead>
                <tbody >
                  {lines.map((l, i) => {
                    const isGrant = l.source === 'disbursement' && l.kind === 'grant'
                    const isFee = l.source === 'repayment' && l.entry_type === 'fee'
                    const unverified = l.source === 'repayment' && l.verified === false
                    return (
                      <tr key={i} className={isGrant ? "grant-row" : ""}>
                        <td className="nowrap strong">{l.date}</td>
                        <td className="type-cell">
                          <span className={`pill ${l.source === "disbursement" ? (isGrant ? "ok" : "neutral") : (isFee ? "warn" : "ok")}`}>
                            {l.source === 'disbursement'
                              ? `Track ${l.track} ${l.kind}`
                              : (l.entry_type || 'repayment')}
                          </span>
                          {unverified && <AlertCircle size={12} className="warn-text" />}
                        </td>
                        <td className="muted sm">
                          {l.label}
                          {l.channel && <span className="muted xs">{l.channel}</span>}
                        </td>
                        <td className=" r font-semibold text-sky-800">
                          {l.source === 'disbursement' ? fmtEur(l.amount_eur) : ''}
                        </td>
                        <td className="r ok-text" style={{fontWeight: 600}}>
                          {l.source === 'repayment' ? fmtEur(l.amount_eur) : ''}
                        </td>
                        <td className="r warn-text strong">{fmtEur(l.balance_eur)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted xs">
            Grants (Track I stipends/vouchers and Track II co-financing) are not repayable. Repayments offset the Track II loan only.
            The balance column reflects instalments and refinancing; fees are charges, not repayments.
          </p>
        </div>
      </div>
    </Modal>
  )
}


// Sub-component: Edit Payment Modal
function EditPaymentModal({ branchId, repayment, onClose, onSuccess }) {
  const [paymentDate, setPaymentDate] = useState(repayment.payment_date || '')
  const [amountEur, setAmountEur] = useState(repayment.amount_eur || '')
  const [exchangeRate, setExchangeRate] = useState(repayment.exchange_rate || 0.76)
  const [paymentMethod, setPaymentMethod] = useState(repayment.payment_method || 'Bank Transfer')
  const [referenceNumber, setReferenceNumber] = useState(repayment.reference_number || '')
  const [notes, setNotes] = useState(repayment.notes || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api.put(`/repayments/${branchId}/${repayment.id}/`, {
        payment_date: paymentDate,
        amount: parseFloat(amountEur),
        exchange_rate: parseFloat(exchangeRate),
        payment_method: paymentMethod,
        reference_number: referenceNumber,
        notes,
      })
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update repayment.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title={`Edit Repayment #${repayment.id}: ${repayment.business_name || 'Payment'}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="stack">
        {error && (
          <div className="alert">
            {error}
          </div>
        )}

        <div className="grid-2">
          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Payment Date</label>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="input"
              required
            />
          </div>
          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Payment Method</label>
            <select
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
              className="input"
            >
              <option value="Bank Transfer">Bank Transfer</option>
              <option value="Cheque">Cheque</option>
              <option value="Cash">Cash</option>
              <option value="Deposit Slip">Deposit Slip</option>
              <option value="Mobile Wallet">Mobile Wallet</option>
              <option value="Other">Other</option>
            </select>
          </div>
        </div>

        <div className="grid-2">
          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Amount (EUR)</label>
            <input
              type="number"
              step="0.01"
              value={amountEur}
              onChange={(e) => setAmountEur(e.target.value)}
              className="input strong"
              required
            />
          </div>
          <div>
            <label className="xs strong" style={{display: "block", marginBottom: 4}}>Exchange Rate (EUR/JOD)</label>
            <input
              type="number"
              step="0.0001"
              value={exchangeRate}
              onChange={(e) => setExchangeRate(e.target.value)}
              className="input"
            />
          </div>
        </div>

        <div>
          <label className="xs strong" style={{display: "block", marginBottom: 4}}>Reference Number</label>
          <input
            type="text"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            className="input mono"
          />
        </div>

        <div>
          <label className="xs strong" style={{display: "block", marginBottom: 4}}>Notes</label>
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="input"
          />
        </div>

        <div className="row end gap modal-foot">
          <button
            type="button"
            onClick={onClose}
            className="btn ghost sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="btn primary sm"
          >
            {submitting ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  )
}


// Sub-component: Import Repayments Modal
function ImportRepaymentsModal({ branchId, onClose, onSuccess }) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  const downloadTemplate = async () => {
    try {
      const res = await api.get(`/repayments/${branchId}/import-template/`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `loan_repayments_import_template_${branchId}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      setError('Failed to download import template: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError('')
      setResult(null)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0])
      setError('')
      setResult(null)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) {
      setError('Please select an Excel or CSV file to import.')
      return
    }

    setUploading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await api.post(`/repayments/${branchId}/import/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to import repayments from spreadsheet.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Modal title="Import Startup Loan Repayments from Excel" onClose={onClose} wide>
      <div className="stack">
        {/* Template Download Card */}
        <div className="note-box row spread gap">
          <div>
            <h4 className="xs strong" style={{color: "var(--accent)"}}>Need the standard spreadsheet format?</h4>
            <p className="xs" style={{color: "var(--accent)"}}>
              Download the pre-filled template containing all active startup borrowers in this branch.
            </p>
          </div>
          <button
            type="button"
            onClick={downloadTemplate}
            className="btn ghost sm"
          >
            <Download size={14} /> Download Template
          </button>
        </div>

        {error && (
          <div className="alert row gap" style={{fontSize: 12}}>
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Results Feedback */}
        {result ? (
          <div className="stack">
            <div className="ok-box stack-sm">
              <div className="row gap strong ok-text">
                <CheckCircle2 size={20} />
                Import Complete!
              </div>
              <div className="grid-4 stat-strip">
                <div className="card-flat green">
                  <span className="muted xs">New Payments</span>
                  <span className="ok-text strong">{result.imported_count}</span>
                </div>
                <div className="card-flat green">
                  <span className="muted xs">Updated Payments</span>
                  <span className="strong" style={{color: "var(--accent)"}}>{result.updated_count}</span>
                </div>
                <div className="card-flat green">
                  <span className="muted xs">Total EUR</span>
                  <span className="strong">€{result.total_amount_eur.toLocaleString()}</span>
                </div>
                <div className="card-flat green">
                  <span className="muted xs">Total JOD</span>
                  <span className="ok-text strong">{result.total_amount_jod.toLocaleString()} JOD</span>
                </div>
              </div>
            </div>

            {result.errors && result.errors.length > 0 && (
              <div className="warn-box stack-sm">
                <div className="row gap strong warn-text">
                  <AlertCircle size={16} />
                  {result.errors.length} Warnings / Skipped Rows:
                </div>
                <ul className="warn-list">
                  {result.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="row end gap">
              <button
                type="button"
                onClick={onSuccess}
                className="btn primary sm"
              >
                Done & View Repayments
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="stack">
            {/* File Drop Zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`dropzone ${dragOver ? "over" : ""}`}
              onClick={() => document.getElementById('repayment-file-input')?.click()}
            >
              <input
                id="repayment-file-input"
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <Upload size={32} />
              {file ? (
                <div>
                  <p className="xs strong">{file.name}</p>
                  <p className="muted xs">{(file.size / 1024).toFixed(1)} KB — Click to change file</p>
                </div>
              ) : (
                <div>
                  <p className="xs strong">Click to browse or drag and drop spreadsheet</p>
                  <p className="muted xs">Supports Microsoft Excel (.xlsx, .xls) and CSV (.csv)</p>
                </div>
              )}
            </div>

            <div className="row end gap modal-foot">
              <button
                type="button"
                onClick={onClose}
                className="btn ghost sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!file || uploading}
                className="btn primary sm"
              >
                <Upload size={14} />
                {uploading ? 'Processing Spreadsheet...' : 'Upload & Process Repayments'}
              </button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  )
}


// ================================================================ Monthly Batches
// Batch uploads mirror the disbursement flow: a draft batch is visible but
// holds no money until it is confirmed and locked.

function BatchesTab({ branchId, batches, reload, onChanged }) {
  const [showUpload, setShowUpload] = useState(false)
  const [detailId, setDetailId] = useState(null)

  return (
    <div className="stack">
      <div className="row spread gap wrap">
        <p className="muted sm">
          Upload a monthly repayment register (Excel/CSV) per cohort. Rows whose
          startup cannot be matched are reported back instead of being guessed.
          A draft batch does not move any balance until it is confirmed.
        </p>
        <button
          onClick={() => setShowUpload(true)}
          className="btn primary"
        >
          <Upload size={16} /> Upload Batch
        </button>
      </div>

      {batches.length === 0 ? (
        <div className="card pad muted center">
          No repayment batches uploaded yet.
        </div>
      ) : (
        <div className="card">
          <table className="modal-table">
            <thead className="sticky-head">
              <tr>
                <th >Batch</th>
                <th >Source</th>
                <th >Rows</th>
                <th >Total (JOD)</th>
                <th >Total (EUR)</th>
                <th >Status</th>
                <th className=" r">Actions</th>
              </tr>
            </thead>
            <tbody >
              {batches.map((b) => (
                <tr key={b.id} >
                  <td >
                    <button className="link-strong" onClick={() => setDetailId(b.id)}>
                      {b.title}
                    </button>
                    <span className="muted xs">{b.batch_month || ''}</span>
                  </td>
                  <td className="muted" style={{maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"}} title={b.source}>{b.source || '—'}</td>
                  <td className="strong">{b.rows_count}</td>
                  <td className="ok-text" style={{fontWeight: 600}}>{(b.total_jod || 0).toLocaleString()} JOD</td>
                  <td className="strong">€{(b.total_eur || 0).toLocaleString()}</td>
                  <td >
                    {b.status === 'processed'
                      ? <span className="pill ok"><Lock size={12} /> Processed</span>
                      : <span className="pill warn"><Clock size={12} /> Draft</span>}
                  </td>
                  <td className="r nowrap">
                    <button className="btn ghost sm" onClick={() => setDetailId(b.id)}>View</button>
                    {b.status === 'draft' && <ConfirmBatchButton branchId={branchId} batchId={b.id} onDone={onChanged} />}
                    {b.status === 'processed' && <ReopenBatchButton branchId={branchId} batchId={b.id} onDone={onChanged} />}
                    <DeleteBatchButton branchId={branchId} batchId={b.id} locked={b.status === 'processed'} onDone={onChanged} />
                    <a
                      href={`/api/repayments/${branchId}/batches/${b.id}/export/`}
                      className="btn ghost sm" style={{display: "inline-block"}}
                      onClick={async (e) => {
                        e.preventDefault()
                        try {
                          const res = await api.get(`/repayments/${branchId}/batches/${b.id}/export/`, { responseType: 'blob' })
                          const url = window.URL.createObjectURL(new Blob([res.data]))
                          const a = document.createElement('a')
                          a.href = url
                          a.download = `${b.title.replace(/[^A-Za-z0-9_-]+/g, '_')}.xlsx`
                          a.click()
                          a.remove()
                        } catch (err) {
                          alert('Export failed: ' + (err.response?.data?.detail || err.message))
                        }
                      }}
                    >XLSX</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showUpload && (
        <UploadBatchModal
          branchId={branchId}
          onClose={() => setShowUpload(false)}
          onUploaded={(res) => { setShowUpload(false); reload(); onChanged() }}
        />
      )}
      {detailId && (
        <BatchDetailModal branchId={branchId} batchId={detailId} onClose={() => setDetailId(null)} />
      )}
    </div>
  )
}


function ConfirmBatchButton({ branchId, batchId, onDone }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      disabled={busy}
      onClick={async () => {
        if (!window.confirm('Confirm this batch? It becomes locked and its rows count toward balances.')) return
        setBusy(true)
        try { await api.post(`/repayments/${branchId}/batches/${batchId}/confirm/`); onDone() }
        catch (err) { alert(err.response?.data?.detail || 'Confirm failed') }
        finally { setBusy(false) }
      }}
      className="btn primary sm"
    >Confirm</button>
  )
}


function ReopenBatchButton({ branchId, batchId, onDone }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      disabled={busy}
      onClick={async () => {
        if (!window.confirm('Reopen this processed batch for corrections?')) return
        setBusy(true)
        try { await api.post(`/repayments/${branchId}/batches/${batchId}/reopen/`); onDone() }
        catch (err) { alert(err.response?.data?.detail || 'Reopen failed') }
        finally { setBusy(false) }
      }}
      className="btn ghost sm"
    >Reopen</button>
  )
}


function DeleteBatchButton({ branchId, batchId, locked, onDone }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      disabled={busy || locked}
      title={locked ? 'Processed batches are locked — reopen first' : 'Delete draft batch'}
      onClick={async () => {
        if (!window.confirm('Delete this draft batch and all its rows?')) return
        setBusy(true)
        try { await api.delete(`/repayments/${branchId}/batches/${batchId}/`); onDone() }
        catch (err) { alert(err.response?.data?.detail || 'Delete failed') }
        finally { setBusy(false) }
      }}
      className={`btn ghost sm ${locked ? "" : "danger"}`}
    >Delete</button>
  )
}


function UploadBatchModal({ branchId, onClose, onUploaded }) {
  const [file, setFile] = useState(null)
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!file) { setError('Choose an Excel or CSV file first.'); return }
    setBusy(true); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (title) fd.append('title', title)
      if (source) fd.append('source', source)
      const res = await api.post(`/repayments/${branchId}/batches/upload/`, fd)
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally { setBusy(false) }
  }

  if (result) {
    return (
      <Modal title="Batch uploaded" onClose={() => onUploaded(result)} wide>
        <div className="stack">
          <div className="ok-box strong">
            {result.detail}
          </div>
          <div className="grid-3">
            <div className="card-flat">
              <span className="muted xs">Rows created</span>
              <b className="strong">{result.batch.rows_count}</b>
            </div>
            <div className="card-flat">
              <span className="muted xs">Startups matched</span>
              <b className="strong">{result.matched_startups}</b>
            </div>
            <div className="card-flat">
              <span className="muted xs">Rows skipped</span>
              <b className="strong">{result.skipped_rows}</b>
            </div>
          </div>
          {result.unmatched?.length > 0 && (
            <div className="warn-box stack-sm">
              <b className="row gap" style={{marginBottom: 4, display: "flex"}}><AlertCircle size={14} /> {result.unmatched.length} row(s) skipped — startup not found in this branch:</b>
              <ul className="list-disc ml-5">
                {[...new Set(result.unmatched.map(u => u.startup))].map((s) => (
                  <li key={s}>{s} <span className="warn-text">({result.unmatched.filter(u => u.startup === s).length} rows)</span></li>
                ))}
              </ul>
              <p className="warn-text" style={{marginTop: 6}}>Add these startups to the branch (with their loan cases), then upload a follow-up batch for them.</p>
            </div>
          )}
          <div className="row end gap">
            <button onClick={() => onUploaded(result)} className="btn primary">
              Done
            </button>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title="Upload repayment batch" onClose={onClose} wide>
      <form onSubmit={submit} className="stack">
        <p className="muted xs">
          Expected columns: Cohort, Startup, Loan #, Paid by, Date of repayment,
          Cash / Bank, Channel, Amount (JOD), Amount (EUR), Instalment / notes, Verified against.
        </p>
        <label className="block">
          <span className="muted xs strong">Spreadsheet (xlsx / csv)</span>
          <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)}
                 className="input" />
        </label>
        <label className="block">
          <span className="muted xs strong">Batch title (optional)</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Track II Repayments — October 2026"
                 className="input" />
        </label>
        <label className="block">
          <span className="muted xs strong">Source / verification note (optional)</span>
          <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. Bank al Etihad statement ...1004"
                 className="input" />
        </label>
        {error && <div className="alert strong">{error}</div>}
        <div className="row end gap">
          <button type="button" onClick={onClose} className="btn ghost">Cancel</button>
          <button type="submit" disabled={busy} className="btn primary">
            {busy ? 'Uploading…' : 'Upload batch'}
          </button>
        </div>
      </form>
    </Modal>
  )
}


function BatchDetailModal({ branchId, batchId, onClose }) {
  const { data: batch, loading } = useFetch(branchId && batchId ? `/repayments/${branchId}/batches/${batchId}/` : null)
  if (loading || !batch) {
    return <Modal title="Batch" onClose={onClose} wide><div className="muted center" style={{padding: 32}}>Loading…</div></Modal>
  }
  return (
    <Modal title={batch.title} onClose={onClose} wide>
      <div className="stack">
        <div className="grid-4">
          <div className="card-flat">
            <span className="muted xs">Rows</span><b className="strong">{batch.rows_count}</b>
          </div>
          <div className="card-flat">
            <span className="muted xs">Total JOD</span><b className="ok-text">{(batch.total_jod || 0).toLocaleString()}</b>
          </div>
          <div className="card-flat">
            <span className="muted xs">Total EUR</span><b className="strong">€{(batch.total_eur || 0).toLocaleString()}</b>
          </div>
          <div className="card-flat">
            <span className="muted xs">Status</span>
            <b className={batch.status === "processed" ? "ok-text" : "warn-text"}>{batch.status}</b>
          </div>
        </div>
        {batch.source && <p className="muted xs">Source: {batch.source}</p>}
        <div className="scroll-table" style={{maxHeight: 420}}>
          <table className="modal-table">
            <thead className="sticky-head">
              <tr>
                <th >Date</th><th >Startup</th><th >Loan #</th>
                <th >Paid by</th><th >Channel</th>
                <th >JOD</th><th >EUR</th><th >Instalment / notes</th>
                <th >Verified</th>
              </tr>
            </thead>
            <tbody >
              {(batch.repayments || []).map((r) => (
                <tr key={r.id} >
                  <td className="nowrap">{r.payment_date}</td>
                  <td className="strong">{r.business_name}</td>
                  <td className="muted mono">{r.loan_number}</td>
                  <td className="muted sm">{r.payer_name || '—'}</td>
                  <td className="muted sm">{r.channel || r.payment_method}</td>
                  <td className="ok-text" style={{fontWeight: 600}}>{r.amount_jod ? r.amount_jod.toLocaleString() : '—'}</td>
                  <td className="strong">{r.amount_eur ? `€${r.amount_eur.toLocaleString()}` : '—'}</td>
                  <td className="muted sm">{r.instalment_label || '—'}</td>
                  <td >
                    {r.verified
                      ? <CheckCircle2 size={14} />
                      : <AlertCircle size={14} title={r.verified_against} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  )
}
