import { useState, useMemo } from 'react'
import {
  Receipt, Plus, Download, Upload, CheckCircle2, Clock, XCircle,
  FileText, Search, Building2, User, DollarSign,
  TrendingUp, CreditCard, Calendar, ChevronRight, AlertCircle, Edit, Trash2,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import api from '../api'
import { DataTable, Pager, Modal, StatTile } from '../components/ui'

export default function LoanRepayments() {
  const { branch, user } = useAuth()
  const branchId = branch?.id || user?.branch_id || 1

  const [activeTab, setActiveTab] = useState('ledger') // 'ledger' | 'borrowers'
  const [page, setPage] = useState(1)
  const pageSize = 15
  const [search, setSearch] = useState('')
  const [selectedProgram, setSelectedProgram] = useState('')
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
  const summaryUrl = branchId ? `/repayments/${branchId}/summary/` : null
  const overviewUrl = branchId ? `/repayments/${branchId}/loans-overview/` : null
  const programsUrl = branchId ? `/programs/${branchId}/?page=1&page_size=100` : null

  const ledgerQueryParams = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
    ...(search && { search }),
    ...(selectedProgram && { program_id: selectedProgram }),
    ...(selectedMethod && { payment_method: selectedMethod }),
    ...(selectedStatus && { status: selectedStatus }),
  }).toString()

  const ledgerUrl = branchId ? `/repayments/${branchId}/?${ledgerQueryParams}` : null

  const summaryRes = useFetch(summaryUrl)
  const overviewRes = useFetch(overviewUrl)
  const ledgerRes = useFetch(ledgerUrl)
  const programsRes = useFetch(programsUrl)

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

  const reloadAll = () => {
    ledgerRes.reload && ledgerRes.reload()
    summaryRes.reload && summaryRes.reload()
    overviewRes.reload && overviewRes.reload()
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
    <div className="pad-lg font-sans text-slate-800 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-teal-50 rounded-xl text-teal-700 border border-teal-200/60 shadow-xs">
              <Receipt className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Loan Repayments & Recoveries</h1>
              <p className="text-sm text-slate-500 font-normal">
                Track startup loan repayments, record payment receipts, and monitor loan balance recovery schedules.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-medium text-slate-600">
            <button
              onClick={() => handleExport('excel')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md hover:bg-white hover:shadow-xs transition-all text-emerald-700 font-semibold"
            >
              <Download className="w-3.5 h-3.5" /> Export Excel
            </button>
            <button
              onClick={() => handleExport('csv')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md hover:bg-white hover:shadow-xs transition-all text-slate-700"
            >
              <FileText className="w-3.5 h-3.5" /> CSV
            </button>
          </div>

          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-900 text-white font-medium text-sm px-3.5 py-2 rounded-lg shadow-xs transition-all"
          >
            <Upload className="w-4 h-4 text-teal-400" /> Import Excel
          </button>

          <button
            onClick={() => { setSelectedBusinessId(null); setShowRecordModal(true); }}
            className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white font-medium text-sm px-4 py-2 rounded-lg shadow-xs transition-all"
          >
            <Plus className="w-4 h-4" /> Record Payment
          </button>
        </div>
      </div>

      {/* KPI Stats Section */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile
          label="Total Loans Approved / Disbursed"
          value={`€${(summary.total_approved_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          sub={`${(summary.total_approved_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD total facility`}
        />
        <StatTile
          label="Total Principal Repaid to Date"
          value={`€${(summary.total_repaid_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          sub={`${(summary.total_repaid_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD (${summary.recovery_rate_pct || 0}% recovery)`}
        />
        <StatTile
          label="Outstanding Portfolio Balance"
          value={`€${(summary.outstanding_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          sub={`${(summary.outstanding_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD remaining`}
        />
        <StatTile
          label="Active Borrowers & Payments"
          value={`${summary.active_borrowers_count || 0} Startups`}
          sub={`${summary.total_repayments_count || 0} recorded payment transactions`}
        />
      </div>

      {/* Main Navigation Tabs */}
      <div className="flex border-b border-slate-200 gap-8">
        <button
          onClick={() => setActiveTab('ledger')}
          className={`pb-3 text-sm font-semibold transition-all relative ${
            activeTab === 'ledger' ? 'text-teal-700 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Repayment Ledger ({totalCount})
        </button>
        <button
          onClick={() => setActiveTab('borrowers')}
          className={`pb-3 text-sm font-semibold transition-all relative ${
            activeTab === 'borrowers' ? 'text-teal-700 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Borrowers & Loan Accounts ({borrowers.length})
        </button>
      </div>

      {/* TAB 1: REPAYMENT LEDGER */}
      {activeTab === 'ledger' && (
        <div className="space-y-4">
          {/* Filter Toolbar */}
          <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs flex flex-wrap items-center justify-between gap-3">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search by startup, reference #, notes…"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                className="w-full text-sm pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500"
              />
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={selectedProgram}
                onChange={(e) => { setSelectedProgram(e.target.value); setPage(1); }}
                className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-teal-500/20"
              >
                <option value="">All Cohorts / Programs</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>

              <select
                value={selectedMethod}
                onChange={(e) => { setSelectedMethod(e.target.value); setPage(1); }}
                className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-teal-500/20"
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
                className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-teal-500/20"
              >
                <option value="">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="pending">Pending</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>

          {/* Transactions Table */}
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden">
            <DataTable
              columns={[
                {
                  header: 'Payment Date',
                  render: (r) => (
                    <div className="flex items-center gap-1.5 text-slate-700 font-medium text-xs">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      {r.payment_date || '—'}
                    </div>
                  ),
                },
                {
                  header: 'Startup / Borrower',
                  render: (r) => (
                    <div>
                      <button
                        onClick={() => { setSelectedBusinessId(r.business_id); setShowStatementModal(true); }}
                        className="font-bold text-slate-900 hover:text-teal-600 transition-colors text-sm block text-left"
                      >
                        {r.business_name}
                      </button>
                      {r.recorded_by && (
                        <span className="text-[11px] text-slate-400">By: {r.recorded_by.name}</span>
                      )}
                    </div>
                  ),
                },
                {
                  header: 'Cohort',
                  render: (r) => <span className="text-xs text-slate-600">{r.program_name || '—'}</span>,
                },
                {
                  header: 'Base Amount (EUR)',
                  render: (r) => (
                    <span className="font-semibold text-slate-900 text-sm">
                      €{(r.amount_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </span>
                  ),
                },
                {
                  header: 'JOD Equivalent',
                  render: (r) => (
                    <div>
                      <span className="font-semibold text-emerald-700 text-sm block">
                        {(r.amount_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                      <span className="text-[10px] text-slate-400">Rate: {r.exchange_rate}</span>
                    </div>
                  ),
                },
                {
                  header: 'Method & Ref',
                  render: (r) => (
                    <div className="text-xs">
                      <span className="font-medium text-slate-800 block">{r.payment_method}</span>
                      <span className="text-slate-400 font-mono text-[11px]">{r.reference_number || 'No Ref'}</span>
                    </div>
                  ),
                },
                {
                  header: 'Status',
                  render: (r) => (
                    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${
                      r.status === 'completed' ? 'bg-emerald-100 text-emerald-800' :
                      r.status === 'pending' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                    }`}>
                      {r.status === 'completed' && <CheckCircle2 className="w-3 h-3" />}
                      {r.status === 'pending' && <Clock className="w-3 h-3" />}
                      {r.status === 'cancelled' && <XCircle className="w-3 h-3" />}
                      {(r.status || 'completed').toUpperCase()}
                    </span>
                  ),
                },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="flex items-center gap-1 justify-end">
                      <button
                        onClick={() => { setSelectedBusinessId(r.business_id); setShowStatementModal(true); }}
                        title="View Startup Statement"
                        className="p-1.5 text-slate-400 hover:text-teal-600 hover:bg-slate-50 rounded-md transition-colors"
                      >
                        <FileText className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => { setEditingRepayment(r); setShowEditModal(true); }}
                        title="Edit Payment"
                        className="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-slate-50 rounded-md transition-colors"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={async () => {
                          if (window.confirm(`Are you sure you want to void repayment #${r.id} for ${r.business_name}?`)) {
                            await api.delete(`/repayments/${branchId}/${r.id}/`)
                            reloadAll()
                          }
                        }}
                        title="Void / Delete Payment"
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-slate-50 rounded-md transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ),
                },
              ]}
              rows={repaymentsList}
              empty="No repayment transactions found."
              footer={
                <div className="p-4 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-xs text-slate-500">
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
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden">
            <DataTable
              columns={[
                {
                  header: 'Startup Borrower',
                  render: (b) => (
                    <div>
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowStatementModal(true); }}
                        className="font-bold text-slate-900 hover:text-teal-600 text-sm text-left block"
                      >
                        {b.company_name}
                      </button>
                      {b.ceo_name && <span className="text-xs text-slate-400">CEO: {b.ceo_name}</span>}
                    </div>
                  ),
                },
                {
                  header: 'Cohort',
                  render: (b) => <span className="text-xs text-slate-600">{b.program_name}</span>,
                },
                {
                  header: 'Approved Loan Facility',
                  render: (b) => (
                    <div>
                      <span className="font-bold text-slate-900 text-sm block">
                        €{(b.loan_approved_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="text-xs text-slate-500 font-medium">
                        {(b.loan_approved_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Total Repaid',
                  render: (b) => (
                    <div>
                      <span className="font-bold text-emerald-700 text-sm block">
                        €{(b.total_repaid_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="text-xs text-emerald-600 font-medium">
                        {(b.total_repaid_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Outstanding Balance',
                  render: (b) => (
                    <div>
                      <span className="font-bold text-amber-800 text-sm block">
                        €{(b.outstanding_balance_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                      <span className="text-xs text-amber-700 font-medium">
                        {(b.outstanding_balance_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD
                      </span>
                    </div>
                  ),
                },
                {
                  header: 'Recovery Progress',
                  render: (b) => (
                    <div className="w-36 space-y-1">
                      <div className="flex justify-between text-xs font-semibold">
                        <span className="text-slate-600">{b.pct_repaid}%</span>
                        <span className="text-slate-400 text-[10px]">{b.repayments_count} pymts</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            b.pct_repaid >= 100 ? 'bg-emerald-500' :
                            b.pct_repaid > 50 ? 'bg-teal-500' : 'bg-amber-500'
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
                    <div className="flex items-center gap-2 justify-end">
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowRecordModal(true); }}
                        className="px-2.5 py-1 bg-teal-50 text-teal-700 hover:bg-teal-100 rounded-md text-xs font-semibold transition-colors flex items-center gap-1"
                      >
                        <Plus className="w-3 h-3" /> Record Pay
                      </button>
                      <button
                        onClick={() => { setSelectedBusinessId(b.business_id); setShowStatementModal(true); }}
                        className="px-2.5 py-1 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-md text-xs font-medium transition-colors flex items-center gap-1"
                      >
                        Statement <ChevronRight className="w-3.5 h-3.5" />
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
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-rose-50 text-rose-700 border border-rose-200 rounded-lg text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Startup Borrower *</label>
          <select
            value={businessId}
            onChange={(e) => setBusinessId(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:ring-2 focus:ring-teal-500/20"
            required
          >
            <option value="">Select Startup</option>
            {borrowers.map((b) => (
              <option key={b.business_id} value={b.business_id}>
                {b.company_name} (Outstanding: €{(b.outstanding_balance_eur || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} / {(b.outstanding_balance_jod || 0).toLocaleString('en-US', { minimumFractionDigits: 3 })} JOD)
              </option>
            ))}
          </select>
        </div>

        {selectedBorrower && (
          <div className="p-3 bg-teal-50/60 rounded-lg border border-teal-100 text-xs text-teal-900 space-y-1">
            <div className="flex justify-between font-medium">
              <span>Approved Facility:</span>
              <span className="font-bold">€{(selectedBorrower.loan_approved_eur || 0).toLocaleString()} ({(selectedBorrower.loan_approved_jod || 0).toLocaleString()} JOD)</span>
            </div>
            <div className="flex justify-between text-teal-800">
              <span>Total Repaid to Date:</span>
              <span className="font-semibold">€{(selectedBorrower.total_repaid_eur || 0).toLocaleString()}</span>
            </div>
            <div className="flex justify-between font-bold text-teal-950 pt-1 border-t border-teal-200/50">
              <span>Outstanding Balance:</span>
              <span>€{(selectedBorrower.outstanding_balance_eur || 0).toLocaleString()} ({(selectedBorrower.outstanding_balance_jod || 0).toLocaleString()} JOD)</span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Date *</label>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Method</label>
            <select
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20"
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

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-1">
            <label className="block text-xs font-semibold text-slate-700 mb-1">Amount (EUR) *</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              placeholder="e.g. 1000.00"
              value={amountEur}
              onChange={(e) => setAmountEur(e.target.value)}
              className="w-full text-sm font-bold border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20"
              required
            />
          </div>

          <div className="col-span-1">
            <label className="block text-xs font-semibold text-slate-700 mb-1">FX Rate (EUR➔JOD)</label>
            <input
              type="number"
              step="0.0001"
              value={exchangeRate}
              onChange={(e) => setExchangeRate(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20"
            />
          </div>

          <div className="col-span-1">
            <label className="block text-xs font-semibold text-slate-700 mb-1">Equivalent (JOD)</label>
            <div className="p-2 bg-slate-100 rounded-lg border border-slate-200 text-sm font-bold text-emerald-800 flex items-center h-[38px]">
              {calculatedJod} JOD
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Bank Reference / Receipt #</label>
          <input
            type="text"
            placeholder="e.g. TRX-987654321"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20 font-mono"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Notes / Description</label>
          <textarea
            rows={2}
            placeholder="Additional details regarding this repayment tranche..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-teal-500/20"
          />
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors shadow-xs"
          >
            {submitting ? 'Recording...' : 'Record Payment Receipt'}
          </button>
        </div>
      </form>
    </Modal>
  )
}


// Sub-component: Startup Statement Modal
function StartupStatementModal({ branchId, businessId, onClose, onRecordPay }) {
  const { data: stmt, loading } = useFetch(branchId && businessId ? `/repayments/${branchId}/startup/${businessId}/statement/` : null)

  if (loading || !stmt) {
    return (
      <Modal title="Startup Loan Account Statement" onClose={onClose} wide>
        <div className="p-8 text-center text-slate-400">Loading statement details...</div>
      </Modal>
    )
  }

  return (
    <Modal title={`Loan Statement: ${stmt.business_name || 'Startup'}`} onClose={onClose} wide>
      <div className="space-y-5 max-w-2xl">
        {/* Startup Overview Header */}
        <div className="bg-slate-900 text-white p-4 rounded-xl shadow-xs space-y-3">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] uppercase font-bold tracking-wider text-teal-400">{stmt.program_name}</span>
              <h2 className="text-xl font-bold">{stmt.business_name}</h2>
              {stmt.founders?.length > 0 && (
                <p className="text-xs text-slate-300">Founders: {stmt.founders.join(', ')}</p>
              )}
            </div>
            <button
              onClick={onRecordPay}
              className="px-3 py-1.5 bg-teal-500 hover:bg-teal-600 text-white text-xs font-bold rounded-lg shadow-xs transition-all flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Record Payment
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-800 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px]">Loan Facility:</span>
              <span className="font-bold text-white">€{(stmt.loan_approved_eur || 0).toLocaleString()}</span>
              <span className="text-[10px] text-slate-400 block">{(stmt.loan_approved_jod || 0).toLocaleString()} JOD</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px]">Total Repaid:</span>
              <span className="font-bold text-emerald-400">€{(stmt.total_repaid_eur || 0).toLocaleString()}</span>
              <span className="text-[10px] text-emerald-500/80 block">{(stmt.total_repaid_jod || 0).toLocaleString()} JOD</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px]">Outstanding Balance:</span>
              <span className="font-bold text-amber-400">€{(stmt.outstanding_balance_eur || 0).toLocaleString()}</span>
              <span className="text-[10px] text-amber-500/80 block">{(stmt.outstanding_balance_jod || 0).toLocaleString()} JOD</span>
            </div>
          </div>
        </div>

        {/* Transaction History */}
        <div>
          <h3 className="text-sm font-bold text-slate-900 mb-2">Payment Transaction History</h3>
          {(!stmt.repayments || stmt.repayments.length === 0) ? (
            <div className="p-6 bg-slate-50 border border-slate-200 rounded-lg text-center text-xs text-slate-500">
              No repayment transactions logged for this startup yet.
            </div>
          ) : (
            <div className="border border-slate-200 rounded-lg overflow-hidden text-xs">
              <table className="w-full text-left">
                <thead className="bg-slate-50 font-semibold text-slate-600 border-b border-slate-200">
                  <tr>
                    <th className="p-2.5">Date</th>
                    <th className="p-2.5">EUR Amount</th>
                    <th className="p-2.5">JOD Equivalent</th>
                    <th className="p-2.5">Method & Ref</th>
                    <th className="p-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {stmt.repayments.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-50/80">
                      <td className="p-2.5 font-medium text-slate-800">{r.payment_date}</td>
                      <td className="p-2.5 font-bold text-slate-900">€{(r.amount_eur || 0).toLocaleString()}</td>
                      <td className="p-2.5 font-semibold text-emerald-700">{(r.amount_jod || 0).toLocaleString()} JOD</td>
                      <td className="p-2.5">
                        <span>{r.payment_method}</span>
                        {r.reference_number && <span className="text-[10px] text-slate-400 font-mono block">{r.reference_number}</span>}
                      </td>
                      <td className="p-2.5 font-bold text-emerald-700 uppercase text-[10px]">{r.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-rose-50 text-rose-700 border border-rose-200 rounded-lg text-xs">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Date</label>
            <input
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Method</label>
            <select
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2"
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

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Amount (EUR)</label>
            <input
              type="number"
              step="0.01"
              value={amountEur}
              onChange={(e) => setAmountEur(e.target.value)}
              className="w-full text-sm font-bold border border-slate-200 rounded-lg p-2"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Exchange Rate (EUR/JOD)</label>
            <input
              type="number"
              step="0.0001"
              value={exchangeRate}
              onChange={(e) => setExchangeRate(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg p-2"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Reference Number</label>
          <input
            type="text"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2 font-mono"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Notes</label>
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2"
          />
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white rounded-lg"
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
      <div className="space-y-4 max-w-xl">
        {/* Template Download Card */}
        <div className="p-3.5 bg-teal-50/70 border border-teal-200/80 rounded-xl flex items-center justify-between gap-3">
          <div>
            <h4 className="text-xs font-bold text-teal-900">Need the standard spreadsheet format?</h4>
            <p className="text-[11px] text-teal-700 mt-0.5">
              Download the pre-filled template containing all active startup borrowers in this branch.
            </p>
          </div>
          <button
            type="button"
            onClick={downloadTemplate}
            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-white text-teal-800 hover:bg-teal-100/50 border border-teal-300 rounded-lg text-xs font-semibold shadow-2xs transition-all"
          >
            <Download className="w-3.5 h-3.5 text-teal-600" /> Download Template
          </button>
        </div>

        {error && (
          <div className="p-3 bg-rose-50 text-rose-700 border border-rose-200 rounded-lg text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Results Feedback */}
        {result ? (
          <div className="space-y-3">
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-950 space-y-2">
              <div className="flex items-center gap-2 font-bold text-sm text-emerald-800">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                Import Complete!
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs">
                <div className="bg-white/80 p-2 rounded-lg border border-emerald-100">
                  <span className="text-[10px] text-slate-500 block">New Payments</span>
                  <span className="font-bold text-emerald-700 text-sm">{result.imported_count}</span>
                </div>
                <div className="bg-white/80 p-2 rounded-lg border border-emerald-100">
                  <span className="text-[10px] text-slate-500 block">Updated Payments</span>
                  <span className="font-bold text-teal-700 text-sm">{result.updated_count}</span>
                </div>
                <div className="bg-white/80 p-2 rounded-lg border border-emerald-100">
                  <span className="text-[10px] text-slate-500 block">Total EUR</span>
                  <span className="font-bold text-slate-900 text-sm">€{result.total_amount_eur.toLocaleString()}</span>
                </div>
                <div className="bg-white/80 p-2 rounded-lg border border-emerald-100">
                  <span className="text-[10px] text-slate-500 block">Total JOD</span>
                  <span className="font-bold text-emerald-700 text-sm">{result.total_amount_jod.toLocaleString()} JOD</span>
                </div>
              </div>
            </div>

            {result.errors && result.errors.length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs space-y-1">
                <div className="font-bold text-amber-900 flex items-center gap-1.5">
                  <AlertCircle className="w-4 h-4 text-amber-600" />
                  {result.errors.length} Warnings / Skipped Rows:
                </div>
                <ul className="list-disc list-inside text-amber-800 space-y-0.5 max-h-32 overflow-y-auto pl-1">
                  {result.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onSuccess}
                className="px-4 py-2 text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors shadow-xs"
              >
                Done & View Repayments
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* File Drop Zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`p-6 border-2 border-dashed rounded-xl text-center cursor-pointer transition-all ${
                dragOver ? 'border-teal-500 bg-teal-50/50' : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
              }`}
              onClick={() => document.getElementById('repayment-file-input')?.click()}
            >
              <input
                id="repayment-file-input"
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <Upload className="w-8 h-8 mx-auto text-slate-400 mb-2" />
              {file ? (
                <div>
                  <p className="text-xs font-bold text-slate-900">{file.name}</p>
                  <p className="text-[11px] text-slate-500">{(file.size / 1024).toFixed(1)} KB — Click to change file</p>
                </div>
              ) : (
                <div>
                  <p className="text-xs font-semibold text-slate-700">Click to browse or drag and drop spreadsheet</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">Supports Microsoft Excel (.xlsx, .xls) and CSV (.csv)</p>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!file || uploading}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white rounded-lg transition-colors shadow-xs"
              >
                <Upload className="w-3.5 h-3.5" />
                {uploading ? 'Processing Spreadsheet...' : 'Upload & Process Repayments'}
              </button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  )
}
