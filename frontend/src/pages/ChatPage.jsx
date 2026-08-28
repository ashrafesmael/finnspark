import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import api from '../api'

export default function ChatPage() {
  const { branch, user } = useAuth()
  const { data: chats, reload } = useFetch('/chats/')
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const boxRef = useRef(null)
  const { data: users } = useFetch(branch ? `/v2/users/${branch.id}/?page_size=200` : null)
  const [newChatOpen, setNewChatOpen] = useState(false)

  useEffect(() => {
    if (!activeId) return
    let alive = true
    const load = () => api.get(`/chats/${activeId}/messages/`).then((r) => {
      if (alive) setMessages(r.data)
    }).catch(() => {})
    load()
    const iv = setInterval(load, 3000)   // polling (no websocket infra on this stack)
    return () => { alive = false; clearInterval(iv) }
  }, [activeId])

  useEffect(() => {
    boxRef.current?.scrollTo(0, boxRef.current.scrollHeight)
  }, [messages])

  const send = async () => {
    if (!draft.trim()) return
    await api.post(`/chats/${activeId}/messages/`, { body: draft })
    setDraft('')
  }

  const startChat = async (otherUserId) => {
    const existing = (chats || []).find((c) => !c.is_group &&
      c.participants.some((p) => p.id === otherUserId))
    if (existing) { setActiveId(existing.id); setNewChatOpen(false); return }
    const res = await api.post('/user-chats/', {
      branch_id: branch.id, participants: [otherUserId],
    })
    setNewChatOpen(false); reload(); setActiveId(res.data.id)
  }

  const active = (chats || []).find((c) => c.id === activeId)

  return (
    <div className="chat-shell card">
      <aside className="chat-list">
        <div className="row spread">
          <b>Chats</b>
          <button className="btn ghost sm" onClick={() => setNewChatOpen(!newChatOpen)}>+</button>
        </div>
        {newChatOpen && (
          <div className="new-chat">
            {(users?.results || []).filter((u) => u.id !== user.id).map((u) => (
              <button key={u.id} className="btn ghost sm" onClick={() => startChat(u.id)}>
                {u.first_name} {u.last_name}
              </button>
            ))}
          </div>
        )}
        {(chats || []).map((c) => (
          <button key={c.id} onClick={() => setActiveId(c.id)}
                  className={`chat-item ${c.id === activeId ? 'active' : ''}`}>
            <span>{c.is_group ? `# ${c.title || 'Group'}` :
                   c.participants[0]?.name || 'Direct message'}</span>
            {c.unread > 0 && <span className="badge-dot">{c.unread}</span>}
          </button>
        ))}
      </aside>
      <section className="chat-thread">
        {active ? (
          <>
            <header><b>{active.is_group ? active.title : active.participants[0]?.name}</b></header>
            <div className="msg-box" ref={boxRef}>
              {messages.map((m) => (
                <div key={m.id} className={`msg ${m.sender_id === user.id ? 'mine' : ''}`}>
                  <span className="sender">{m.sender_name}</span>
                  <p>{m.body}</p>
                  <time>{m.sent_at.slice(11, 16)}</time>
                </div>
              ))}
            </div>
            <footer className="row gap">
              <input value={draft} placeholder="Type a message…"
                     onChange={(e) => setDraft(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && send()} />
              <button className="btn primary sm" onClick={send}>Send</button>
            </footer>
          </>
        ) : <p className="muted center pad">Select a chat to start messaging.</p>}
      </section>
    </div>
  )
}
