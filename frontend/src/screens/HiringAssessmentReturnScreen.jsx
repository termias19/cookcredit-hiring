import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getHiringAssessmentSession } from '../utils/Api'

export default function HiringAssessmentReturnScreen() {
  const { sessionId } = useParams(), { user } = useAuth(), navigate = useNavigate()
  const [error, setError] = useState(''), [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    ;(async () => {
      try {
        const result = await getHiringAssessmentSession({ token: await user.getIdToken(), sessionId })
        if (!active) return
        if (!result.session?.applicationId) throw new Error('Your application could not be located. Please retry.')
        navigate(`/application/${result.session.applicationId}`, { replace: true })
      } catch (cause) { if (active) setError(cause.message || 'Your application could not be opened. Please retry.') }
    })()
    return () => { active = false }
  }, [sessionId, user, navigate, retry])
  return <main className="cc-hiring-page" style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', padding: 28 }}>
    <div>{error ? <><p role="alert">{error}</p><button onClick={() => { setError(''); setRetry(value => value + 1) }} style={{ marginTop: 16, padding: '12px 22px', border: 0, background: '#1F6F5C', color: '#fff' }}>Retry</button></> : <p role="status">Opening your application…</p>}</div>
  </main>
}
