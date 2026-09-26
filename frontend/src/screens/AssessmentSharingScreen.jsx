import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getAssessmentSharing, shareAssessment, revokeAssessmentSharing } from '../utils/Api'

const buttonStyle = { padding: '13px 20px', border: '1px solid #1F6F5C', background: '#1F6F5C', color: '#fff', fontSize: 16, cursor: 'pointer' }

export default function AssessmentSharingScreen() {
  const { roleId, attemptId } = useParams()
  const { user } = useAuth()
  const [notice, setNotice] = useState(null)
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let current = true
    setNotice(null)
    setAccepted(false)
    setError('')
    async function load() {
      try {
        const token = await user.getIdToken()
        const data = await getAssessmentSharing({ token, roleId, attemptId })
        if (current) setNotice(data)
      } catch (e) {
        if (current) setError(e.message || 'The sharing request could not be loaded.')
      }
    }
    if (user) load()
    return () => { current = false }
  }, [user, roleId, attemptId])

  async function submit(revoke = false) {
    if (busy || (!revoke && !accepted)) return
    setBusy(true)
    setError('')
    try {
      const token = await user.getIdToken()
      if (revoke) {
        await revokeAssessmentSharing({ token, shareId: notice.shareId })
        setNotice(n => ({ ...n, shareStatus: 'revoked' }))
      } else {
        const result = await shareAssessment({ token, roleId, attemptId, consentVersion: notice.consentVersion })
        setNotice(n => ({ ...n, shareId: result.shareId, shareStatus: 'shared' }))
      }
    } catch (e) {
      setError(e.message || 'Could not update sharing. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="cc-hiring-page" style={{ minHeight: '100vh', background: '#F4F1EA', padding: '48px 20px', color: '#1a1a1a' }}>
      <section style={{ maxWidth: 560, margin: '0 auto', background: '#FEFDFB', border: '1px solid #ddd', padding: 28 }}>
        <p style={{ color: '#1F6F5C', fontSize: 16 }}>CookCredit</p>
        <h1 style={{ fontFamily: 'var(--cc-display)', fontWeight: 400, fontSize: 32 }}>You choose who can review.</h1>
        {!notice && !error && <p role="status">Loading the sharing request…</p>}
        {error && <p role="alert" style={{ color: '#9b3327' }}>{error}</p>}
        {notice && <>
          <h2 style={{ fontFamily: 'var(--cc-display)', fontWeight: 400 }}>{notice.company}</h2>
          <p>{notice.role}</p>
          <p style={{ fontSize: 16, lineHeight: 1.6 }}>{notice.consentText}</p>
          {notice.shareStatus === 'shared' ? <>
            <p role="status">This assessment is shared with this company.</p>
            <button style={buttonStyle} disabled={busy} onClick={() => submit(true)}>{busy ? 'Revoking…' : 'Revoke access'}</button>
          </> : notice.shareStatus === 'revoked' ? <p role="status">Access revoked. Previously issued playback links expire within five minutes. This grant cannot be reopened.</p>
            : !notice.ready ? <p>This assessment is not ready to share. Wait for verification before continuing.</p>
              : <>
                <label style={{ display: 'flex', gap: 12, padding: '16px 0', lineHeight: 1.5 }}>
                  <input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} disabled={busy} />
                  I agree to share this assessment with {notice.company} for this role.
                </label>
                <button style={{ ...buttonStyle, opacity: accepted && !busy ? 1 : 0.5 }} disabled={!accepted || busy} onClick={() => submit()}>{busy ? 'Sharing…' : 'Share assessment'}</button>
              </>}
          <p style={{ marginTop: 24, fontSize: 14, color: '#666' }}>This permission applies to this assessment only. Your other recordings remain private.</p>
        </>}
      </section>
    </main>
  )
}
