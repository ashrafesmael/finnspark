import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal, StatusPill } from '../components/ui'
import api from '../api'

export default function Programs() {
  const { branch, can } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [edit, setEdit] = useState(null)
  const pageSize = 10

  const { data: types } = useFetch(branch ? `/program-types/${branch.id}/` : null)
  const list = useFetch(branch ? `/programs/${branch.id}/?page=${page}&page_size=${pageSize}&search=${search}` : null)

  return (
    <div>
      <h3>Program types</h3>
      <div className="type-cards">
        {(types || []).map((t) => (
          <div key={t.id} className="card type-card">
            <b>{t.name}</b>
            <span className="muted">{t.programs_count} programmes · {t.duration_months} months</span>
          </div>
        ))}
        {can('programs.edit') && (
          <button className="card type-card add" onClick={() => setEdit({ __type: true })}>
            + Manage types
          </button>
        )}
      </div>

      <div className="toolbar row spread">
        <h3>Programmes</h3>
        <div className="row gap">
          <input placeholder="Search…" value={search}
                 onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          {can('programs.edit') && (
            <button className="btn primary sm" onClick={() => setEdit({})}>+ Add program</button>
          )}
        </div>
      </div>

      <DataTable
        columns={[
          { header: 'Program', key: 'name' },
          { header: 'Type', render: (r) => r.program_type?.name || '—' },
          { header: 'Businesses', key: 'businesses_count' },
          { header: 'Courses', key: 'courses_count' },
          { header: 'Created', render: (r) => (r.creation_date || '').slice(0, 10) },
          { header: 'Scoring req.', render: (r) => (r.scoring_required ? 'Yes' : 'No') },
          { header: '', render: (r) => (
            <span className="row gap">
              <Link className="btn ghost sm" to={`/programs-courses/${r.id}`}>Open</Link>
              {can('programs.edit') && (
                <button className="btn ghost sm danger" onClick={async () => {
                  if (confirm('Delete programme?')) {
                    await api.delete(`/programs/${branch.id}/${r.id}/`); list.reload()
                  }
                }}>Delete</button>
              )}
            </span>
          )},
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />

      {edit?.__type && (
        <TypeEditor branchId={branch.id} onClose={() => setEdit(null)}
                    onSaved={() => { setEdit(null); types.reload && types.reload() }} />
      )}
      {edit !== null && !edit.__type && (
        <ProgramEditor initial={edit} branchId={branch.id}
                       onClose={() => setEdit(null)}
                       onSaved={() => { setEdit(null); list.reload() }} />
      )}
    </div>
  )
}

function TypeEditor({ branchId, onClose, onSaved }) {
  const [name, setName] = useState('')
  const [months, setMonths] = useState(6)
  const { data: types, reload } = useFetch(`/program-types/${branchId}/`)
  return (
    <Modal title="Programme types" onClose={onClose}>
      {(types || []).map((t) => (
        <div key={t.id} className="row spread card-flat">
          <span>{t.name}</span>
          <button className="btn ghost sm" onClick={() =>
            confirm(`Remove ${t.name}?`) && api.delete(`/program-types/${branchId}/${t.id}/`).then(reload)
          }>✕</button>
        </div>
      ))}
      <hr />
      <div className="row gap">
        <input placeholder="Type name" value={name} onChange={(e) => setName(e.target.value)} />
        <input type="number" min="1" max="36" value={months} style={{ width: 80 }}
               onChange={(e) => setMonths(e.target.value)} />
        <button className="btn primary sm" onClick={async () => {
          if (!name) return
          await api.post(`/program-types/${branchId}/`, { name, duration_months: Number(months) })
          setName(''); reload()
        }}>Add</button>
      </div>
      <div className="row end modal-foot"><button className="btn primary" onClick={onSaved}>Done</button></div>
    </Modal>
  )
}

function ProgramEditor({ initial, branchId, onClose, onSaved }) {
  const [name, setName] = useState(initial?.name || '')
  const [desc, setDesc] = useState(initial?.description || '')
  const [typeId, setTypeId] = useState(initial?.program_type?.id || '')
  const [scoringRequired, setScoringRequired] = useState(!!initial?.scoring_required)
  const { data: types } = useFetch(`/program-types/${branchId}/`)
  const { data: statuses } = useFetch(`/program-statuses/${branchId}/`)
  const [status, setStatus] = useState(
    initial?.status?.code_name || statuses?.find((s) => s.code_name === 'active')?.code_name || 'active')

  const save = async () => {
    const payload = {
      name, description: desc, program_type_id: typeId ? Number(typeId) : null,
      scoring_required: scoringRequired, status,
    }
    if (initial?.id) await api.patch(`/programs/${branchId}/${initial.id}/`, payload)
    else await api.post(`/programs/${branchId}/`, payload)
    onSaved()
  }

  return (
    <Modal title={initial?.id ? `Edit — ${initial.name}` : 'New programme'} onClose={onClose}>
      <label className="stacked">Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="stacked">Description<input value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
      <div className="grid-2 gap">
        <label className="stacked">Type
          <select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">—</option>
            {(types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label className="stacked">Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {(statuses || []).map((s) => <option key={s.id} value={s.code_name}>{s.name}</option>)}
          </select>
        </label>
      </div>
      <label className="choice">
        <input type="checkbox" checked={scoringRequired}
               onChange={(e) => setScoringRequired(e.target.checked)} /> Scoring required
      </label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!name}>Save</button>
      </div>
    </Modal>
  )
}

export { ProgramEditor }
