import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { acceptBusinessTeamInvitation } from '../utils/Api'

export default function BusinessInviteAcceptScreen() {
  const { token } = useParams()
  const navigate = useNavigate()
  const { user, refreshProfile } = useAuth()
  const [status, setStatus] = useState('Accepting your workspace invitation…')
  const [failed, setFailed] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return undefined
    started.current = true
    let live = true
    let redirectTimer
    ;(async () => {
      try {
        const idToken = await user.getIdToken(true)
        await acceptBusinessTeamInvitation({ token: idToken, invitationToken: token })
        await refreshProfile()
        if (live) {
          setStatus('Invitation accepted. Opening the workspace…')
          redirectTimer = window.setTimeout(() => navigate('/business/roles', { replace: true }), 500)
        }
      } catch (err) {
        if (live) { setStatus(err.message || 'This invitation could not be accepted.'); setFailed(true) }
      }
    })()
    return () => { live = false; if (redirectTimer) window.clearTimeout(redirectTimer) }
  }, [navigate, refreshProfile, token, user])

  return <main className="cc-hiring-page" style={{ minHeight: '100vh', background: '#F7F4EE', display: 'grid', placeItems: 'center', padding: 24 }}>
    <section style={{ width: '100%', maxWidth: 480, background: '#fff', border: '1px solid #e5e5e5', padding: 28 }}>
      <div style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>CookCredit workspace</div>
      <h1 style={{ fontFamily: 'var(--cc-display)', fontWeight: 400, fontSize: 30, letterSpacing: '-0.04em', margin: '12px 0' }}>{failed ? 'Invitation unavailable' : 'Joining the team'}</h1>
      <p style={{ color: failed ? '#9B341F' : '#666', lineHeight: 1.6 }}>{status}</p>
      {failed && <button onClick={() => navigate('/business', { replace: true })} style={{ border: 0, background: '#1a1a1a', color: '#fff', padding: '11px 15px', marginTop: 10 }}>Return to CookCredit</button>}
    </section>
  </main>
}
