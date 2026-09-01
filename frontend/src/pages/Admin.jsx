import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import FormRenderer from '../components/FormRenderer'
import { useAuth } from '../context/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { DataTable, Pager, Modal, StatusPill } from '../components/ui'
import api from '../api'

export function UsersAdmin() {
  const { branch, can, user: currentUser } = useAuth()
  const [page, setPage] = useState(1)
  const [statusF, setStatusF] = useState('')
  const [roleF, setRoleF] = useState('')
  const [search, setSearch] = useState('')
  const [invite, setInvite] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [deletingUser, setDeletingUser] = useState(null)
  const [rolesOpen, setRolesOpen] = useState(false)
  const pageSize = 12
  const { data: roles, reload: reloadRoles } = useFetch(branch ? `/roles/${branch.id}/` : null)
  const { data: statuses } = useFetch('/user-statuses/')
  const list = useFetch(branch
    ? `/v2/users/${branch.id}/?page=${page}&page_size=${pageSize}&search=${search}&role=${roleF}&status=${statusF}`
    : null)

  const reloadAll = () => {
    list.reload()
    reloadRoles && reloadRoles()
  }

  return (
    <div>
      <div className="toolbar row spread">
        <div>
          <h3>Users & Roles/Permissions</h3>
          <p className="sm muted">Manage branch team members, assign access roles, and configure custom permissions.</p>
        </div>
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
          {
            header: 'User',
            render: (r) => (
              <div>
                <b style={{ color: 'var(--text-main)' }}>{r.first_name} {r.last_name}</b>
                <div className="sm muted">{r.email}</div>
              </div>
            ),
          },
          {
            header: 'Position & Organization',
            render: (r) => (
              <div className="sm">
                <div>{r.position || '—'}</div>
                {r.company && <div className="muted">{r.company}</div>}
              </div>
            ),
          },
          {
            header: 'Assigned Roles',
            render: (r) => (
              <div className="row wrap gap" style={{ gap: '4px' }}>
                {(r.roles || []).length > 0 ? (
                  r.roles.map((x) => (
                    <span
                      key={x.id}
                      className={`pill ${x.code_name === 'branch_admin' || x.code_name === 'organization_admin' ? 'warn' : 'neutral'}`}
                      style={{ fontSize: '11px', padding: '2px 8px' }}
                    >
                      {x.name}
                    </span>
                  ))
                ) : (
                  <span className="sm muted">No roles</span>
                )}
              </div>
            ),
          },
          {
            header: 'Status',
            render: (r) => r.status && <StatusPill {...r.status} />,
          },
          {
            header: 'Actions',
            render: (r) => (
              <div className="row gap" style={{ justifyContent: 'flex-end' }}>
                {can('users.manage') && (
                  <>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => setEditingUser(r)}
                      title="Edit user details and roles"
                      style={{ padding: '3px 8px', fontSize: '12px' }}
                    >
                      Edit
                    </button>
                    {r.id !== currentUser?.id && (
                      <button
                        type="button"
                        className="btn ghost sm danger"
                        onClick={() => setDeletingUser(r)}
                        title="Remove user from this branch"
                        style={{ padding: '3px 8px', fontSize: '12px' }}
                      >
                        Remove
                      </button>
                    )}
                  </>
                )}
              </div>
            ),
          },
        ]}
        rows={list.data?.results || []}
        footer={<Pager page={page} pageSize={pageSize} count={list.data?.count || 0} onPage={setPage} />}
      />

      {invite && (
        <InviteModal
          branchId={branch.id}
          roles={roles || []}
          onClose={() => setInvite(false)}
          onSaved={() => { setInvite(false); reloadAll() }}
        />
      )}

      {editingUser && (
        <EditUserModal
          user={editingUser}
          branchId={branch.id}
          roles={roles || []}
          statuses={statuses || []}
          onClose={() => setEditingUser(null)}
          onSaved={() => { setEditingUser(null); reloadAll() }}
        />
      )}

      {deletingUser && (
        <DeleteUserModal
          user={deletingUser}
          branchId={branch.id}
          onClose={() => setDeletingUser(null)}
          onDeleted={() => { setDeletingUser(null); reloadAll() }}
        />
      )}

      {rolesOpen && (
        <RolesModal branchId={branch.id} onClose={() => { setRolesOpen(false); reloadRoles() }} />
      )}
    </div>
  )
}

