import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  PlayCircle, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  BookOpen, Clock, Layers, Award, Lightbulb, ClipboardCheck, FileText, Compass,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { Pager, StatusPill } from '../components/ui'
import api from '../api'

/* ------------------------------------------------------------------ helpers */

const BLOCK_META = {
  body: null,
  case: { label: 'Case study', Icon: Compass, tone: 'case' },
  checklist: { label: 'Self-check', Icon: ClipboardCheck, tone: 'checklist' },
  worksheet: { label: 'Worksheet', Icon: FileText, tone: 'worksheet' },
  practice: { label: 'In practice', Icon: Lightbulb, tone: 'practice' },
  variant: { label: '', Icon: Lightbulb, tone: 'variant' },
  related: { label: 'Related', Icon: Lightbulb, tone: 'practice' },
}

const splitNumber = (name = '') => {
  const m = name.match(/^(\d+)\.\s*(.*)$/)
  return m ? { index: m[1], title: m[2] } : { index: '', title: name }
}

const stripHtml = (html = '') =>
  html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&lsquo;|&rsquo;/g, "'")
    .replace(/&ndash;/g, '–')
    .replace(/&mdash;/g, '—')
    .replace(/&amp;/g, '&')
    .replace(/&nbsp;/g, ' ')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim()

const readingTime = (blocks = []) => {
  const words = blocks.reduce((n, b) => n + stripHtml(b.payload?.html).split(' ').length, 0)
  return Math.max(1, Math.round(words / 200))
}

function ProgressBar({ value = 0, tone = 'accent' }) {
  return (
    <div className="track" role="progressbar" aria-valuenow={Math.round(value)}
         aria-valuemin={0} aria-valuemax={100}>
      <div className={`fill tone-${tone}`} style={{ width: `${Math.min(100, value)}%` }} />
    </div>
  )
}

function ProgressRing({ value = 0, size = 56, label }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const done = Math.min(100, Math.max(0, value))
  return (
    <div className="learn-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} className="learn-ring-bg" />
        <circle cx={size / 2} cy={size / 2} r={r} className="learn-ring-fg"
                strokeDasharray={circ} strokeDashoffset={circ - (done / 100) * circ} />
      </svg>
      <span className="learn-ring-label">{label ?? `${Math.round(done)}%`}</span>
    </div>
  )
}

/* ------------------------------------------------------------------ catalogue */

