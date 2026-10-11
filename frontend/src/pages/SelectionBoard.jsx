import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, StatusPill, Modal } from '../components/ui'
import api from '../api'

export default function SelectionBoard() {
  const { branch, can } = useAuth()
  const [stage, setStage] = useState('')
  const [program, setProgram] = useState('')
  const [viewBy, setViewBy] = useState('stage') // 'stage' | 'program'
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [minScore, setMinScore] = useState('')
  const [registered, setRegistered] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const pageSize = 15

  const { data: stages } = useFetch(branch ? `/stages/${branch.id}/` : null)
  const { data: statuses } = useFetch('/applicant-statuses/')
  const { data: programsRes } = useFetch(branch ? `/programs/${branch.id}/?page_size=100` : null)
  const rawPrograms = programsRes?.results || (Array.isArray(programsRes) ? programsRes : [])
  const programs = rawPrograms
    .filter((p) => p.businesses_count > 0 || (p.name && p.name.toLowerCase().includes('cohort')))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))

  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (stage) qs.set('stage', stage)
  if (program) qs.set('program', program)
  if (search) qs.set('search', search)
  if (status) qs.set('status', status)
  if (minScore) qs.set('min_score', minScore)
  if (registered) qs.set('registered', registered)

  const list = useFetch(branch && can('selections.view') ? `/v2/applicants/${branch.id}/?${qs}` : null)

  return (
    <div>
      {/* Select By Stage vs Program toggle */}
      <div className="row spread wrap center" style={{ marginBottom: 10, gap: 12 }}>
        <div className="row center wrap" style={{ gap: 8 }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Select By:
          </span>
          <div style={{ display: 'inline-flex', background: '#eef2f5', borderRadius: 6, padding: 2 }}>
            <button
              id="select-by-stage"
              className={`btn sm ${viewBy === 'stage' ? 'primary' : 'ghost'}`}
              style={{ padding: '3px 12px', fontSize: '0.82rem', borderRadius: 4, height: 'auto' }}
              onClick={() => setViewBy('stage')}
            >
              Stage
            </button>
            <button
              id="select-by-program"
              className={`btn sm ${viewBy === 'program' ? 'primary' : 'ghost'}`}
              style={{ padding: '3px 12px', fontSize: '0.82rem', borderRadius: 4, height: 'auto' }}
              onClick={() => setViewBy('program')}
            >
              Program / Cohort
            </button>
          </div>
        </div>

        {(stage || program || status || search || minScore || registered) && (
          <button
            id="btn-reset-filters"
            className="btn ghost sm"
            style={{ fontSize: '0.78rem', padding: '2px 8px', color: 'var(--bad)' }}
            onClick={() => {
              setStage('')
              setProgram('')
              setStatus('')
              setSearch('')
              setMinScore('')
              setRegistered('')
              setPage(1)
            }}
          >
            ✕ Reset Filters
          </button>
        )}
      </div>

      <div className="row spread wrap">
        <div className="tabs sub-tabs">
          {viewBy === 'stage' ? (
            <>
              <button className={`tab ${stage === '' ? 'active' : ''}`}
                      onClick={() => { setStage(''); setPage(1) }}>
                All Stages
              </button>
              {(stages || []).map((s) => (
                <button key={s.id} className={`tab ${String(stage) === String(s.id) ? 'active' : ''}`}
                        onClick={() => { setStage(String(s.id)); setPage(1) }}>{s.name}</button>
              ))}
            </>
          ) : (
            <>
              <button className={`tab ${program === '' ? 'active' : ''}`}
                      onClick={() => { setProgram(''); setPage(1) }}>
                All Cohorts
              </button>
              {(programs || []).map((p) => (
                <button key={p.id} className={`tab ${String(program) === String(p.id) ? 'active' : ''}`}
                        onClick={() => { setProgram(String(p.id)); setPage(1) }}>{p.name}</button>
              ))}
            </>
          )}
        </div>
      </div>

      <div className="filters row wrap">
        <input placeholder="Search business / founder…" value={search}
               onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <select id="filter-program" value={program} onChange={(e) => { setProgram(e.target.value); setPage(1) }}>
          <option value="">All programs / cohorts</option>
          {(programs || []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select id="filter-stage" value={stage} onChange={(e) => { setStage(e.target.value); setPage(1) }}>
          <option value="">All stages</option>
          {(stages || []).map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">All statuses</option>
          {(statuses || []).map((s) => <option key={s.id} value={s.code_name}>{s.name}</option>)}
        </select>
        <select value={minScore} onChange={(e) => { setMinScore(e.target.value); setPage(1) }}>
          <option value="">Any score</option>
          {[40, 50, 60, 70, 80].map((n) => <option key={n} value={n}>{n}+</option>)}
        </select>
        <select value={registered} onChange={(e) => { setRegistered(e.target.value); setPage(1) }}>
          <option value="">All registrations</option>
          <option value="true">Registered</option>
          <option value="false">Not registered</option>
        </select>
      </div>

      <DataTable
        columns={[
          { header: 'Business/Project', key: 'business_name' },
          { header: 'Founder', render: (r) => `${r.first_name} ${r.last_name}` },
          { header: 'Program', key: 'program_name' },
          { header: 'Stage', render: (r) => r.selection_stage?.name || '—' },
          { header: 'Eval. by me', render: (r) => r.evaluated_by_me ? 'Yes' : 'No' },
          { header: 'Status', render: (r) => r.status && <StatusPill codeName={r.status.code_name} name={r.status.name} /> },
          { header: 'Registered', render: (r) => r.registered ? 'Yes' : 'No' },
          { header: 'Avg score', render: (r) => r.average_score != null ? r.average_score.toFixed(1) : '—' },
          { header: 'Applied', render: (r) => (r.application_date || '').slice(0, 10) },
          { header: '', render: (r) => <button className="btn ghost sm" onClick={() => setSelectedId(r.id)}>Open</button> },
        ]}
        rows={list.data?.results || []}
        footer={
          <Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />
        }
      />

      {selectedId && (
        <ApplicantDrawer id={selectedId} branchId={branch.id}
                         stages={stages || []} statuses={statuses || []}
                         onClose={() => setSelectedId(null)} />
      )}
    </div>
  )
}

function ApplicantDrawer({ id, branchId, stages, statuses, onClose }) {
  const { data: a, reload } = useFetch(branchId ? `/applicants/${branchId}/${id}/` : null)
  const [scores, setScores] = useState({})
  const [formId, setFormId] = useState('')
  const [inviting, setInviting] = useState(false)
  const [inviteLink, setInviteLink] = useState(null)
  const [inviteEmail, setInviteEmail] = useState(null)
  const [inviteError, setInviteError] = useState(null)
  const [inviteSent, setInviteSent] = useState(null)
  const [copiedInvite, setCopiedInvite] = useState(false)
  const [activeTab, setActiveTab] = useState('application') // 'application' | 'disbursements'

  useEffect(() => {
    setInviteLink(null); setInviteEmail(null); setInviteError(null); setCopiedInvite(false); setInviteSent(null); setActiveTab('application')
  }, [id])

  const moveStage = async (sid) => {
    await api.patch(`/applicants/${branchId}/${id}/`, { selection_stage_id: Number(sid) })
    reload()
  }
  const setStatus = async (code) => {
    await api.patch(`/applicants/${branchId}/${id}/`, { status: code })
    reload()
  }
  const submitScore = async () => {
    if (!formId) return
    const answers = Object.entries(scores).map(([qid, v]) => ({ question_id: Number(qid), score: Number(v) }))
    await api.post(`/applicants/${branchId}/${id}/score/`,
                   { scoring_form_id: Number(formId), answers })
    setScores({}); setFormId(''); reload()
  }

  if (!a) return null
  const form = (a.scoring_forms || []).find((f) => String(f.id) === String(formId))
  const disbCount = (a.disbursements || []).length
  const totalDisbursed = a.total_disbursed || 0

  return (
    <Modal title={`${a.business_name || ''} — ${a.first_name} ${a.last_name}`} onClose={onClose} wide>
      {/* Option bar to switch between Application details and Disbursements */}
      <div className="row spread center wrap" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 8, marginBottom: 16, gap: 10 }}>
        <div className="tabs sub-tabs" style={{ margin: 0, borderBottom: 'none' }}>
          <button
            className={`tab ${activeTab === 'application' ? 'active' : ''}`}
            onClick={() => setActiveTab('application')}
          >
            Application & Evaluation
          </button>
          <button
            id="tab-startup-disbursements"
            className={`tab ${activeTab === 'disbursements' ? 'active' : ''}`}
            onClick={() => setActiveTab('disbursements')}
          >
            💳 Disbursements ({disbCount})
          </button>
        </div>
        {activeTab === 'application' && (
          <button
            id="btn-view-disbursements-header"
            className="btn secondary sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            onClick={() => setActiveTab('disbursements')}
          >
            <span>💳 View Disbursements ({disbCount})</span>
            {totalDisbursed > 0 && (
              <span className="badge-pill" style={{ background: '#e6f4ec', color: '#2f7d51', fontWeight: 700, padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem' }}>
                €{totalDisbursed.toLocaleString()}
              </span>
            )}
          </button>
        )}
      </div>

      {activeTab === 'disbursements' ? (
        <StartupDisbursementsView applicant={a} onBack={() => setActiveTab('application')} />
      ) : (
        <div className="grid-2 gap">
          <div>
            <h4>Application answers</h4>
            <AnswerTable answers={a.answers} labels={a.answer_labels} />
            <p className="muted sm">Email: {a.email} · Age: {a.age ?? '—'} · Applied {(a.application_date || '').slice(0, 10)}</p>
            <h4>Evaluations ({(a.evaluations || []).length})</h4>
            {(a.evaluations || []).map((e) => (
              <div key={e.id} className="chip-row">
                Score {e.total_score}% · by user #{e.evaluator_id} · {e.created_at.slice(0, 10)}
              </div>
            ))}
          </div>
          <div>
            <h4>Pipeline</h4>
            <label className="stacked">Stage
              <select value={a.selection_stage_id || ''} onChange={(e) => moveStage(e.target.value)}>
                {stages.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <label className="stacked">Status
              <select value={a.status?.code_name || ''} onChange={(e) => setStatus(e.target.value)}>
                {statuses.map((s) => <option key={s.id} value={s.code_name}>{s.name}</option>)}
              </select>
            </label>

            {/* Quick Disbursements Option Card */}
            <div className="card" style={{ marginTop: 14, padding: '12px 14px', background: '#f8fbfc', border: '1px solid #d0e2e5', borderRadius: 8 }}>
              <div className="row spread center wrap" style={{ gap: 8 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--accent-strong)' }}>
                    Startup Disbursements
                  </div>
                  <div className="muted sm" style={{ marginTop: 2 }}>
                    {disbCount > 0
                      ? `${disbCount} payment items · Total: €${totalDisbursed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EUR`
                      : 'No disbursements recorded yet.'}
                  </div>
                </div>
                <button
                  id="btn-pipeline-disbursements"
                  className="btn primary sm"
                  onClick={() => setActiveTab('disbursements')}
                >
                  View Disbursements →
                </button>
              </div>
            </div>

            {!a.registered && (
              <div style={{ marginTop: 12 }}>
                <button className="btn ghost sm" disabled={inviting} onClick={async () => {
                  setInviting(true); setInviteError(null)
                  try {
                    const res = await api.post(`/applicants/${branchId}/${id}/invite/`)
                    setInviteLink(res.data.invite_url)
                    setInviteEmail(res.data.email)
                    setInviteSent(res.data.email_sent)
                    reload()
                  } catch (e) {
                    setInviteError(e.response?.data?.detail || 'Could not generate invitation.')
                  } finally { setInviting(false) }
                }}>{inviting ? 'Generating…' : 'Invite founder to register'}</button>

                {inviteError && <div className="alert" style={{ marginTop: 8 }}>{inviteError}</div>}

                {inviteLink && (
                  <div className="invite-box" style={{ marginTop: 8 }}>
                    {inviteSent === true && (
                      <div className="alert" style={{ background: '#e6f4ec', borderColor: '#52bc7e', marginBottom: 8 }}>
                        ✓ Invitation email sent to <b>{inviteEmail}</b>
                      </div>
                    )}
                    {inviteSent === false && (
                      <p className="muted sm">
                        SMTP not configured — email not sent automatically.
                        Invitation link for <b>{inviteEmail}</b> (valid 14 days).
                        Copy it or open your email client:
                      </p>
                    )}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button className="btn primary sm" onClick={() => {
                        navigator.clipboard?.writeText(inviteLink)
                        setCopiedInvite(true)
                        setTimeout(() => setCopiedInvite(false), 1500)
                      }}>{copiedInvite ? 'Copied ✓' : 'Copy link'}</button>
                      <a className="btn ghost sm" href={`mailto:${inviteEmail}?subject=${encodeURIComponent(
                        'Your finnspark founder account invitation'
                      )}&body=${encodeURIComponent(
                        `Hello,

Please create your founder account using this link (valid 14 days):
${inviteLink}

Welcome aboard!`
                      )}`}>Email link</a>
                    </div>
                    <p className="muted sm" style={{ wordBreak: 'break-all', marginTop: 6 }}>{inviteLink}</p>
                  </div>
                )}

                {!inviteLink && a.invited_at && (
                  <p className="muted sm" style={{ marginTop: 6 }}>
                    Previously invited {(a.invited_at || '').slice(0, 10)} — generate a new link any time.
                  </p>
                )}
              </div>
            )}
            {a.registered && <p className="muted sm" style={{ marginTop: 8 }}>✓ Founder has registered their account.</p>}
            {can_score() && (
              <>
                <h4>Score applicant</h4>
                <select value={formId} onChange={(e) => setFormId(e.target.value)}>
                  <option value="">Choose scoring form…</option>
                  {(a.scoring_forms || []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  {(a.graduation_forms || []).map((f) =>
                    <option key={f.id} value={f.id}>{f.name} (graduation)</option>)}
                </select>
                {form && (
                  <div className="scoring">
                    {form.questions?.map((q) => (
                      <label key={q.id} className="stacked">
                        {q.name} ({q.weightage.toFixed(0)}%)
                        <select value={scores[q.id] ?? ''}
                                onChange={(e) => setScores({ ...scores, [q.id]: e.target.value })}>
                          <option value="">Rate…</option>
                          {[...Array(11).keys()].reverse().map((n) =>
                            <option key={n} value={n}>{n}</option>)}
                        </select>
                      </label>
                    ))}
                    <button className="btn primary sm" onClick={submitScore}>Submit evaluation</button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  )

  function can_score() { return true }
}

function StartupDisbursementsView({ applicant, onBack }) {
  const items = applicant.disbursements || []
  const totalEur = applicant.total_disbursed_eur || applicant.total_disbursed || 0
  const totalJod = applicant.total_disbursed_jod || items.reduce((acc, it) => acc + (it.amount_jod || (it.amount * (it.exchange_rate || 0.76))), 0)
  const uniquePrograms = Array.from(new Set(items.map((it) => it.program_name).filter(Boolean)))

  return (
    <div className="startup-disbursements-view">
      <div className="row spread center wrap" style={{ marginBottom: 14, gap: 8 }}>
        <div>
          <h4 style={{ margin: 0, color: 'var(--accent-strong)' }}>
            Disbursements for {applicant.business_name || 'Startup'}
          </h4>
          <p className="muted sm" style={{ margin: '2px 0 0' }}>
            Complete audit of all stipend, milestone voucher, and blended finance transactions in Base EUR and Disbursed JOD.
          </p>
        </div>
        <button className="btn ghost sm" onClick={onBack}>
          ← Back to Application
        </button>
      </div>

      {/* KPI Metric Tiles */}
      <div className="grid-3 tiles-row" style={{ marginBottom: 16 }}>
        <div className="card stat-tile" style={{ padding: '12px 16px' }}>
          <div className="stat-value" style={{ color: totalEur > 0 ? 'var(--ok)' : 'var(--text)', fontSize: '22px' }}>
            €{totalEur.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="stat-label">Total Base Amount (EUR)</div>
        </div>
        <div className="card stat-tile" style={{ padding: '12px 16px' }}>
          <div className="stat-value" style={{ color: totalJod > 0 ? '#0284c7' : 'var(--text)', fontSize: '22px' }}>
            {totalJod.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD
          </div>
          <div className="stat-label">Total Disbursed Equivalent (JOD)</div>
        </div>
        <div className="card stat-tile" style={{ padding: '12px 16px' }}>
          <div className="stat-value" style={{ fontSize: '22px' }}>{items.length}</div>
          <div className="stat-label">Transactions ({uniquePrograms.length || 1} Cohort{uniquePrograms.length > 1 ? 's' : ''})</div>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="card" style={{ padding: '36px 20px', textAlign: 'center' }}>
          <div style={{ fontSize: '2.4rem', marginBottom: 8 }}>💳</div>
          <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text)' }}>No Disbursements Found</div>
          <p className="muted sm" style={{ maxWidth: 440, margin: '6px auto 0' }}>
            No disbursements have been recorded for {applicant.business_name || 'this startup'} yet. Once payment batches are processed, they will automatically appear here.
          </p>
        </div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ maxHeight: 440, overflowY: 'auto' }}>
            <table className="data-table" style={{ width: '100%', margin: 0, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ width: 110, padding: '10px 12px', textAlign: 'left' }}>Disbursement Date</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left' }}>Program</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left' }}>Batch Title</th>
                  <th style={{ width: 115, padding: '10px 12px', textAlign: 'right' }}>Base Amount (EUR)</th>
                  <th style={{ width: 90, padding: '10px 12px', textAlign: 'center' }}>FX Rate</th>
                  <th style={{ width: 120, padding: '10px 12px', textAlign: 'right' }}>Disbursed (JOD)</th>
                  <th style={{ width: 90, padding: '10px 12px', textAlign: 'center' }}>Status</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left' }}>Notes</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const itEur = Number(it.amount_eur != null ? it.amount_eur : it.amount || 0)
                  const itRate = Number(it.exchange_rate || 0.76)
                  const itJod = Number(it.amount_jod != null ? it.amount_jod : (itEur * itRate))
                  const itDate = it.disbursement_date || it.payment_date || '—'

                  return (
                    <tr key={it.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ whiteSpace: 'nowrap', padding: '10px 12px', fontSize: '13px', fontWeight: 600 }}>
                        {itDate}
                      </td>
                      <td style={{ padding: '10px 12px', fontSize: '13px' }}>
                        <span className="badge-pill sm" style={{ background: '#eef2f6', color: '#334155', padding: '2px 8px', borderRadius: 4 }}>
                          {it.program_name || '—'}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', fontSize: '13px' }}>
                        <div style={{ fontWeight: 600, color: 'var(--accent-strong)' }}>{it.batch_title}</div>
                      </td>
                      <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700, fontSize: '13px', color: itEur > 0 ? 'var(--ok)' : 'var(--muted)' }}>
                        €{itEur.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td style={{ textAlign: 'center', padding: '10px 12px', fontSize: '12.5px', color: '#64748b' }}>
                        {itRate.toFixed(4)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700, fontSize: '13px', color: itJod > 0 ? '#0284c7' : 'var(--muted)' }}>
                        {itJod.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })} JOD
                      </td>
                      <td style={{ textAlign: 'center', padding: '10px 12px' }}>
                        <StatusPill codeName={it.status} name={it.status} />
                      </td>
                      <td className="muted sm" style={{ padding: '10px 12px', maxWidth: 220, fontSize: '12px' }}>
                        {it.notes || '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}


function formatAnswer(v) {
  if (v == null) return ''
  if (Array.isArray(v)) return v.join(', ')
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function AnswerTable({ answers = {}, labels = {} }) {
  const entries = Object.entries(answers)
  // labelled keys first (in form order), then any extras
  const ordered = [
    ...Object.keys(labels).filter((k) => k in answers),
    ...entries.map(([k]) => k).filter((k) => !(k in labels)),
  ]
  const pretty = (k) =>
    labels[k] || k.replace(/^field_/, '').replace(/_/g, ' ').trim() || k

  if (!ordered.length) return <p className="muted sm">No answers captured.</p>
  return (
    <table className="kv">
      <tbody>
        {ordered.map((k) => {
          const v = formatAnswer(answers[k])
          if (!v) return null
          return <tr key={k}><th>{pretty(k)}</th><td>{v}</td></tr>
        })}
      </tbody>
    </table>
  )
}