function EditUserModal({ user, branchId, roles, statuses, onClose, onSaved }) {
  const [f, setF] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    email: user?.email || '',
    position: user?.position || '',
    company: user?.company || '',
    status: user?.status?.code_name || 'active',
    password: '',
  })
  const [selectedRoleIds, setSelectedRoleIds] = useState(
    new Set((user?.roles || []).map((r) => r.id))
  )
  const [saving, setSaving] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)

  const toggleRole = (roleId) => {
    const next = new Set(selectedRoleIds)
    if (next.has(roleId)) {
      next.delete(roleId)
    } else {
      next.add(roleId)
    }
    setSelectedRoleIds(next)
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setErrorMsg(null)
    try {
      const payload = {
        first_name: f.first_name,
        last_name: f.last_name,
        email: f.email,
        position: f.position,
        company: f.company,
        status: f.status,
        role_ids: Array.from(selectedRoleIds),
      }
      if (f.password.trim()) {
        payload.password = f.password.trim()
      }
      await api.patch(`/users/${branchId}/${user.id}/`, payload)
      onSaved()
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to update user: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={`Edit User: ${user.first_name} ${user.last_name}`} onClose={onClose} wide>
      <form onSubmit={handleSave}>
        {errorMsg && (
          <div className="card pad" style={{ background: '#fdf2f2', borderColor: 'var(--bad-fg)', marginBottom: '14px' }}>
            <b style={{ color: 'var(--bad-fg)' }}>✕ Error:</b> {errorMsg}
          </div>
        )}

        <div className="grid-2 gap">
          <label className="stacked">
            <span>First name</span>
            <input
              type="text"
              required
              value={f.first_name}
              onChange={(e) => setF({ ...f, first_name: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Last name</span>
            <input
              type="text"
              required
              value={f.last_name}
              onChange={(e) => setF({ ...f, last_name: e.target.value })}
            />
          </label>
        </div>

        <div className="grid-2 gap">
          <label className="stacked">
            <span>Email</span>
            <input
              type="email"
              required
              value={f.email}
              onChange={(e) => setF({ ...f, email: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Account Status</span>
            <select
              value={f.status}
              onChange={(e) => setF({ ...f, status: e.target.value })}
            >
              {(statuses || []).map((s) => (
                <option key={s.id} value={s.code_name}>{s.name}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid-2 gap">
          <label className="stacked">
            <span>Position / Title</span>
            <input
              type="text"
              placeholder="e.g. Acceleration Director, Senior Mentor"
              value={f.position}
              onChange={(e) => setF({ ...f, position: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Company / Organization</span>
            <input
              type="text"
              placeholder="e.g. finnpact, Partner Firm"
              value={f.company}
              onChange={(e) => setF({ ...f, company: e.target.value })}
            />
          </label>
        </div>

        {/* Assigned Roles */}
        <div style={{ marginTop: '10px', marginBottom: '14px' }}>
          <label className="stacked">
            <span><b>Assigned Roles in this Branch</b> ({selectedRoleIds.size} selected)</span>
            <span className="sm muted">Select one or more roles to grant permissions for this branch.</span>
          </label>

          <div className="grid-2 gap" style={{ marginTop: '8px' }}>
            {(roles || []).map((r) => {
              const isChecked = selectedRoleIds.has(r.id)
              return (
                <div
                  key={r.id}
                  onClick={() => toggleRole(r.id)}
                  className="card-flat pad"
                  style={{
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderColor: isChecked ? 'var(--accent)' : 'var(--border)',
                    background: isChecked ? 'var(--accent-soft)' : 'var(--bg-card)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div>
                    <b style={{ color: isChecked ? 'var(--accent-strong)' : 'inherit', fontSize: '13.5px' }}>
                      {r.name}
                    </b>
                    <div className="sm muted">
                      <code>{r.code_name}</code> {r.is_constant && '• System'}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                  />
                </div>
              )
            })}
          </div>
          {selectedRoleIds.size === 0 && (
            <p className="sm" style={{ color: 'var(--warn-fg)', marginTop: '6px' }}>
              ⚠️ No roles selected. The user will have no active permissions in this branch.
            </p>
          )}
        </div>

        {/* Admin Password Reset */}
        <details className="card-flat" style={{ padding: '10px', marginBottom: '14px' }}>
          <summary style={{ cursor: 'pointer', fontWeight: '600', fontSize: '13px' }}>
            🔑 Reset User Password (Optional)
          </summary>
          <div style={{ marginTop: '10px' }}>
            <label className="stacked">
              <span>New Password</span>
              <input
                type="password"
                placeholder="Leave blank to keep existing password unchanged"
                value={f.password}
                onChange={(e) => setF({ ...f, password: e.target.value })}
                minLength={6}
              />
            </label>
            <span className="sm muted">Setting a new password will immediately take effect for the user's login.</span>
          </div>
        </details>

        <div className="row end gap modal-foot">
          <button type="button" className="btn ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={saving || !f.email || !f.first_name || !f.last_name}>
            {saving ? 'Saving Changes…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function DeleteUserModal({ user, branchId, onClose, onDeleted }) {
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)

  const handleConfirm = async () => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await api.delete(`/users/${branchId}/${user.id}/`)
      onDeleted()
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to remove user: ' + err.message)
      setSubmitting(false)
    }
  }

  return (
    <Modal title="Remove User from Branch" onClose={onClose}>
      {errorMsg && (
        <div className="card pad" style={{ background: '#fdf2f2', borderColor: 'var(--bad-fg)', marginBottom: '14px' }}>
          <b style={{ color: 'var(--bad-fg)' }}>✕ Error:</b> {errorMsg}
        </div>
      )}

      <p style={{ marginBottom: '14px' }}>
        Are you sure you want to remove <b>{user.first_name} {user.last_name}</b> (<code>{user.email}</code>) from this branch?
      </p>

      <div className="card pad" style={{ background: '#fff9db', borderColor: '#f59f00', fontSize: '12.5px', marginBottom: '14px' }}>
        <b>Notice:</b> This will revoke all role assignments and permissions for this user in this branch.
        If the user is not part of any other branch, their account status will be set to Inactive.
      </div>

      <div className="row end gap modal-foot">
        <button type="button" className="btn ghost" onClick={onClose} disabled={submitting}>
          Cancel
        </button>
        <button type="button" className="btn danger" onClick={handleConfirm} disabled={submitting}>
          {submitting ? 'Removing…' : 'Remove User'}
        </button>
      </div>
    </Modal>
  )
}

function InviteModal({ branchId, roles, onClose, onSaved }) {
  const [f, setF] = useState({
    email: '',
    first_name: '',
    last_name: '',
    position: '',
    company: '',
    password: '',
  })
  const [selectedRoleIds, setSelectedRoleIds] = useState(
    new Set(roles.length > 0 ? [roles[0].id] : [])
  )
  const [saving, setSaving] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)

  const toggleRole = (roleId) => {
    const next = new Set(selectedRoleIds)
    if (next.has(roleId)) {
      next.delete(roleId)
    } else {
      next.add(roleId)
    }
    setSelectedRoleIds(next)
  }

  const handleInvite = async (e) => {
    e.preventDefault()
    if (!f.email || selectedRoleIds.size === 0) return
    setSaving(true)
    setErrorMsg(null)
    try {
      await api.post(`/users/${branchId}/invite/`, {
        ...f,
        role_ids: Array.from(selectedRoleIds),
      })
      onSaved()
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to add user: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add User to Branch" onClose={onClose} wide>
      <form onSubmit={handleInvite}>
        {errorMsg && (
          <div className="card pad" style={{ background: '#fdf2f2', borderColor: 'var(--bad-fg)', marginBottom: '14px' }}>
            <b style={{ color: 'var(--bad-fg)' }}>✕ Error:</b> {errorMsg}
          </div>
        )}

        <div className="grid-2 gap">
          <label className="stacked">
            <span>First name</span>
            <input
              type="text"
              value={f.first_name}
              onChange={(e) => setF({ ...f, first_name: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Last name</span>
            <input
              type="text"
              value={f.last_name}
              onChange={(e) => setF({ ...f, last_name: e.target.value })}
            />
          </label>
        </div>

        <div className="grid-2 gap">
          <label className="stacked">
            <span>Email</span>
            <input
              type="email"
              required
              value={f.email}
              onChange={(e) => setF({ ...f, email: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Initial Password</span>
            <input
              type="password"
              placeholder="Leave blank for default (Welcome123!)"
              value={f.password}
              onChange={(e) => setF({ ...f, password: e.target.value })}
            />
          </label>
        </div>

        <div className="grid-2 gap">
          <label className="stacked">
            <span>Position / Title</span>
            <input
              type="text"
              placeholder="e.g. Program Manager, Mentor"
              value={f.position}
              onChange={(e) => setF({ ...f, position: e.target.value })}
            />
          </label>
          <label className="stacked">
            <span>Company / Organization</span>
            <input
              type="text"
              placeholder="e.g. finnpact"
              value={f.company}
              onChange={(e) => setF({ ...f, company: e.target.value })}
            />
          </label>
        </div>

        {/* Roles Selection */}
        <div style={{ marginTop: '10px', marginBottom: '14px' }}>
          <label className="stacked">
            <span><b>Assign Roles in this Branch</b> ({selectedRoleIds.size} selected)</span>
            <span className="sm muted">Select one or more roles to grant permissions upon addition.</span>
          </label>

          <div className="grid-2 gap" style={{ marginTop: '8px' }}>
            {(roles || []).map((r) => {
              const isChecked = selectedRoleIds.has(r.id)
              return (
                <div
                  key={r.id}
                  onClick={() => toggleRole(r.id)}
                  className="card-flat pad"
                  style={{
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderColor: isChecked ? 'var(--accent)' : 'var(--border)',
                    background: isChecked ? 'var(--accent-soft)' : 'var(--bg-card)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div>
                    <b style={{ color: isChecked ? 'var(--accent-strong)' : 'inherit', fontSize: '13.5px' }}>
                      {r.name}
                    </b>
                    <div className="sm muted">
                      <code>{r.code_name}</code> {r.is_constant && '• System'}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                  />
                </div>
              )
            })}
          </div>
        </div>

        <div className="row end gap modal-foot">
          <button type="button" className="btn ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn primary"
            disabled={saving || !f.email || selectedRoleIds.size === 0}
          >
            {saving ? 'Adding User…' : 'Add User'}
          </button>
        </div>
      </form>
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

export function SystemResetAdmin() {
  const { branch, can } = useAuth()
  const { data: stats, reload, loading } = useFetch(
    branch ? `/system/entrepreneur-data-stats/${branch.id}/` : null
  )
  const [modalMode, setModalMode] = useState(null) // 'wipe' | 'reseed'
  const [confirmInput, setConfirmInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [resultMsg, setResultMsg] = useState(null)
  const [errorMsg, setErrorMsg] = useState(null)

  const handleReset = async () => {
    if (confirmInput.trim().toUpperCase() !== 'RESET') return
    setSubmitting(true)
    setErrorMsg(null)
    setResultMsg(null)
    try {
      const res = await api.post(`/system/reset-entrepreneur-data/${branch.id}/`, {
        mode: modalMode,
        confirmation: confirmInput.trim().toUpperCase(),
      })
      setResultMsg(res.data?.message || 'Data reset completed successfully.')
      setModalMode(null)
      setConfirmInput('')
      reload()
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Reset failed: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="toolbar row spread">
        <div>
          <h3>System Maintenance & Data Reset</h3>
          <p className="muted sm">Manage and reset entrepreneur/startup intake data for <b>{branch?.name}</b></p>
        </div>
        <button className="btn ghost sm" onClick={reload}>Refresh Stats</button>
      </div>

      {resultMsg && (
        <div className="card pad" style={{ background: '#eaf7ef', borderColor: 'var(--ok-fg)', marginBottom: '14px' }}>
          <b style={{ color: 'var(--ok-fg)' }}>✓ Success:</b> {resultMsg}
        </div>
      )}

      {errorMsg && (
        <div className="card pad" style={{ background: '#fdf2f2', borderColor: 'var(--bad-fg)', marginBottom: '14px' }}>
          <b style={{ color: 'var(--bad-fg)' }}>✕ Error:</b> {errorMsg}
        </div>
      )}

      {/* Live Stats */}
      <h4 style={{ margin: '14px 0 8px' }}>Current Data Counts in Branch</h4>
      <div className="grid-3 gap" style={{ marginBottom: '20px' }}>
        <div className="card pad">
          <span className="muted sm">Intake Applicants</span>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--accent)' }}>
            {loading ? '…' : (stats?.applicants_count ?? 0)}
          </div>
          <span className="sm muted">Intake applications & answers</span>
        </div>
        <div className="card pad">
          <span className="muted sm">Cohort Startups</span>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--ok-fg)' }}>
            {loading ? '…' : (stats?.businesses_count ?? 0)}
          </div>
          <span className="sm muted">Enrolled businesses & founders</span>
        </div>
        <div className="card pad">
          <span className="muted sm">Disbursement Batches</span>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--accent-strong)' }}>
            {loading ? '…' : (stats?.disbursements_count ?? 0)}
          </div>
          <span className="sm muted">Processed & draft payouts</span>
        </div>
        <div className="card pad">
          <span className="muted sm">Investment & Dealflow Cases</span>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--warn-fg)' }}>
            {loading ? '…' : (stats?.investment_cases_count ?? 0)}
          </div>
          <span className="sm muted">Dealflow & portfolio pipeline</span>
        </div>
        <div className="card pad">
          <span className="muted sm">Entrepreneur User Accounts</span>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--muted)' }}>
            {loading ? '…' : (stats?.entrepreneurs_count ?? 0)}
          </div>
          <span className="sm muted">Entrepreneur platform logins</span>
        </div>
      </div>

      {/* Actions */}
      <h4 style={{ margin: '14px 0 8px' }}>Available Reset Operations</h4>
      <div className="grid-2 gap">
        <div className="card pad" style={{ borderLeft: '4px solid var(--bad-fg)' }}>
          <div className="row spread" style={{ marginBottom: '8px' }}>
            <b>Option 1: Wipe All Entrepreneur Data (Clean Slate)</b>
            <span className="pill bad">Destructive</span>
          </div>
          <p className="sm muted" style={{ lineHeight: '1.5', marginBottom: '14px' }}>
            Permanently deletes all intake applicants, cohort businesses, founder profiles, evaluation scores,
            disbursement batches, investment cases, course enrollments, and entrepreneur user accounts in this branch.
            <br />
            <br />
            <b>Keeps intact:</b> Program structures, application forms, scoring rubrics, courses, and admin/mentor staff accounts.
          </p>
          <button
            type="button"
            className="btn ghost sm danger"
            onClick={() => { setModalMode('wipe'); setConfirmInput(''); setErrorMsg(null) }}
          >
            Wipe Entrepreneur Data…
          </button>
        </div>

        <div className="card pad" style={{ borderLeft: '4px solid var(--accent)' }}>
          <div className="row spread" style={{ marginBottom: '8px' }}>
            <b>Option 2: Reset & Reload Official Cohort 3 Dataset</b>
            <span className="pill neutral">Cohort 3</span>
          </div>
          <p className="sm muted" style={{ lineHeight: '1.5', marginBottom: '14px' }}>
            Resets all existing data and reloads the official Cohort 3 dataset
            (40 acceleration startups, founder profiles, progress scores,
            and 10 reconciled monthly stipend & prototype voucher disbursement batches totaling 94,750 EUR).
          </p>
          <button
            type="button"
            className="btn primary sm"
            onClick={() => { setModalMode('reseed'); setConfirmInput(''); setErrorMsg(null) }}
          >
            Reset & Reload Cohort 3 Data…
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      {modalMode && (
        <Modal
          title={modalMode === 'wipe' ? '⚠️ Confirm Data Wipe' : '🔄 Confirm Reset & Reload'}
          onClose={() => !submitting && setModalMode(null)}
        >
          <div style={{ padding: '4px 0' }}>
            <div className="alert danger" style={{ marginBottom: '14px', lineHeight: '1.5' }}>
              <b>Warning:</b> This action will permanently remove all current entrepreneur records,
              businesses, evaluations, and disbursements for <b>{branch?.name}</b>.
            </div>

            <p className="sm" style={{ marginBottom: '14px' }}>
              {modalMode === 'wipe'
                ? 'All entrepreneur and applicant data will be wiped clean. The platform will be completely empty and ready for fresh real-world submissions.'
                : 'All current data will be cleared and replaced with the official Cohort 3 dataset (40 startups, founders, and 10 reconciled disbursement batches).'}
            </p>

            <label className="stacked">
              <span>To confirm, please type <b>RESET</b> in capital letters:</span>
              <input
                type="text"
                placeholder="RESET"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                autoFocus
                disabled={submitting}
              />
            </label>

            <div className="row end gap modal-foot">
              <button
                type="button"
                className="btn ghost"
                onClick={() => setModalMode(null)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn ${modalMode === 'wipe' ? 'danger' : 'primary'}`}
                disabled={confirmInput.trim().toUpperCase() !== 'RESET' || submitting}
                onClick={handleReset}
              >
                {submitting ? 'Processing…' : modalMode === 'wipe' ? 'Permanently Wipe Data' : 'Reset & Re-Seed'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

