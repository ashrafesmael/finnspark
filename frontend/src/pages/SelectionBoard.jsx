import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, StatusPill, Modal } from '../components/ui'
import api from '../api'

export default function SelectionBoard() {
  const { branch, can } = useAuth()
  const [stage, setStage] = useState('')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [minScore, setMinScore] = useState('')
  const [registered, setRegistered] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const pageSize = 15

  const { data: stages } = useFetch(branch ? `/stages/${branch.id}/` : null)
  const { data: statuses } = useFetch('/applicant-statuses/')
  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (stage) qs.set('stage', stage)
  if (search) qs.set('search', search)
  if (status) qs.set('status', status)
  if (minScore) qs.set('min_score', minScore)
  if (registered) qs.set('registered', registered)

  const list = useFetch(branch && can('selections.view') ? `/v2/applicants/${branch.id}/?${qs}` : null)

  return (
    <div>
      <div className="row spread wrap">
        <div className="tabs sub-tabs">
          <button className={`tab ${stage === '' ? 'active' : ''}`}
                  onClick={() => { setStage(''); setPage(1) }}>
            All applicants
          </button>
          {(stages || []).map((s) => (
            <button key={s.id} className={`tab ${String(stage) === String(s.id) ? 'active' : ''}`}
                    onClick={() => { setStage(s.id); setPage(1) }}>{s.name}</button>
          ))}
        </div>
      </div>

      <div className="filters row wrap">
        <input placeholder="Search business / founder…" value={search}
               onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {(statuses || []).map((s) => <option key={s.id} value={s.code_name}>{s.name}</option>)}
        </select>
        <select value={minScore} onChange={(e) => setMinScore(e.target.value)}>
          <option value="">Any score</option>
          {[40, 50, 60, 70, 80].map((n) => <option key={n} value={n}>{n}+</option>)}
        </select>
        <select value={registered} onChange={(e) => setRegistered(e.target.value)}>
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

  useEffect(() => {
    setInviteLink(null); setInviteEmail(null); setInviteError(null); setCopiedInvite(false); setInviteSent(null)
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

  return (
    <Modal title={`${a.business_name || ''} — ${a.first_name} ${a.last_name}`} onClose={onClose} wide>
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
    </Modal>
  )

  function can_score() { return true }
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
