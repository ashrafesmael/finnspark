export function DataTable({ columns, rows, empty = 'No records', footer }) {
  return (
    <div className="table-wrap card">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key || c.header}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={columns.length} className="muted center">{empty}</td></tr>
          )}
          {rows.map((row, i) => (
            <tr key={row.id ?? i}>
              {columns.map((c) => (
                <td key={c.key || c.header}>
                  {c.render ? c.render(row, i) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {footer}
    </div>
  )
}

export function Pager({ page, pageSize, count, onPage }) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  if (pages <= 1) return null
  return (
    <div className="pager">
      <button className="btn ghost sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</button>
      <span>Page {page} / {pages} ({count})</span>
      <button className="btn ghost sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>›</button>
    </div>
  )
}

export function StatTile({ label, value, sub }) {
  return (
    <div className="card stat-tile">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="muted sm">{sub}</div>}
    </div>
  )
}

export function BarList({ items, color = 'var(--accent)' }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div className="bar-list">
      {items.map((it) => (
        <div key={it.name} className="bar-row">
          <span className="bar-name" title={it.name}>{it.name}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(100 * it.value) / max}%`, background: color }} />
          </div>
          <span className="bar-count">{it.value}</span>
        </div>
      ))}
      {items.length === 0 && <p className="muted sm">No data</p>}
    </div>
  )
}

export function Modal({ title, children, onClose, wide }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal card ${wide ? 'wide' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="row spread modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function StatusPill({ codeName, name }) {
  const cls = { approved: 'ok', active: 'ok', published: 'ok', graduated: 'ok',
                rejected: 'bad', archived: 'bad', in_approval: 'warn', revision: 'warn',
                invited: 'warn', draft: 'warn' }[codeName] || 'neutral'
  return <span className={`pill ${cls}`}>{name}</span>
}
