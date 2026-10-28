import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { acceptBusinessTeamInvitation } from '../utils/Api'

export default function BusinessInviteAcceptScreen() {
  const { token } = useParams()
  const navigate = useNavigate()
  const { user, refreshProfile, logout } = useAuth()
  const [status, setStatus] = useState('Accept this invitation to join the workspace. Sign in with the invited email address. Your access is limited to this workspace and the role assigned by its administrator.')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const inFlight = useRef(false)

  async function accept() {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setFailed(false)
    try {
      const idToken = await user.getIdToken(true)
      await acceptBusinessTeamInvitation({ token: idToken, invitationToken: token })
      await refreshProfile()
      navigate('/business/roles', { replace: true })
    } catch (err) {
      setStatus(err.message || 'This invitation could not be accepted. Please try again.')
      setFailed(true)
    } finally { inFlight.current = false; setBusy(false) }
  }

  return <main className="cc-hiring-page" style={{ minHeight: '100vh', background: '#F7F4EE', display: 'grid', placeItems: 'center', padding: 24 }}>
    <section style={{ width: '100%', maxWidth: 480, background: '#fff', border: '1px solid var(--cc-border)', padding: 28 }}>
      <div style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>CookCredit workspace</div>
      <h1 style={{ fontFamily: 'var(--cc-display)', fontWeight: 400, fontSize: 30, letterSpacing: '-0.04em', margin: '12px 0' }}>Join your team</h1>
      <p role={failed ? 'alert' : 'status'} style={{ color: failed ? '#9B341F' : '#666', lineHeight: 1.6 }}>{status}</p>
      <p style={{ color: "#666", overflowWrap: "anywhere" }}>Signed in as {user.email}</p>
      <button disabled={busy} onClick={() => logout()} style={{ display: "block", background: "transparent", color: "var(--cc-ink)", border: "1px solid var(--cc-border)", padding: "10px 14px" }}>Use another account</button>
      <button disabled={busy} onClick={accept} style={{ border: 0, background: 'var(--cc-ink)', color: '#fff', padding: '11px 15px', marginTop: 10 }}>{busy ? 'Joining...' : failed ? 'Retry invitation' : 'Accept invitation'}</button>
    </section>
  </main>
}
