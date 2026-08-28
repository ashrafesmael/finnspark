import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { Modal } from '../components/ui'
import api from '../api'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function CalendarPage() {
  const { branch, user } = useAuth()
  const [monthOffset, setMonthOffset] = useState(0)
  const [filter, setFilter] = useState('all')
  const [modal, setModal] = useState(null)
  const events = useFetch(branch ? `/calendar-events/${branch.id}/?type=${filter}` : null)

  const grid = useMemo(() => {
    const base = new Date()
    base.setDate(1)
    base.setMonth(base.getMonth() + monthOffset)
    const year = base.getFullYear(), month = base.getMonth()
    const firstDow = (new Date(year, month, 1).getDay() + 6) % 7
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const cells = []
    for (let i = 0; i < firstDow; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d))
    while (cells.length % 7) cells.push(null)
    return { label: base.toLocaleDateString('en', { month: 'long', year: 'numeric' }), cells }
  }, [monthOffset])

  const byDay = (date) => {
    if (!date || !events.data) return []
    return events.data.filter((e) => e.start.slice(0, 10) === date.toISOString().slice(0, 10))
  }

  const addEvent = async (data) => {
    await api.post(`/calendar-events/${branch.id}/`, data)
    events.reload(); setModal(null)
  }

  return (
    <div>
      <div className="toolbar row spread">
        <h3>{grid.label}</h3>
        <div className="row gap">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
          <button className="btn ghost sm" onClick={() => setMonthOffset(monthOffset - 1)}>‹</button>
          <button className="btn ghost sm" onClick={() => setMonthOffset(0)}>Today</button>
          <button className="btn ghost sm" onClick={() => setMonthOffset(monthOffset + 1)}>›</button>
          <button className="btn primary sm" onClick={() => setModal({})}>+ Add meeting</button>
        </div>
      </div>

      <div className="calendar card">
        <div className="cal-head">
          {DAYS.map((d) => <div key={d} className="cal-dayname">{d}</div>)}
        </div>
        <div className="cal-grid">
          {grid.cells.map((d, i) => (
            <div key={i} className={`cal-cell ${d && d.toDateString() === new Date().toDateString() ? 'today' : ''}`}>
              {d && <span className="cal-num">{d.getDate()}</span>}
              {byDay(d).map((e) => (
                <div key={e.id}
                     className={`event ${e.visibility === 'private' ? 'priv' : 'pub'}`}
                     title={e.description}>
                  {e.title}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {modal !== null && (
        <EventModal onClose={() => setModal(null)} onSave={addEvent} />
      )}
    </div>
  )
}

function EventModal({ onClose, onSave }) {
  const [f, setF] = useState({
    title: '', description: '',
    start: new Date().toISOString().slice(0, 16),
    end: '', visibility: 'public',
  })
  return (
    <Modal title="New event" onClose={onClose}>
      <label className="stacked">Title<input value={f.title}
                                             onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
      <label className="stacked">Description<textarea rows={2} value={f.description}
          onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
      <div className="grid-2 gap">
        <label className="stacked">Start
          <input type="datetime-local" value={f.start}
                 onChange={(e) => setF({ ...f, start: e.target.value })} /></label>
        <label className="stacked">End
          <input type="datetime-local" value={f.end}
                 onChange={(e) => setF({ ...f, end: e.target.value })} /></label>
      </div>
      <label className="stacked">Visibility
        <select value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })}>
          <option value="public">Public</option>
          <option value="private">Private</option>
        </select>
      </label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!f.title}
                onClick={() => onSave(f)}>Save</button>
      </div>
    </Modal>
  )
}
