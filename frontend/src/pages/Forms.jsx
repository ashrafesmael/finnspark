import { useEffect } from 'react'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, StatusPill, Modal } from '../components/ui'
import api from '../api'

const FIELD_TYPES = ['header', 'input', 'poll', 'multi_poll', 'spinner', 'file', 'date',
                     'number', 'long_text']

export default function Forms() {
  const [tab, setTab] = useState(0)
  return (
    <div>
      <div className="tabs">
        <button className={`tab ${tab === 0 ? 'active' : ''}`} onClick={() => setTab(0)}>
          Application forms
        </button>
        <button className={`tab ${tab === 1 ? 'active' : ''}`} onClick={() => setTab(1)}>
          Scoring forms
        </button>
      </div>
      {tab === 0 && <ApplicationForms kind="application" />}
      {tab === 1 && <ScoringForms />}
    </div>
  )
}

let _publicBaseCache = null
function usePublicBaseUrl() {
  // canonical shareable origin comes from the backend (PUBLIC_BASE_URL);
  // falls back to the current origin for local/dev setups without it
  const [base, setBase] = useState(_publicBaseCache || window.location.origin)
  useEffect(() => {
    if (_publicBaseCache) return
    api.get('/config/').then((r) => {
      if (r.data?.public_base_url) {
        _publicBaseCache = r.data.public_base_url
        setBase(_publicBaseCache)
      }
    }).catch(() => {})
  }, [])
  return base
}

export function ApplicationForms({ kind = 'application' } = {}) {
  const { branch } = useAuth()
  const [edit, setEdit] = useState(null)
  const [copiedId, setCopiedId] = useState(null)
  const base = kind === 'investment' ? 'investment-application-forms' : 'application-forms'
  const { data, reload } = useFetch(branch ? `/${base}/${branch.id}/?page_size=100` : null)
  const publicBase = usePublicBaseUrl()

  const publicUrl = (formId) => `${publicBase}/apply/${formId}`

  async function copyText(text) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        // fallback for non-secure contexts (plain HTTP on a remote IP)
        const ta = document.createElement('textarea')
        ta.value = text
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      return true
    } catch {
      return false
    }
  }

  const copyLink = async (r) => {
    const ok = await copyText(publicUrl(r.id))
    if (ok) {
      setCopiedId(r.id)
      setTimeout(() => setCopiedId(null), 2000)
    } else {
      window.prompt('Copy this link:', publicUrl(r.id))
    }
  }

  const emailLink = (r) => {
    const url = publicUrl(r.id)
    const subject = `Application invitation — ${r.name}`
    const body = `Hello,\n\nYou are invited to submit your application for "${r.name}".\n\n` +
      `Please complete the online application form here:\n${url}\n\n` +
      `The application takes about 15 minutes. We look forward to learning about your business.`
    return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
  }

  const columns = [
    { header: 'Form name', key: 'name' },
    { header: 'Programme', render: (r) => r.program_name || '—' },
    { header: 'Language', key: 'main_language' },
    { header: 'Fields', render: (r) => (r.fields || []).length },
    { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
    { header: '', render: (r) => (
      <span className="row gap">
        {kind === 'application' && r.status?.code_name === 'published' && (
          <span className="row gap">
            <button className="btn ghost sm" title={publicUrl(r.id)}
                    onClick={() => copyLink(r)}>
              {copiedId === r.id ? 'Copied ✓' : 'Copy link'}
            </button>
            <a className="btn ghost sm" href={emailLink(r)}
               title="Share by email">Email</a>
            <a className="btn ghost sm" href={`/apply/${r.id}`}
               target="_blank" rel="noreferrer" title="Preview the public form">Preview</a>
          </span>
        )}
        <button className="btn ghost sm" onClick={() => setEdit(r)}>Edit</button>
        <button className="btn ghost sm danger" onClick={async () => {
          if (confirm('Delete this form?')) {
            await api.delete(`/${base}/${branch.id}/${r.id}/`); reload()
          }
        }}>Delete</button>
      </span>
    )},
  ]

  return (
    <>
      <div className="toolbar row spread">
        <h3>{kind === 'investment' ? 'Investment forms' : 'Application forms'}</h3>
        <button className="btn primary sm" onClick={() => setEdit({})}>+ Create form</button>
      </div>
      <DataTable columns={columns} rows={data?.results || []} />
      {edit !== null && (
        <AppFormEditor initial={edit} branchId={branch.id} base={base}
                       onClose={() => setEdit(null)}
                       onSaved={() => { setEdit(null); reload() }} />
      )}
    </>
  )
}

