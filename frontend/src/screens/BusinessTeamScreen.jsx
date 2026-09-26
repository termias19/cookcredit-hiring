/** Persisted workspace members and expiring, email-bound invitations. */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Copy, Mail, UserPlus, X } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useBusiness } from '../context/BusinessContext'
import {
  getBusinessTeam, inviteBusinessTeamMember, revokeBusinessTeamInvitation,
} from '../utils/Api'

const SERIF = "var(--cc-display)"
const ROLES = [
  ['recruiter', 'Recruiter'], ['hiring_manager', 'Hiring manager'],
  ['viewer', 'Viewer'], ['admin', 'Admin'],
]

export default function BusinessTeamScreen() {
  const navigate = useNavigate()
  const biz = useBusiness()
  const [team, setTeam] = useState({ members: [], invitations: [], canManage: false })
  const [status, setStatus] = useState('loading')
  const [email, setEmail] = useState('')
  const [seatRole, setSeatRole] = useState('recruiter')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const getToken = biz?.getToken

  const load = useCallback(async () => {
    const token = await getToken?.()
    if (!token) { setStatus('error'); return }
    try {
      const result = await getBusinessTeam({ token })
      setTeam({ members: result.members || [], invitations: result.invitations || [], canManage: Boolean(result.canManage) })
      setStatus('ready')
    } catch (err) {
      setError(err.message || 'Team could not be loaded')
      setStatus('error')
    }
  }, [getToken])

  useEffect(() => { load() }, [load])

  async function invite() {
    if (!email.trim() || busy) return
    setBusy(true); setError(''); setCreated(null)
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

  async function revoke(id) {
    setBusy(true); setError('')
    try {
      const token = await getToken()
      await revokeBusinessTeamInvitation({ token, invitationId: id })
      await load()
    } catch (err) { setError(err.message || 'Invitation could not be revoked') }
    finally { setBusy(false) }
  }

  const header = <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
    <button onClick={() => navigate('/business/roles')} style={back}><ArrowLeft size={14} /><span>{biz?.org?.name || 'Workspace'}</span></button>
    <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>Team</h1>
  </div>

  return <BusinessShell header={header} showNav={false}>
    <div style={{ padding: '24px 28px 40px', maxWidth: 760, margin: '0 auto' }}>
      <p style={explain}>Choose who can review applicants and who can manage your workspace. Only admins can change billing and integration settings.</p>
      {status === 'loading' && <p style={muted}>Loading team…</p>}
      {error && <div role="alert" style={alert}>{error}</div>}

      {team.members.map(member => <div className="cc-business-card" key={member.id} style={row}>
        <Mail size={16} color="#888" />
        <div style={{ flex: 1 }}><strong>{member.name || member.email}</strong><div style={muted}>{member.email}</div></div>
        <span style={badge}>{member.seatRole.replace('_', ' ')}</span>
      </div>)}
      {team.invitations.filter(item => item.status === 'pending').map(item => <div className="cc-business-card" key={item.id} style={row}>
        <Mail size={16} color="#C9A227" />
        <div style={{ flex: 1 }}><strong>{item.email}</strong><div style={muted}>Pending until {new Date(item.expiresAt).toLocaleDateString()}</div></div>
        <span style={badge}>{item.seatRole.replace('_', ' ')}</span>
        {team.canManage && <button aria-label="Revoke invitation" onClick={() => revoke(item.id)} disabled={busy} style={iconButton}><X size={14} /></button>}
      </div>)}

      {team.canManage && <div className="cc-business-card" style={panel}>
        <div style={label}>Invite a teammate</div>
        <input aria-label="Teammate email" value={email} onChange={event => setEmail(event.target.value)} type="email" placeholder="teammate@company.com" style={input} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '9px 0' }}>
          {ROLES.map(([value, name]) => <button key={value} onClick={() => setSeatRole(value)} style={{ ...choice, ...(seatRole === value ? choiceOn : {}) }}>{name}</button>)}
        </div>
        <button onClick={invite} disabled={busy || !email.trim()} style={{ ...primary, opacity: busy || !email.trim() ? 0.5 : 1 }}><UserPlus size={15} />{busy ? 'Saving…' : 'Create invitation'}</button>
        <p style={muted}>Team seats require an active Team or Enterprise subscription. Invitations expire after seven days and only the invited verified email can accept.</p>
      </div>}

      {created && <div style={{ ...panel, borderColor: '#A8D5C8', background: '#F5FBF8' }}>
        <strong>Invitation recorded</strong>
        <p style={{ ...muted, margin: '6px 0 10px' }}>{created.emailDelivered ? 'Email delivered. You can also copy the link.' : 'Email delivery is not configured or failed. Copy this one-time link now.'}</p>
        <button onClick={() => navigator.clipboard?.writeText(created.inviteUrl)} style={secondary}><Copy size={14} />Copy invitation link</button>
      </div>}
    </div>
  </BusinessShell>
}

const back = { display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 0, cursor: 'pointer', padding: 0, marginBottom: 10, fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }
const explain = { color: '#666', fontSize: 13, lineHeight: 1.6, margin: '0 0 16px' }
const muted = { color: '#74756f', fontSize: 11, margin: '3px 0 0' }
const alert = { background: '#FFF3F0', color: '#9B341F', padding: 10, marginBottom: 12, fontSize: 12 }
const row = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, border: '1px solid #E3E0D9', background: '#FEFDFB', borderRadius: 2, padding: 14, marginBottom: 9 }
const badge = { fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', color: '#526057', background: '#E9F3E9', borderRadius: 2, padding: '5px 8px' }
const panel = { border: '1px solid #E3E0D9', background: '#FEFDFB', borderRadius: 2, padding: 16, marginTop: 18 }
const label = { fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', color: '#777', marginBottom: 8 }
const input = { width: '100%', padding: '11px 12px', border: '1px solid #E3E0D9', background: '#fff', borderRadius: 2, fontSize: 14 }
const choice = { border: '1px solid #E3E0D9', background: '#fff', color: '#526057', borderRadius: 2, padding: '7px 11px', fontSize: 11, cursor: 'pointer' }
const choiceOn = { borderColor: '#1F6F5C', background: '#1F6F5C', color: '#fff' }
const primary = { width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, border: 0, borderRadius: 2, background: '#1F6F5C', color: '#fff', fontWeight: 500, padding: 12, cursor: 'pointer' }
const secondary = { display: 'inline-flex', alignItems: 'center', gap: 7, border: '1px solid #1F6F5C', borderRadius: 2, background: '#FEFDFB', color: '#1F6F5C', padding: '9px 12px', cursor: 'pointer' }
const iconButton = { border: 0, background: 'none', color: '#74756f', cursor: 'pointer', padding: 4 }
