import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Download, TrendingUp } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal } from '../components/ui'
import api, { setAccessToken, getAccessToken } from '../api'

const TABS = ['Businesses/Projects', 'Business files', 'Courses progress',
              "Mentor's review questions", 'Mentor conclusion questions']

export default function ProgramDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { branch } = useAuth()
  const [tab, setTab] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [investBiz, setInvestBiz] = useState(null)
  const pageSize = 12

  const detail = useFetch(branch ? `/programs/${branch.id}/${id}/` : null)
  const list = useFetch(branch
    ? `/v2/programs/${branch.id}/${id}/businesses/?page=${page}&page_size=${pageSize}&business_name=${search}`
    : null)

  async function downloadExport() {
    const res = await api.get(`/programs/${branch.id}/${id}/export/`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${detail.data?.name || 'program'}_businesses.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="row spread">
        <h2>{detail.data?.name || 'Programme'}</h2>
        <button className="btn ghost sm" onClick={() => navigate('/programs')}>‹ All programmes</button>
      </div>
      <div className="tabs">
        {TABS.map((name, i) => (
          <button key={name} className={`tab ${i === tab ? 'active' : ''}`}
                  onClick={() => setTab(i)}>{name}</button>
        ))}
      </div>

      {tab === 0 && (
        <>
          <div className="toolbar row spread">
            <input placeholder="Search businesses…" value={search}
                   onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
            <button className="btn ghost sm" onClick={downloadExport}>
              <Download size={14} /> Export to Excel
            </button>
          </div>
          <DataTable
            columns={[
              { header: 'Business/Project', key: 'name' },
              { header: 'Founder(s)', render: (r) =>
                  (r.founders || []).map((f) => `${f.first_name} ${f.last_name}`).join(', ') || '—' },
              { header: 'Course progress %', render: (r) => `${r.course_progress}%` },
              { header: 'Course score %', render: (r) => `${r.course_score}%` },
              { header: 'Avg evaluator score', render: (r) => `${r.average_evaluator_score}%` },
              { header: 'Mentors', render: (r) =>
                  (r.mentors || []).map((m) => m.name).join(', ') || '—' },
              { header: 'Graduation', render: (r) => r.graduation_status },
              { header: '', render: (r) => (
                <span className="row gap">
                  <button className="btn ghost sm" onClick={async () => {
                    await api.patch(`/businesses/${branch.id}/${r.id}/`, {
                      graduation_status: r.graduation_status === 'Graduated'
                        ? 'Not graduated' : 'Graduated',
                    })
                    list.reload()
                  }}>Toggle</button>
                  <button className="btn ghost sm" onClick={() => setInvestBiz(r)}>Mentors</button>
                  {!r.invested && (
                    <button className="btn primary sm" onClick={() => doInvest(r)}>
                      <TrendingUp size={13} /> Invest
                    </button>
                  )}
                </span>
              )},
            ]}
            rows={list.data?.results || []}
            footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
          />
        </>
      )}

      {tab === 1 && <FilesPanel programId={id} branchId={branch?.id} />}
      {tab === 2 && <CoursesProgress programId={id} />}
      {tab === 3 && <QuestionsPanel kind="review" programId={id} title="Mentor review questions" />}
      {tab === 4 && <QuestionsPanel kind="conclusion" programId={id} title="Mentor conclusion questions" />}

      {investBiz && (
        <Modal title={`Assign mentors — ${investBiz.name}`}
               onClose={() => setInvestBiz(null)}>
          <MentorPicker businessId={investBiz.id} branchId={branch.id}
                        current={(investBiz.mentors || []).map((m) => m.id)}
                        onDone={() => { setInvestBiz(null); list.reload() }} />
        </Modal>
      )}
    </div>
  )

  async function doInvest(biz) {
    const amount = prompt(`Requested investment amount (USD) for ${biz.name}:`, '25000')
    if (amount == null) return
    try {
      await api.post(`/businesses/${branch.id}/${biz.id}/invest/`, {
        amount_requested: Number(amount),
      })
      alert(`${biz.name} promoted to the investment track (dealflow).`)
      list.reload()
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed')
    }
  }
}

function MentorPicker({ businessId, branchId, current, onDone }) {
  const { data: mentors } = useFetch(branchId ? `/users/${branchId}/mentors/` : null)
  const [ids, setIds] = useState(current || [])
  return (
    <div>
      {(mentors || []).map((m) => (
        <label key={m.id} className="choice">
          <input type="checkbox" checked={ids.includes(m.id)}
                 onChange={(e) => setIds(e.target.checked ? [...ids, m.id]
                                                          : ids.filter((x) => x !== m.id))} />
          {m.name} ({m.email})
        </label>
      ))}
      <div className="row end modal-foot">
        <button className="btn primary sm" onClick={async () => {
          await api.patch(`/businesses/${branchId}/${businessId}/`, { mentor_ids: ids })
          onDone()
        }}>Save mentors</button>
      </div>
    </div>
  )
}

function FilesPanel({ programId, branchId }) {
  const docs = useFetch(branchId ? `/branch/${branchId}/documents/?program=${programId}` : null)
  const [file, setFile] = useState(null)
  const upload = async () => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', file.name)
    fd.append('program_id', programId)
    await api.post(`/branch/${branchId}/documents/`, fd)
    setFile(null); docs.reload()
  }
  return (
    <>
      <div className="toolbar row gap">
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button className="btn primary sm" onClick={upload} disabled={!file}>Upload file</button>
      </div>
      <DataTable
        columns={[
          { header: 'Name', key: 'name' },
          { header: 'Size', render: (r) => `${(r.size / 1024).toFixed(1)} KB` },
          { header: 'Uploaded', render: (r) => (r.created_at || '').slice(0, 10) },
          { header: '', render: (r) => (
            <a className="btn ghost sm"
               href={`/api/documents/${r.id}/download/?branch_id=${branchId}`}>Download</a>
          )},
        ]}
        rows={docs.data || []}
      />
    </>
  )
}

function CoursesProgress({ programId }) {
  const courses = useFetch(`/programs/${programId}/courses-list/`)
  if (!courses.data) return null
  return (
    <div className="card pad">
      {courses.data.map((c) => (
        <div key={c.id} className="bar-row">
          <span className="bar-name">{c.name}</span>
          <div className="bar-track"><div className="bar-fill" style={{
            width: `${c.avg_progress || 0}%` }} /></div>
          <span className="bar-count">{(c.avg_progress || 0).toFixed(0)}%</span>
        </div>
      ))}
    </div>
  )
}

function QuestionsPanel({ kind, programId, title }) {
  const base = kind === 'review'
    ? `/v2/programs/${programId}/business-review/questions/`
    : `/v2/programs/${programId}/mentor-conclusion/questions/`
  const { data, reload } = useFetch(base)
  const [text, setText] = useState('')
  return (
    <div className="card pad">
      <h3>{title}</h3>
      {(data || []).map((q) => (
        <div key={q.id} className="row spread card-flat">
          <span>{q.order + 1}. {q.text}</span>
          <button className="btn ghost sm danger" onClick={() =>
            confirm('Remove?') &&
            api.delete(base + q.id + '/').catch(() => {}) && reload()
          }>✕</button>
        </div>
      ))}
      <div className="row gap" style={{ marginTop: 8 }}>
        <input placeholder="New question…" value={text}
               onChange={(e) => setText(e.target.value)} />
        <button className="btn primary sm" onClick={async () => {
          if (!text) return
          await api.post(base, { text, order: (data || []).length })
          setText(''); reload()
        }}>Add</button>
      </div>
    </div>
  )
}
