import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable } from '../components/ui'
import api from '../api'

export default function Library() {
  const { branch, can } = useAuth()
  const [file, setFile] = useState(null)
  const docs = useFetch(branch ? `/branch/${branch.id}/documents/` : null)

  const upload = async () => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', file.name)
    await api.post(`/branch/${branch.id}/documents/`, fd)
    setFile(null); docs.reload()
  }

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Branch files</h3>
        <div className="row gap">
          <input type="file" onChange={(e) => setFile(e.target.files[0])} />
          <button className="btn primary sm" onClick={upload} disabled={!file}>Upload file</button>
        </div>
      </div>
      <DataTable
        columns={[
          { header: 'Name', key: 'name' },
          { header: 'Size', render: (r) => `${(r.size / 1024).toFixed(1)} KB` },
          { header: 'Type', key: 'mime' },
          { header: 'Uploaded', render: (r) => (r.created_at || '').slice(0, 10) },
          { header: '', render: (r) => (
            <span className="row gap">
              <a className="btn ghost sm"
                 href={`/api/documents/${r.id}/download/?branch_id=${branch.id}`}>Download</a>
              {can('library.edit') && (
                <button className="btn ghost sm danger" onClick={async () => {
                  if (confirm(`Delete ${r.name}?`)) {
                    await api.delete(`/branch/${branch.id}/documents/${r.id}/`)
                    docs.reload()
                  }
                }}>Delete</button>
              )}
            </span>
          )},
        ]}
        rows={docs.data || []}
      />
    </div>
  )
}
