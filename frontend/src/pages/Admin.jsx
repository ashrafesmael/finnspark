import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import FormRenderer from '../components/FormRenderer'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal, StatusPill } from '../components/ui'
import api from '../api'

export function UsersAdmin() {
  const { branch, can } = useAuth()
  const [page, setPage] = useState(1)
  const [statusF, setStatusF] = useState('')
  const [roleF, setRoleF] = useState('')
  const [search, setSearch] = useState('')
  const [invite, setInvite] = useState(false)
  const [rolesOpen, setRolesOpen] = useState(false)
  const pageSize = 12
  const { data: roles, reload: reloadRoles } = useFetch(branch ? `/roles/${branch.id}/` : null)
  const { data: statuses } = useFetch('/user-statuses/')
  const list = useFetch(branch
    ? `/v2/users/${branch.id}/?page=${page}&page_size=${pageSize}&search=${search}&role=${roleF}&status=${statusF}`
    : null)

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Users & Roles/Permissions</h3>
        <div className="row gap">
          <button className="btn ghost sm" onClick={() => setRolesOpen(true)}>Manage roles</button>
          {can('users.manage') && (
            <button className="btn primary sm" onClick={() => setInvite(true)}>+ Add user</button>
          )}
        </div>
      </div>
      <div className="filters row wrap">
        <input placeholder="Search name/email…" value={search}
               onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <select value={statusF} onChange={(e) => setStatusF(e.target.value)}>
          <option value="">All statuses</option>
          {(statuses || []).map((s) =>
            <option key={s.id} value={s.code_name}>{s.name}</option>)}
        </select>
        <select value={roleF} onChange={(e) => setRoleF(e.target.value)}>
          <option value="">All roles</option>
          {(roles || []).map((r) =>
            <option key={r.id} value={r.code_name}>{r.name}</option>)}
        </select>
      </div>
      <DataTable
        columns={[
          { header: 'Name', render: (r) => `${r.first_name} ${r.last_name}` },
          { header: 'Position', render: (r) => r.position || '—' },
          { header: 'Role', render: (r) => (r.roles || []).map((x) => x.name).join(', ') || '—' },
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />

      {invite && (
        <InviteModal branchId={branch.id} roles={roles || []}
                     onClose={() => setInvite(false)}
                     onSaved={() => { setInvite(false); list.reload() }} />
      )}
      {rolesOpen && (
        <RolesModal branchId={branch.id} onClose={() => { setRolesOpen(false); reloadRoles() }} />
      )}
    </div>
  )
}

function InviteModal({ branchId, roles, onClose, onSaved }) {
  const [f, setF] = useState({ email: '', first_name: '', last_name: '',
                               position: '', role_id: '', password: '' })
  return (
    <Modal title="Add user to branch" onClose={onClose}>
      <label className="stacked">Email<input value={f.email}
          onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
      <div className="grid-2 gap">
        <label className="stacked">First name<input value={f.first_name}
            onChange={(e) => setF({ ...f, first_name: e.target.value })} /></label>
        <label className="stacked">Last name<input value={f.last_name}
            onChange={(e) => setF({ ...f, last_name: e.target.value })} /></label>
      </div>
      <label className="stacked">Position<input value={f.position}
          onChange={(e) => setF({ ...f, position: e.target.value })} /></label>
      <label className="stacked">Role
        <select value={f.role_id} onChange={(e) => setF({ ...f, role_id: e.target.value })}>
          <option value="">Choose role…</option>
          {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </label>
      <label className="stacked">Initial password<input value={f.password}
          onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!f.email || !f.role_id} onClick={async () => {
          await api.post(`/users/${branchId}/invite/`, f)
          onSaved()
        }}>Add user</button>
      </div>
    </Modal>
  )
}

const ALL_PERMS = ['dashboard.view', 'selections.view', 'selections.edit', 'applicants.score',
  'mentor.review', 'forms.view', 'forms.edit', 'programs.view', 'programs.edit',
  'courses.view', 'courses.edit', 'library.view', 'library.edit', 'dealflow.view', 'dealflow.edit',
  'approval.view', 'approval.decide', 'portfolio.view', 'portfolio.edit',
  'reports.view', 'reports.export', 'announcements.view', 'announcements.edit',
  'calendar.view', 'directories.view', 'chat.use', 'users.manage']

function RolesModal({ branchId, onClose }) {
  const { data: roles, reload } = useFetch(`/roles/${branchId}/`)
  const [creating, setCreating] = useState(null)

  return (
    <Modal title="Manage roles" onClose={onClose} wide>
      {(roles || []).map((r) => (
        <details key={r.id} className="card-flat">
          <summary><b>{r.name}</b> <code>{r.code_name}</code>{r.is_constant &&
            <span className="pill neutral">constant</span>}</summary>
          {!r.is_constant ? (
            <>
              <p className="muted sm">Permissions:</p>
              <div className="perm-grid">
                {ALL_PERMS.map((p) => (
                  <label key={p} className="choice">
                    <input type="checkbox"
                           defaultChecked={(r.permissions || []).includes(p)}
                           onChange={async (e) => {
                             const next = e.target.checked
                               ? [...(r.permissions || []), p]
                               : (r.permissions || []).filter((x) => x !== p)
                             await api.patch(`/roles/${branchId}/${r.id}/`, {
                               permissions: next,
                             }).catch(() => {})
                             reload()
                           }} /> {p}
                    </label>
                ))}
              </div>
              <button className="btn ghost sm danger" onClick={async () => {
                if (!confirm(`Delete role ${r.name}?`)) return
                await api.delete(`/roles/${branchId}/${r.id}/`).catch(() => {})
                reload()
              }}>Delete role</button>
            </>
          ) : <p className="muted sm">Constant system role — always present.</p>}
        </details>
      ))}
      {creating === null && (
        <button className="btn primary sm" onClick={() => setCreating({})}>+ Create custom role</button>
      )}
      {creating !== null && (
        <CustomRoleForm branchId={branchId} onDone={() => { setCreating(null); reload() }} />
      )}
    </Modal>
  )
}

function CustomRoleForm({ branchId, onDone }) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [perms, setPerms] = useState([])
  return (
    <div className="card-flat">
      <div className="grid-2 gap">
        <label className="stacked">Role name<input value={name}
            onChange={(e) => setName(e.target.value)} /></label>
        <label className="stacked">Code name<input value={code} placeholder="e.g. investment_manager"
            onChange={(e) => setCode(e.target.value)} /></label>
      </div>
      <div className="perm-grid">
        {ALL_PERMS.map((p) => (
          <label key={p} className="choice">
            <input type="checkbox" checked={perms.includes(p)}
                   onChange={(e) => setPerms(e.target.checked ? [...perms, p]
                                                              : perms.filter((x) => x !== p))} /> {p}
          </label>
        ))}
      </div>
      <button className="btn primary sm" disabled={!name || !code} onClick={async () => {
        await api.post(`/roles/${branchId}/`, { name, code_name: code, permissions: perms })
        onDone()
      }}>Create role</button>
    </div>
  )
}

