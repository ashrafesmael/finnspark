import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal } from '../components/ui'
import api from '../api'

export default function Announcements() {
  const { branch, can } = useAuth()
  const [page, setPage] = useState(1)
  const [edit, setEdit] = useState(null)   // {} = create, announcement object = edit
  const [view, setView] = useState(null)   // announcement being read
  const pageSize = 10
  const list = useFetch(branch ? `/announcements/${branch.id}/?page=${page}&page_size=${pageSize}` : null)
  const canEdit = can('announcements.edit')

  const react = async (a) => {
    await api.post(`/announcements/${branch.id}/${a.id}/react/`)
    list.reload()
  }

  const statusLabel = (r) => r.status_id === 1 ? 'Published' : 'Draft'

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Announcements</h3>
        {canEdit && (
          <button className="btn primary sm" onClick={() => setEdit({})}>+ Create announcement</button>
        )}
      </div>
      <DataTable
        columns={[
          { header: 'Announcement', render: (r) => (
              <a className="link-strong" style={{ cursor: 'pointer' }} onClick={() => setView(r)}>
                {r.title}
              </a>
            )},
          { header: 'Date', render: (r) => (r.published_at || '').slice(0, 16).replace('T', ' ') },
          { header: 'Reactions', render: (r) => (
            <button className={`btn ghost sm ${r.reacted ? 'primary' : ''}`} onClick={() => react(r)}>
              👏 {r.reactions_count}
            </button>
          )},
          { header: 'Status', render: statusLabel },
          ...(canEdit ? [{ header: 'Actions', render: (r) => (
            <button className="btn ghost sm" onClick={() => setEdit(r)}>Edit</button>
          )}] : []),
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />
      {view && (
        <Modal title={view.title} onClose={() => setView(null)}>
          <div className="muted sm" style={{ marginBottom: 10 }}>
            {(view.published_at || '').slice(0, 16).replace('T', ' ')} · {statusLabel(view)}
          </div>
          <div style={{ whiteSpace: 'pre-wrap' }}>{view.body || '—'}</div>
          {canEdit && (
            <div className="row end gap modal-foot">
              <button className="btn ghost" onClick={() => { setView(null); setEdit(view) }}>Edit</button>
            </div>
          )}
        </Modal>
      )}
      {edit !== null && (
        <AnnouncementEditor branchId={branch.id} initial={edit}
                            onClose={() => setEdit(null)}
                            onSaved={() => { setEdit(null); list.reload() }} />
      )}
    </div>
  )
}

function AnnouncementEditor({ branchId, initial, onClose, onSaved }) {
  const isEdit = !!initial?.id
  const [title, setTitle] = useState(initial?.title || '')
  const [body, setBody] = useState(initial?.body || '')
  const [status, setStatus] = useState(
    initial?.id ? (initial.status_id === 1 ? 'published' : 'draft') : 'draft')
  const save = async () => {
    if (isEdit) {
      await api.patch(`/announcements/${branchId}/${initial.id}/`, { title, body, status })
    } else {
      await api.post(`/announcements/${branchId}/`, { title, body, status })
    }
    onSaved()
  }
  return (
    <Modal title={isEdit ? 'Edit announcement' : 'New announcement'} onClose={onClose}>
      <label className="stacked">Title<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="stacked">Body<textarea rows={4} value={body}
                                               onChange={(e) => setBody(e.target.value)} /></label>
      <label className="stacked">Status
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
      </label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!title}>Save</button>
      </div>
    </Modal>
  )
}
