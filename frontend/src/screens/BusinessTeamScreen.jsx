/** Persisted workspace members and expiring, email-bound invitations. */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Copy, Mail, UserPlus, X } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useBusiness } from '../context/BusinessContext'
import {
  getBusinessTeam, inviteBusinessTeamMember, revokeBusinessTeamInvitation, changeBusinessMember,
} from '../utils/Api'

const SERIF = "var(--cc-display)"
const ROLES = [
  ['recruiter', 'Recruiter'], ['hiring_manager', 'Hiring manager'],
  ['viewer', 'Viewer'], ['admin', 'Admin'],
]
const ROLE_HELP = {
  admin: 'Manage team, company, billing and integrations; review applicants and edit roles.',
  hiring_manager: 'Edit roles and review applicants and shared assessment evidence. No team or billing control.',
  recruiter: 'Edit roles and review applicants and shared assessment evidence. No team or billing control.',
  viewer: 'View the workspace and role list. No applicant records, videos or editing.',
}

function MemberControls({ member, disabled, onSave }) {
  const [role, setRole] = useState(member.seatRole)
  return <div style={{ width: '100%' }}>
    <label style={muted}>Team role for {member.name || member.email}
      <select value={role} onChange={event => setRole(event.target.value)} disabled={disabled} style={input}>
        {ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
    <p style={muted}>{ROLE_HELP[role]}</p>
    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
      <button style={secondary} disabled={disabled || role === member.seatRole} onClick={() => onSave(member, role)}>Save role</button>
      <button style={secondary} disabled={disabled} onClick={() => onSave(member, null)}>Remove access</button>
    </div>
  </div>
}

export default function BusinessTeamScreen({ embedded = false } = {}) {
  const navigate = useNavigate()
  const biz = useBusiness()
  const [team, setTeam] = useState({ members: [], invitations: [], canManage: false, invitationAccess: null })
  const [status, setStatus] = useState('loading')
  const [email, setEmail] = useState('')
  const [seatRole, setSeatRole] = useState('recruiter')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const [copyStatus, setCopyStatus] = useState('')
  const invitationsAvailable = team.invitationAccess?.enabled ?? ['team', 'integration', 'enterprise'].includes(biz?.org?.plan)
  const getToken = biz?.getToken

  const load = useCallback(async () => {
    setStatus('loading'); setError('')
    try {
      const token = await getToken?.()
      if (!token) throw new Error('Sign in again to load your team.')
      const result = await getBusinessTeam({ token })
      setTeam({ members: result.members || [], invitations: result.invitations || [], canManage: Boolean(result.canManage), invitationAccess: result.invitationAccess || null })
      setStatus('ready')
    } catch (err) {
      setError(err.message || 'Team could not be loaded')
      setStatus('error')
    }
  }, [getToken])

  useEffect(() => { load() }, [load])

  async function invite() {
    if (!email.trim() || busy || !invitationsAvailable) return
    setBusy(true); setError(''); setCreated(null); setCopyStatus('')
    try {
      const token = await getToken()
      const result = await inviteBusinessTeamMember({ token, email: email.trim(), seatRole })
      setCreated(result.invitation)
      setEmail('')
      await load()
    } catch (err) {
      setError(err.message || 'Invitation could not be created')
    } finally { setBusy(false) }
  }

  async function copyInvitation() {
    try {
      await navigator.clipboard.writeText(created.inviteUrl)
      setCopyStatus('Invitation link copied.')
    } catch { setCopyStatus('Could not copy automatically. Select and copy the link below.') }
  }

  async function revoke(id) {
    setBusy(true); setError('')
    try {
      const token = await getToken()
      await revokeBusinessTeamInvitation({ token, invitationId: id })
      await load()
    } catch (err) { setError(err.message || 'Invitation could not be revoked') }
    finally { setBusy(false) }
  }

  async function saveMember(member, role) {
    if (busy) return
    const action = role ? `Change ${member.name || member.email} to ${role.replaceAll('_', ' ')}?` : `Remove ${member.name || member.email} from this workspace? They will need a new invitation to return.`
    if (!window.confirm(action)) return
    setBusy(true); setError('')
    try {
      await changeBusinessMember({ token: await getToken(), memberId: member.id, seatRole: role, remove: role === null })
      await load()
      biz.refresh()
    } catch (err) { setError(err.message || 'Team access could not be changed') }
    finally { setBusy(false) }
  }

  const header = <div style={{ background: 'var(--cc-surface)', borderBottom: '1px solid var(--cc-border)', padding: '20px 28px' }}>
    <button onClick={() => navigate('/business/roles')} style={back}><ArrowLeft size={14} /><span>{biz?.org?.name || 'Workspace'}</span></button>
    <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: 'var(--cc-ink)', margin: 0 }}>Team</h1>
  </div>

  return <BusinessShell embedded={embedded} header={embedded ? null : header} showNav={false}>
    <div style={{ padding: '24px 28px 40px', maxWidth: 760, margin: '0 auto' }}>
      <p style={explain}>Choose who can review applicants and who can manage your workspace. Only admins can change billing and integration settings.</p>
      {status === 'loading' && <p style={muted}>Loading team…</p>}
      {error && <div role="alert" style={alert}>{error}</div>}
      {status === 'error' && <button onClick={load} style={secondary}>Retry loading team</button>}

      {team.members.map(member => <div className="cc-business-card" key={member.id} style={row}>
        <Mail size={16} color="#888" />
        <div style={{ flex: 1 }}><strong>{member.name || member.email}</strong><div style={muted}>{member.email}</div></div>
        <span style={badge}>{member.seatRole.replace('_', ' ')}</span>
        {team.canManage && <MemberControls key={`${member.id}:${member.seatRole}`} member={member} disabled={busy} onSave={saveMember} />}
      </div>)}
      {team.invitations.filter(item => item.status === 'pending').map(item => <div className="cc-business-card" key={item.id} style={row}>
        <Mail size={16} color="#C9A227" />
        <div style={{ flex: 1 }}><strong>{item.email}</strong><div style={muted}>Pending until {new Date(item.expiresAt).toLocaleDateString()}</div></div>
        <span style={badge}>{item.seatRole.replace('_', ' ')}</span>
        {team.canManage && <button aria-label="Revoke invitation" onClick={() => revoke(item.id)} disabled={busy} style={iconButton}><X size={14} /></button>}
      </div>)}

      {status === 'ready' && team.canManage && !invitationsAvailable && <p role="status" style={explain}>Team invitations are not enabled for this workspace. Your current hiring access remains available. Contact CookCredit to arrange team access.</p>}
      {status === 'ready' && team.canManage && invitationsAvailable && <div className="cc-business-card" style={panel}>
        <div style={label}>Invite a teammate</div>
        <input aria-label="Teammate email" value={email} onChange={event => setEmail(event.target.value)} type="email" placeholder="teammate@company.com" style={input} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '9px 0' }}>
          {ROLES.map(([value, name]) => <button key={value} onClick={() => setSeatRole(value)} style={{ ...choice, ...(seatRole === value ? choiceOn : {}) }}>{name}</button>)}
        </div>
        <p style={{ ...muted, marginBottom: 12 }}>{ROLE_HELP[seatRole]}</p>
        <button onClick={invite} disabled={busy || !email.trim()} style={{ ...primary, opacity: busy || !email.trim() ? 0.5 : 1 }}><UserPlus size={15} />{busy ? 'Saving…' : 'Create invitation'}</button>
        <p style={muted}>{team.invitationAccess?.seatLimit ? `${team.invitationAccess.seatLimit} seats include members and pending invitations. ` : ''}Invitations expire after seven days. The invited email must be verified and approved by CookCredit before joining.</p>
      </div>}

      {created && <div style={{ ...panel, borderColor: '#A8D5C8', background: '#F5FBF8' }}>
        <strong>Invitation recorded</strong>
        <p style={{ ...muted, margin: '6px 0 10px' }}>{created.emailQueued ? 'Invitation email queued for delivery. You can also copy the link.' : created.emailDelivered ? 'Invitation email accepted for sending. Inbox receipt is not confirmed. You can also copy the link.' : 'The invitation was saved, but its email was not sent. Copy the link below and share it with the invited teammate.'}</p>
        <button onClick={copyInvitation} style={secondary}><Copy size={14} />Copy invitation link</button>
        {copyStatus && <p role="status" style={muted}>{copyStatus}</p>}
        <input aria-label="Invitation link" readOnly value={created.inviteUrl} onFocus={event => event.target.select()} style={{ ...input, marginTop: 10 }} />
      </div>}
    </div>
  </BusinessShell>
}

