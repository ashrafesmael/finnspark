import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal } from '../components/ui'
import api from '../api'

export default function Announcements() {
  const { branch, can } = useAuth()
  const [page, setPage] = useState(1)
  const [edit, setEdit] = useState(null)
  const pageSize = 10
  const list = useFetch(branch ? `/announcements/${branch.id}/?page=${page}&page_size=${pageSize}` : null)

  const react = async (a) => {
    await api.post(`/announcements/${branch.id}/${a.id}/react/`)
    list.reload()
  }

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Announcements</h3>
        {can('announcements.edit') && (
          <button className="btn primary sm" onClick={() => setEdit({})}>+ Create announcement</button>
        )}
      </div>
      <DataTable
        columns={[
          { header: 'Announcement', key: 'title' },
          { header: 'Date', render: (r) => (r.published_at || '').slice(0, 16).replace('T', ' ') },
          { header: 'Reactions', render: (r) => (
            <button className={`btn ghost sm ${r.reacted ? 'primary' : ''}`} onClick={() => react(r)}>
              👏 {r.reactions_count}
            </button>
          )},
          { header: 'Status', render: (r) => r.status_id === 1 ? 'Published' : 'Draft' },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />
      {edit !== null && (
        <AnnouncementEditor branchId={branch.id} initial={edit}
                            onClose={() => setEdit(null)}
                            onSaved={() => { setEdit(null); list.reload() }} />
      )}
    </div>
  )
}

function AnnouncementEditor({ branchId, initial, onClose, onSaved }) {
  const [title, setTitle] = useState(initial?.title || '')
  const [body, setBody] = useState(initial?.body || '')
  const [status, setStatus] = useState('draft')
  const save = async () => {
    await api.post(`/announcements/${branchId}/`, { title, body, status })
    onSaved()
  }
  return (
    <Modal title="New announcement" onClose={onClose}>
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
