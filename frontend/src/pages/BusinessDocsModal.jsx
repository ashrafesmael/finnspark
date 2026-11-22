import { useState } from 'react'
import { useFetch } from '../hooks/useFetch'
import { Modal } from '../components/ui'
import api from '../api'

/** Per-business document panel: upload (e.g. KYC IDs) and list/view/download/delete
 *  documents scoped to this specific startup. PDFs and images view on-screen. */
export default function BusinessDocsModal({ branchId, business, onClose }) {
  const [file, setFile] = useState(null)
  const [docName, setDocName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [viewer, setViewer] = useState(null)   // {url, name, mime, isImage}
  const docs = useFetch(branchId ? `/branch/${branchId}/documents/?business_id=${business.id}` : null)

  const view = async (d) => {
    try {
      const res = await api.get(`/documents/${d.id}/download/?branch_id=${branchId}`,
                                { responseType: 'blob' })
      const mime = res.headers['content-type'] || d.mime || 'application/octet-stream'
      const url = URL.createObjectURL(new Blob([res.data], { type: mime }))
      setViewer({ url, name: d.name, mime, isImage: mime.startsWith('image/') })
    } catch (e) {
      setError('Failed to open document: ' + (e.response?.data?.detail || e.message))
    }
  }

  const download = (id) => {
    api.get(`/documents/${id}/download/?branch_id=${branchId}`, { responseType: 'blob' })
      .then((res) => {
        const mime = res.headers['content-type'] || 'application/octet-stream'
        const url = URL.createObjectURL(new Blob([res.data], { type: mime }))
        const a = document.createElement('a')
        a.href = url
        a.download = ''
        a.click()
        setTimeout(() => URL.revokeObjectURL(url), 60000)
      })
  }

  const upload = async () => {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('name', docName.trim() || file.name)
      fd.append('business_id', business.id)
      await api.post(`/branch/${branchId}/documents/`, fd)
      setFile(null); setDocName(''); docs.reload()
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally { setBusy(false) }
  }

  return (
    <>
      <Modal title={`Documents — ${business.name}`} onClose={onClose}>
        <div className="card pad" style={{ marginBottom: 14 }}>
          <label className="stacked">Document name (optional)
            <input value={docName} placeholder="e.g. KYC — Passport (signed)"
                   onChange={(e) => setDocName(e.target.value)} />
          </label>
          <label className="stacked">File
            <input type="file" onChange={(e) => setFile(e.target.files[0])} />
          </label>
          {error && <div className="alert">{error}</div>}
          <button className="btn primary sm" onClick={upload} disabled={busy || !file}>
            {busy ? 'Uploading…' : 'Upload to this startup'}
          </button>
        </div>

        <h4 style={{ marginBottom: 8 }}>Documents ({(docs.data || []).length})</h4>
        {(docs.data || []).length === 0 ? (
          <p className="muted sm">No documents uploaded for this startup yet.</p>
        ) : (
          <div className="stack" style={{ gap: 6 }}>
            {(docs.data || []).map((d) => (
              <div key={d.id} className="row spread card-flat" style={{ padding: '6px 10px' }}>
                <span>
                  <b className="sm">{d.name}</b>
                  <span className="sm muted" style={{ marginLeft: 8 }}>
                    {(d.size / 1024).toFixed(0)} KB · {(d.created_at || '').slice(0, 10)}
                  </span>
                </span>
                <span className="row gap">
                  <button className="btn ghost sm" onClick={() => view(d)}>View</button>
                  <button className="btn ghost sm" onClick={() => download(d.id)}>Download</button>
                  <button className="btn ghost sm danger" onClick={async () => {
                    if (!confirm(`Delete ${d.name}?`)) return
                    await api.delete(`/branch/${branchId}/documents/${d.id}/`)
                    docs.reload()
                  }}>✕</button>
                </span>
              </div>
            ))}
          </div>
        )}
      </Modal>

      {viewer && (
        <Modal title={viewer.name} onClose={() => { URL.revokeObjectURL(viewer.url); setViewer(null) }} wide>
          {viewer.isImage ? (
            <img src={viewer.url} alt={viewer.name}
                 style={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', margin: '0 auto' }} />
          ) : (
            <iframe src={viewer.url} title={viewer.name}
                    style={{ width: '100%', height: '72vh', border: '1px solid var(--border)', borderRadius: 8 }} />
          )}
        </Modal>
      )}
    </>
  )
}
