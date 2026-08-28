import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PlayCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, StatusPill, Modal } from '../components/ui'
import api from '../api'

function OpenCourseButton({ id }) {
  const navigate = useNavigate()
  return <button className="btn ghost sm" onClick={() => navigate(`/courses/view/${id}`)}>
    Open course</button>
}

export default function Courses() {
  const { branch } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [language, setLanguage] = useState('')
  const pageSize = 10
  const list = useFetch(
    branch ? `/courses/${branch.id}/?page=${page}&page_size=${pageSize}&search=${search}&language=${language}` : null)

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Courses</h3>
        <div className="row gap">
          <input placeholder="Search…" value={search}
                 onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="">All languages</option>
            {['en', 'ar', 'ru', 'fr', 'pt'].map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>
      <DataTable
        columns={[
          { header: 'Course', key: 'name' },
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
          { header: 'Modules', key: 'modules_count' },
          { header: 'Language', render: (r) =>
              `${r.language} · subs: ${(r.subtitle_languages || []).join(', ') || '—'}` },
          { header: 'Progress', render: (r) => `${r.progress}%` },
          { header: '', key: 'open', render: (r) => <OpenCourseButton id={r.id} /> },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />
    </div>
  )
}

export function CourseDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { branch } = useAuth()
  const detail = useFetch(branch ? `/courses/${branch.id}/${id}/` : null)
  const [openLesson, setOpenLesson] = useState(null)

  if (!detail.data) return <p className="muted">Loading…</p>
  const c = detail.data

  const completeBlock = async (blockId) => {
    await api.post(`/content-blocks/${blockId}/complete/`)
    detail.reload()
  }

  return (
    <div>
      <div className="row spread">
        <h2>{c.name}</h2>
        <button className="btn ghost sm" onClick={() => navigate('/courses')}>‹ All courses</button>
      </div>
      <p className="muted">{c.description}</p>
      {!c.is_enrolled && (
        <button className="btn primary sm" onClick={async () => {
          await api.post(`/courses/${branch.id}/${c.id}/enroll/`)
          detail.reload()
        }}>Enroll</button>
      )}

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${c.progress}%` }} />
        <span>{c.progress}% complete</span>
      </div>

      {(c.modules || []).map((m) => (
        <div key={m.id} className="card pad module">
          <h3>{m.name} {m.is_completed && <span className="pill ok">done</span>}</h3>
          <p className="muted sm">{m.description}</p>
          {(m.lessons || []).map((l) => (
            <div key={l.id} className="lesson">
              <button className="lesson-head row spread" onClick={() =>
                setOpenLesson(openLesson === l.id ? null : l.id)}>
                <span><PlayCircle size={15} /> {l.name} {l.is_completed && '✓'}</span>
                <span className="muted sm">{(l.blocks || []).length} blocks</span>
              </button>
              {openLesson === l.id && (
                <div className="blocks">
                  {(l.blocks || []).map((b) => (
                    <div key={b.id} className={`block card-flat ${b.is_completed ? 'done' : ''}`}>
                      <b>{b.title}</b> <span className="pill neutral">{b.block_type}</span>
                      {b.block_type === 'video' && b.payload?.url && (
                        <video controls src={b.payload.url} width="100%" />
                      )}
                      {b.block_type === 'text' && (
                        <div dangerouslySetInnerHTML={{ __html: b.payload?.html || '' }} />
                      )}
                      {b.block_type === 'image' && b.payload?.url && (
                        <img src={b.payload.url} alt={b.title} style={{ maxWidth: '100%' }} />
                      )}
                      {b.block_type === 'file' && b.payload?.url && (
                        <a href={b.payload.url} target="_blank" rel="noreferrer">Download file</a>
                      )}
                      {b.block_type === 'quiz' && (b.payload?.questions || []).map((q, qi) => (
                        <label key={qi} className="stacked">{q.q}
                          <select>{(q.options || []).map((o) => <option key={o}>{o}</option>)}</select>
                        </label>
                      ))}
                      <button className="btn ghost sm" disabled={b.is_completed}
                              onClick={() => completeBlock(b.id)}>
                        {b.is_completed ? 'Completed ✓' : 'Mark complete'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