function AppFormEditor({ initial, branchId, base = 'application-forms', onClose, onSaved }) {
  const [nameEn, setNameEn] = useState(initial?.name || '')
  const [desc, setDesc] = useState(initial?.form_description || '')
  const [status, setStatus] = useState(initial?.status?.code_name || 'draft')
  const [programId, setProgramId] = useState(initial?.program_id || '')
  const [fields, setFields] = useState(
    (initial?.fields || []).map((f) => ({
      name: f.name || '', field_type: f.field_type?.code_name || 'input',
      is_required: !!f.is_required,
      options: (f.options || []).map((o) => o.name),
    })),
  )
  const { data: programs } = useFetch(branchId ? `/programs/${branchId}/?page_size=100` : null)
  const { data: types } = useFetch('/field-types/')
  const typeMap = Object.fromEntries((types || []).map((t) => [t.code_name, t.id]))

  const setField = (i, patch) =>
    setFields(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)))

  const save = async () => {
    const payload = {
      name_i18n: { en: nameEn },
      form_description: desc,
      status,
      main_language: 'en',
      program_id: programId ? Number(programId) : null,
      fields: fields.map((f) => ({
        name_i18n: { en: f.name },
        field_type: typeMap[f.field_type],
        is_required: f.is_required,
        options: (f.options || []).map((o) => ({ name_i18n: { en: o } })),
      })),
    }
    if (initial?.id) await api.patch(`/${base}/${branchId}/${initial.id}/`, payload)
    else await api.post(`/${base}/${branchId}/`, payload)
    onSaved()
  }

  const needsOptions = ['poll', 'multi_poll', 'spinner']

  return (
    <Modal title={initial?.id ? `Edit form — ${initial.name}` : 'New application form'}
           onClose={onClose} wide>
      <div className="grid-2 gap">
        <label className="stacked">Form name (English)
          <input value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </label>
        <label className="stacked">Description
          <input value={desc} onChange={(e) => setDesc(e.target.value)} />
        </label>
        <label className="stacked">Programme
          <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
            <option value="">—</option>
            {(programs?.results || []).map((p) =>
              <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label className="stacked">Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
        </label>
      </div>

      <h4>Fields</h4>
      <div className="builder">
        {fields.map((f, i) => (
          <div key={i} className="field-row card-flat">
            <input placeholder="Label" value={f.name}
                   onChange={(e) => setField(i, { name: e.target.value })} />
            <select value={f.field_type}
                    onChange={(e) => setField(i, { field_type: e.target.value })}>
              {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <label className="choice">
              <input type="checkbox" checked={f.is_required}
                     onChange={(e) => setField(i, { is_required: e.target.checked })} /> required
            </label>
            {needsOptions.includes(f.field_type) && (
              <input placeholder="Options, comma separated"
                     value={(f.options || []).join(', ')}
                     onChange={(e) => setField(i, { options:
                       e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
            )}
            <button className="icon-btn" onClick={() =>
              setFields(fields.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn ghost sm" onClick={() =>
          setFields([...fields, { name: '', field_type: 'input', is_required: false, options: [] }])}>
          + Add field
        </button>
      </div>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!nameEn}>Save form</button>
      </div>
    </Modal>
  )
}

function ScoringForms() {
  const { branch } = useAuth()
  const [edit, setEdit] = useState(null)
  const { data, reload } = useFetch(branch ? `/scoring-forms/${branch.id}/?page_size=100` : null)

  return (
    <>
      <div className="toolbar row spread">
        <h3>Scoring forms</h3>
        <button className="btn primary sm" onClick={() => setEdit({})}>+ Create scoring form</button>
      </div>
      <DataTable
        columns={[
          { header: 'Form', render: (r) => r.name },
          { header: 'Graduation', render: (r) => (r.is_for_graduation ? 'Yes' : 'No') },
          { header: 'Questions', render: (r) => (r.questions || []).length },
          { header: 'Total weight', render: (r) =>
              `${(r.questions || []).reduce((s, q) => s + (q.weightage || 0), 0).toFixed(0)}%` },
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
          { header: '', render: (r) => (
            <span className="row gap">
              <button className="btn ghost sm" onClick={() => setEdit(r)}>Edit</button>
            </span>
          )},
        ]}
        rows={data?.results || []}
      />
      {edit !== null && (
        <ScoringFormEditor initial={edit} branchId={branch.id}
                           onClose={() => setEdit(null)}
                           onSaved={() => { setEdit(null); reload() }} />
      )}
    </>
  )
}

function ScoringFormEditor({ initial, branchId, onClose, onSaved }) {
  const [name, setName] = useState(initial?.name || '')
  const [graduation, setGraduation] = useState(!!initial?.is_for_graduation)
  const [status, setStatus] = useState(initial?.status?.code_name || 'draft')
  const [questions, setQuestions] = useState((initial?.questions || []).map((q) => ({
    name: q.name, description: q.description || '', weightage: q.weightage || 0,
  })))
  const { data: stages } = useFetch(branchId ? `/stages/${branchId}/` : null)
  const { data: programs } = useFetch(branchId ? `/programs/${branchId}/?page_size=100` : null)
  const [stageId, setStageId] = useState(initial?.selection_stage_id || '')
  const [programId, setProgramId] = useState(initial?.program_id || '')

  const totalW = questions.reduce((s, q) => s + Number(q.weightage || 0), 0)

  const save = async () => {
    const payload = {
      name_i18n: { en: name }, is_for_graduation: graduation, status,
      program_id: programId ? Number(programId) : null,
      selection_stage_id: stageId ? Number(stageId) : null,
      questions: questions.map((q) => ({ ...q, weightage: Number(q.weightage) })),
    }
    if (initial?.id) await api.patch(`/scoring-forms/${branchId}/${initial.id}/`, payload)
    else await api.post(`/scoring-forms/${branchId}/`, payload)
    onSaved()
  }

  return (
    <Modal title={initial?.id ? `Edit — ${initial.name}` : 'New scoring form'} onClose={onClose} wide>
      <div className="grid-2 gap">
        <label className="stacked">Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="choice pad-top">
          <input type="checkbox" checked={graduation}
                 onChange={(e) => setGraduation(e.target.checked)} /> is_for_graduation
        </label>
        {!graduation && (
          <label className="stacked">Selection stage
            <select value={stageId} onChange={(e) => setStageId(e.target.value)}>
              <option value="">Any stage</option>
              {(stages || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
        )}
        <label className="stacked">Programme
          <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
            <option value="">—</option>
            {(programs?.results || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label className="stacked">Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
        </label>
      </div>
      <h4>Questions — total weight {totalW.toFixed(0)}%</h4>
      {questions.map((q, i) => (
        <div key={i} className="field-row card-flat">
          <input placeholder="Question" value={q.name}
                 onChange={(e) => setQuestions(questions.map((x, j) =>
                   j === i ? { ...x, name: e.target.value } : x))} />
          <input type="number" min="0" max="100" style={{ maxWidth: 90 }} value={q.weightage}
                 onChange={(e) => setQuestions(questions.map((x, j) =>
                   j === i ? { ...x, weightage: e.target.value } : x))} /> %
          <button className="icon-btn" onClick={() =>
            setQuestions(questions.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="btn ghost sm" onClick={() =>
        setQuestions([...questions, { name: '', weightage: 10 }])}>+ Add question</button>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!name}>Save</button>
      </div>
    </Modal>
  )
}
