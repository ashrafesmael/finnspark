import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager } from '../components/ui'

export function Directories() {
  const { branch } = useAuth()
  const [page, setPage] = useState(1)
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const pageSize = 15
  const { data: roles } = useFetch(branch ? `/roles/${branch.id}/` : null)
  const list = useFetch(branch
    ? `/v2/users/${branch.id}/?page=${page}&page_size=${pageSize}&ordering=first_name&search=${search}&role=${role}`
    : null)

  return (
    <div>
      <div className="toolbar row spread">
        <h3>People directory</h3>
        <div className="row gap">
          <input placeholder="Search…" value={search}
                 onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          <select value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }}>
            <option value="">All roles</option>
            {(roles || []).map((r) => <option key={r.id} value={r.code_name}>{r.name}</option>)}
          </select>
        </div>
      </div>
      <DataTable
        columns={[
          { header: 'Name', render: (r) => `${r.first_name} ${r.last_name}` },
          { header: 'Company', render: (r) => r.company || '—' },
          { header: 'Position', render: (r) => r.position || '—' },
          { header: 'Role', render: (r) => (r.roles || []).map((x) => x.name).join(', ') || '—' },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />
    </div>
  )
}