export function OrganizationsAdmin() {
  const [search, setSearch] = useState('')
  const [newOrg, setNewOrg] = useState(null)
  const [editOrg, setEditOrg] = useState(null)
  const [addBranch, setAddBranch] = useState(null)
  const { data: orgs, reload } = useFetch(search ? `/organizations/?search=${search}` : '/organizations/')

  const removeOrg = async (org) => {
    const sure = confirm(
      `Delete organization "${org.name}"?` +
      (org.branches?.length
        ? `\n\nThis will PERMANENTLY delete ${org.branches.length} branch(es) and ALL their data ` +
          '(applicants, businesses, courses, investment cases…).'
        : ''))
    if (!sure) return
    try {
      await api.delete(`/organizations/${org.id}/?cascade=true`)
      reload()
    } catch (e) {
      alert(e.response?.data?.detail || 'Delete failed')
    }
  }

  const removeBranch = async (org, branch) => {
    if (!confirm(`Delete branch "${branch.name}" and all of its data?`)) return
    try {
      await api.delete(`/branches/${branch.id}/?cascade=true`)
      reload()
    } catch (e) {
      alert(e.response?.data?.detail || 'Delete failed')
    }
  }

  return (
    <div>
      <div className="toolbar row spread">
        <h3>Organizations</h3>
        <div className="row gap">
          <input placeholder="Search…" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
          <button className="btn primary sm" onClick={() => setNewOrg(true)}>+ Add organization</button>
        </div>
      </div>
      <DataTable
        columns={[
          { header: 'Organization', key: 'name' },
          { header: 'Registered', key: 'registration_date' },
          { header: 'Branches', render: (r) => (
            <span className="row gap wrap">
              {(r.branches || []).map((b) => (
                <span key={b.id} className="chip-row">
                  {b.name}
                  <button className="icon-btn" title="Delete branch"
                          onClick={() => removeBranch(r, b)}>✕</button>
                </span>
              ))}
              <button className="btn ghost sm" title="Add branch"
                      onClick={() => setAddBranch(r)}>+ branch</button>
            </span>
          )},
          { header: 'Status', render: (r) => r.status && <StatusPill {...r.status} /> },
          { header: '', render: (r) => (
            <span className="row gap">
              <button className="btn ghost sm" onClick={() => setEditOrg(r)}>Edit</button>
              <button className="btn ghost sm danger" onClick={() => removeOrg(r)}>Delete</button>
            </span>
          )},
        ]}
        rows={orgs || []}
      />
      {newOrg && (
        <Modal title="New organization" onClose={() => setNewOrg(null)}>
          <OrgForm onSaved={() => { setNewOrg(null); reload() }} />
        </Modal>
      )}
      {editOrg && (
        <Modal title={`Edit — ${editOrg.name}`} onClose={() => setEditOrg(null)}>
          <EditOrgForm org={editOrg} onSaved={() => { setEditOrg(null); reload() }} />
        </Modal>
      )}
      {addBranch && (
        <Modal title={`Add branch — ${addBranch.name}`} onClose={() => setAddBranch(null)}>
          <BranchForm orgId={addBranch.id} onSaved={() => { setAddBranch(null); reload() }} />
        </Modal>
      )}
    </div>
  )
}