const back = { display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 0, cursor: 'pointer', padding: 0, marginBottom: 10, fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }
const explain = { color: '#666', fontSize: 13, lineHeight: 1.6, margin: '0 0 16px' }
const muted = { color: '#74756f', fontSize: 11, margin: '3px 0 0' }
const alert = { background: '#FFF3F0', color: '#9B341F', padding: 10, marginBottom: 12, fontSize: 12 }
const row = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, border: '1px solid var(--cc-border)', background: 'var(--cc-surface)', borderRadius: 2, padding: 14, marginBottom: 9 }
const badge = { fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', color: '#526057', background: '#E9F3E9', borderRadius: 2, padding: '5px 8px' }
const panel = { border: '1px solid var(--cc-border)', background: 'var(--cc-surface)', borderRadius: 2, padding: 16, marginTop: 18 }
const label = { fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', color: '#777', marginBottom: 8 }
const input = { width: '100%', padding: '11px 12px', border: '1px solid var(--cc-border)', background: '#fff', borderRadius: 2, fontSize: 14 }
const choice = { border: '1px solid var(--cc-border)', background: '#fff', color: '#526057', borderRadius: 2, padding: '7px 11px', fontSize: 11, cursor: 'pointer' }
const choiceOn = { borderColor: 'var(--cc-forest)', background: 'var(--cc-forest)', color: '#fff' }
const primary = { width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, border: 0, borderRadius: 2, background: 'var(--cc-forest)', color: '#fff', fontWeight: 500, padding: 12, cursor: 'pointer' }
const secondary = { display: 'inline-flex', alignItems: 'center', gap: 7, border: '1px solid var(--cc-forest)', borderRadius: 2, background: 'var(--cc-surface)', color: 'var(--cc-forest)', padding: '9px 12px', cursor: 'pointer' }
const iconButton = { border: 0, background: 'none', color: '#74756f', cursor: 'pointer', padding: 4 }