export default function Courses() {
  const { branch } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [language, setLanguage] = useState('')
  const pageSize = 12

  const list = useFetch(
    branch ? `/courses/${branch.id}/?page=${page}&page_size=${pageSize}&search=${search}&language=${language}` : null
  )

  const courses = list.data?.results || []
  const totals = useMemo(() => {
    const all = list.data?.count || 0
    const started = courses.filter((c) => c.is_started).length
    const done = courses.filter((c) => c.is_completed).length
    return { all, started, done }
  }, [list.data, courses])

  return (
    <div>
      <header className="hub-head">
        <div>
          <h2>Learning hub</h2>
          <p className="muted sm">
            Work through the curriculum in order — each course builds on the one before it.
          </p>
        </div>
        <div className="hub-stats">
          <div className="hub-stat"><b>{totals.all}</b><span className="muted sm">courses</span></div>
          <div className="hub-stat"><b>{totals.started}</b><span className="muted sm">in progress</span></div>
          <div className="hub-stat"><b>{totals.done}</b><span className="muted sm">completed</span></div>
        </div>
      </header>

      <div className="toolbar row spread wrap gap">
        <input placeholder="Search courses…" value={search}
               onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <div className="row gap">
          <select value={language} onChange={(e) => { setLanguage(e.target.value); setPage(1) }}>
            <option value="">All languages</option>
            {['en', 'ar', 'ru', 'fr', 'pt'].map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>

      {courses.length === 0 && <div className="card pad muted center">No courses found.</div>}

      <div className="course-grid">
        {courses.map((c) => <CourseCard key={c.id} course={c} />)}
      </div>

      <Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />
    </div>
  )
}

function CourseCard({ course }) {
  const { index, title } = splitNumber(course.name)
  const progress = course.progress || 0
  const state = course.is_completed ? 'done' : course.is_started ? 'active' : 'todo'
  return (
    <Link to={`/courses/view/${course.id}`} className={`course-card card ${state}`}>
      <div className="course-card-top">
        {index && <span className="course-index">{index}</span>}
        <div className="course-card-meta">
          {course.status && <StatusPill {...course.status} />}
          <span className="muted sm">{course.language}</span>
        </div>
      </div>
      <h3 className="course-card-title">{title}</h3>
      <p className="muted sm course-card-blurb">{stripHtml(course.description).slice(0, 96)}…</p>
      <div className="course-card-foot">
        <span className="row gap sm muted">
          <Layers size={13} /> {course.modules_count} modules
        </span>
        <span className={`pill ${state === 'done' ? 'ok' : state === 'active' ? 'warn' : 'neutral'}`}>
          {state === 'done' ? 'Completed' : state === 'active' ? `${Math.round(progress)}%` : 'Not started'}
        </span>
      </div>
      <ProgressBar value={progress} tone={state === 'done' ? 'ok' : 'accent'} />
    </Link>
  )
}

/* ------------------------------------------------------------------ course detail */

export function CourseDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { branch } = useAuth()
  const detail = useFetch(branch ? `/courses/${branch.id}/${id}/` : null)

  const [openLesson, setOpenLesson] = useState(null)
  const [openModules, setOpenModules] = useState(() => new Set())
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const course = detail.data
  const { index, title } = splitNumber(course?.name || '')

  // flat list of lessons in reading order, for resume + previous/next
  const flat = useMemo(() => {
    if (!course) return []
    const out = []
    ;(course.modules || []).forEach((m, mi) => {
      ;(m.lessons || []).forEach((l, li) => out.push({ ...l, module: m, moduleIndex: mi, lessonIndex: li }))
    })
    return out
  }, [course])

  // open the module holding the first unfinished lesson, so returning learners
  // land on where they left off rather than at the top of the page
  useEffect(() => {
    if (!course || openLesson) return
    const first = flat.find((l) => !l.is_completed) || flat[0]
    if (first) {
      setOpenLesson(first.id)
      setOpenModules(new Set([first.moduleIndex]))
    }
  }, [course, flat, openLesson])

  if (!course) return <p className="muted">Loading…</p>

  const toggleModule = (mi) => {
    setOpenModules((prev) => {
      const next = new Set(prev)
      next.has(mi) ? next.delete(mi) : next.add(mi)
      return next
    })
  }

  const openLessonByIndex = (pos) => {
    const target = flat[pos]
    if (!target) return
    setOpenLesson(target.id)
    setOpenModules(new Set([target.moduleIndex]))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const completeBlock = async (blockId) => {
    setSaving(true)
    setSaveError('')
    try {
      await api.post(`/content-blocks/${blockId}/complete/`)
      detail.reload()
    } catch (e) {
      setSaveError(e.response?.data?.detail || 'Could not save your progress. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const completeLesson = async (lesson) => {
    setSaving(true)
    setSaveError('')
    try {
      for (const b of (lesson.blocks || []).filter((b) => !b.is_completed)) {
        await api.post(`/content-blocks/${b.id}/complete/`)
      }
      detail.reload()
    } catch (e) {
      setSaveError(e.response?.data?.detail || 'Could not save your progress. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const currentPos = flat.findIndex((l) => l.id === openLesson)
  const totalBlocks = flat.reduce((n, l) => n + (l.blocks || []).length, 0)
  const doneBlocks = flat.reduce(
    (n, l) => n + (l.blocks || []).filter((b) => b.is_completed).length, 0)

  return (
    <div className="course-view">
      <button className="btn ghost sm back-link" onClick={() => navigate('/courses')}>
        <ChevronLeft size={14} /> All courses
      </button>

      <header className="course-hero card">
        <div className="course-hero-main">
          <div className="row gap wrap" style={{ marginBottom: 6 }}>
            {index && <span className="course-index big">{index}</span>}
            {course.status && <StatusPill {...course.status} />}
            <span className="pill neutral">{course.language}</span>
          </div>
          <h2 className="course-hero-title">{title}</h2>
          <div
            className="muted rich-text"
            dangerouslySetInnerHTML={{ __html: course.description || '' }}
          />
          <div className="row gap wrap course-facts">
            <span className="row gap sm muted"><Layers size={14} /> {course.modules?.length || 0} modules</span>
            <span className="row gap sm muted"><BookOpen size={14} /> {flat.length} lessons</span>
            <span className="row gap sm muted"><Clock size={14} /> ~{readingTime(flat.flatMap((l) => l.blocks))} min</span>
            {course.is_completed && (
              <span className="row gap sm" style={{ color: 'var(--ok-fg)' }}>
                <Award size={14} /> Completed
              </span>
            )}
          </div>
        </div>
        <div className="course-hero-side">
          <ProgressRing value={course.progress} size={72} />
          <span className="muted sm">{doneBlocks} of {totalBlocks} steps</span>
        </div>
      </header>

      <div className="course-body">
        <nav className="course-outline card">
          <h4>Contents</h4>
          <ol className="outline-list">
            {flat.map((l, i) => (
              <li key={l.id}>
                <button
                  className={`outline-item ${l.id === openLesson ? 'current' : ''} ${l.is_completed ? 'done' : ''}`}
                  onClick={() => openLessonByIndex(i)}
                >
                  <span className="outline-tick">{l.is_completed ? '✓' : i + 1}</span>
                  <span className="outline-name">{splitNumber(l.name).title}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <div className="course-modules">
          {(course.modules || []).map((m, mi) => {
            const isOpen = openModules.has(mi)
            const mLessons = m.lessons || []
            const mDone = mLessons.filter((l) => l.is_completed).length
            const mPct = mLessons.length ? (mDone / mLessons.length) * 100 : 0
            return (
              <section key={m.id} className="card module-block">
                <button className="module-head" onClick={() => toggleModule(mi)}>
                  <div>
                    <h3>{m.name}</h3>
                    <span className="muted sm">
                      {mDone} of {mLessons.length} lessons
                      {m.description ? ` · ${stripHtml(m.description)}` : ''}
                    </span>
                  </div>
                  <div className="row gap">
                    {mPct === 100
                      ? <span className="pill ok">Complete</span>
                      : <span className="muted sm">{Math.round(mPct)}%</span>}
                    <ChevronDown size={16} className={isOpen ? 'flip' : ''} />
                  </div>
                </button>
                <ProgressBar value={mPct} tone={mPct === 100 ? 'ok' : 'accent'} />

                {isOpen && (
                  <div className="module-body">
                    {mLessons.map((l, li) => {
                      const pos = flat.findIndex((f) => f.id === l.id)
                      const isCurrent = l.id === openLesson
                      return (
                        <div key={l.id} className={`lesson-block ${isCurrent ? 'open' : ''}`}>
                          <button className="lesson-head" onClick={() => setOpenLesson(isCurrent ? null : l.id)}>
                            <span className={`lesson-bullet ${l.is_completed ? 'done' : ''}`}>
                              {l.is_completed ? <CheckCircle2 size={16} /> : <PlayCircle size={16} />}
                            </span>
                            <span className="lesson-name">{l.name}</span>
                            <span className="muted sm row gap">
                              <Clock size={12} /> {readingTime(l.blocks)} min
                            </span>
                          </button>

                          {isCurrent && (
                            <div className="lesson-content">
                              {l.description && (
                                <div className="muted rich-text"
                                     dangerouslySetInnerHTML={{ __html: l.description }} />
                              )}
                              {(l.blocks || []).map((b) => {
                                const kind = b.payload?.kind || 'body'
                                const meta = BLOCK_META[kind]
                                const body = (
                                  <div className="rich-text"
                                       dangerouslySetInnerHTML={{ __html: b.payload?.html || '' }} />
                                )
                                return (
                                  <div key={b.id} className={`learn-block learn-block-${kind} ${b.is_completed ? 'done' : ''}`}>
                                    {meta && (
                                      <div className="learn-block-label">
                                        <meta.Icon size={14} />
                                        {meta.label || b.title}
                                        {kind === 'variant' && b.title ? ` · ${b.title}` : ''}
                                      </div>
                                    )}
                                    {body}
                                    <button
                                      className={`btn sm ${b.is_completed ? 'ghost' : 'primary'} block-done`}
                                      disabled={saving || b.is_completed}
                                      onClick={() => completeBlock(b.id)}
                                    >
                                      {b.is_completed ? <><CheckCircle2 size={13} /> Done</> : 'Mark as read'}
                                    </button>
                                  </div>
                                )
                              })}
                              <div className="lesson-actions">
                                {saveError && <span className="pill bad">{saveError}</span>}
                                {!l.is_completed && (
                                  <button className="btn primary sm" disabled={saving}
                                          onClick={() => completeLesson(l)}>
                                    <CheckCircle2 size={14} /> Complete lesson
                                  </button>
                                )}
                                <div className="spacer" />
                                {currentPos > 0 && (
                                  <button className="btn ghost sm" onClick={() => openLessonByIndex(currentPos - 1)}>
                                    <ChevronLeft size={14} /> Previous
                                  </button>
                                )}
                                {currentPos < flat.length - 1 && (
                                  <button className="btn ghost sm" onClick={() => openLessonByIndex(currentPos + 1)}>
                                    Next lesson <ChevronRight size={14} />
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