function EditOrgForm({ org, onSaved }) {
  const [name, setName] = useState(org.name)
  const [status, setStatus] = useState(org.status?.code_name || '')
  const { data: statuses } = useFetch('/organization-statuses/')
  return (
    <>
      <label className="stacked">Organization name<input value={name}
          onChange={(e) => setName(e.target.value)} /></label>
      <label className="stacked">Status
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {(statuses || []).map((s) => <option key={s.id} value={s.code_name}>{s.name}</option>)}
        </select>
      </label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onSaved}>Cancel</button>
        <button className="btn primary" disabled={!name} onClick={async () => {
          await api.patch(`/organizations/${org.id}/`, { name, status })
          onSaved()
        }}>Save changes</button>
      </div>
    </>
  )
}

function BranchForm({ orgId, onSaved }) {
  const [name, setName] = useState('')
  return (
    <>
      <label className="stacked">Branch name<input value={name}
          onChange={(e) => setName(e.target.value)} /></label>
      <div className="row end gap modal-foot">
        <button className="btn ghost" onClick={onSaved}>Cancel</button>
        <button className="btn primary" disabled={!name} onClick={async () => {
          await api.post('/branches/', { organization_id: orgId, name })
          onSaved()
        }}>Create branch</button>
      </div>
    </>
  )
}

function OrgForm({ onSaved }) {
  const [name, setName] = useState('')
  const [branchName, setBranchName] = useState('')
  return (
    <>
      <label className="stacked">Organization name<input value={name}
          onChange={(e) => setName(e.target.value)} /></label>
      <label className="stacked">First branch name<input value={branchName}
          onChange={(e) => setBranchName(e.target.value)} placeholder="optional" /></label>
      <div className="row end modal-foot">
        <button className="btn primary" disabled={!name} onClick={async () => {
          const res = await api.post('/organizations/', { name })
          if (branchName) await api.post('/branches/', {
            organization_id: res.data.id, name: branchName,
          })
          onSaved()
        }}>Create</button>
      </div>
    </>
  )
}

export function HelpCenter() {
  return (
    <div className="card pad help">
      <h2>Help Center</h2>
      <h4>Getting started</h4>
      <ol>
        <li>Pick your branch with the switcher in the top-left.</li>
        <li>Build an application form under Forms and publish it — applicants apply via the public link.</li>
        <li>Move applicants through the Selection Board and score them against a scoring form.</li>
        <li>Enrol selected applicants into a Programme; assign courses and mentors.</li>
        <li>Use Invest on a business to create an investment case in Dealflow, route it through Approval, then manage it under Portfolio & Reports.</li>
      </ol>
    </div>
  )
}

export function PublicApply() {
  const { formId } = useParams()
  const [form, setForm] = useState(null)
  const [values, setValues] = useState({})
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`/api/public/forms/${formId}/`).then(async (r) => {
      if (r.ok) setForm(await r.json())
      else setError('This application form is not available.')
    })
  }, [formId])

  const submit = async () => {
    try {
      // labels let the backend map answers onto the applicant record
      const labels = Object.fromEntries(
        (form?.fields || []).map((f) => [`field_${f.id}`, f.name]))
      const res = await fetch(`/api/public/forms/${formId}/submit/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers: values, labels }),
      })
      if (!res.ok) throw new Error('rejected')
      setDone(true)
    } catch (e) { setError('Submission failed. Please try again.') }
  }

  if (done) return (
    <div className="login-wrap"><div className="card login-card center">
      <h2>Application received ✓</h2>
      <p className="muted">Thank you! Our team will review your application and contact you.</p>
    </div></div>
  )

  return (
    <div className="login-wrap">
      <div className="card login-card wide-form">
        <h2>{form?.name || 'Application form'}</h2>
        <p className="muted">{form?.form_description}</p>
        {error && <div className="alert">{error}</div>}
        {form && (
          <>
            <FormRenderer form={form} values={values} onChange={setValues} />
            <button className="btn primary" onClick={submit}>Submit application</button>
          </>
        )}
      </div>
    </div>
  )
}
