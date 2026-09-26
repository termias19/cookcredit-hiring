import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CircleAlert, LoaderCircle, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getHiringAssessmentSession } from '../utils/Api'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C'

export default function HiringAssessmentReturnScreen() {
  const { sessionId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!user) return
    try {
      const token = await user.getIdToken()
      const result = await getHiringAssessmentSession({ token, sessionId })
      setSession(result.session); setError('')
    } catch (cause) { setError(cause.message || 'The assessment status could not be loaded.') }
  }, [user, sessionId])

  useEffect(() => {
    const initial = window.setTimeout(refresh, 0)
    const timer = window.setInterval(refresh, 5000)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh])

  const done = session?.status === 'completed'
  const processing = session?.status === 'processing'
  const notSubmitted = session?.status === 'started'
  const expired = session?.status === 'expired'
  return <main className="cc-hiring-page" style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', background: '#F7F5F0', padding: 20 }}>
    <section style={{ width: 'min(100%, 520px)', background: '#fff', border: '1px solid #dedbd4', padding: 'clamp(24px, 6vw, 42px)', textAlign: 'center' }}>
      {error || expired || notSubmitted ? <CircleAlert size={32} color="#A44320" /> : done ? <ShieldCheck size={36} color={GREEN} /> : <LoaderCircle size={34} color={GREEN} style={{ animation: 'spin 1.2s linear infinite' }} />}
      <p style={{ fontSize: 10, letterSpacing: 2.5, textTransform: 'uppercase', color: '#999', margin: '17px 0 8px' }}>CookCredit assessment</p>
      <h1 style={{ fontFamily: SERIF, fontSize: 30, fontWeight: 400, margin: '0 0 10px' }}>
        {error ? 'Status unavailable' : done ? 'Your result is ready' : processing ? 'Your assessment is being saved' : notSubmitted ? 'No assessment submitted yet' : expired ? 'This attempt has expired' : 'Checking your assessment'}
      </h1>
      <p style={{ color: '#666', fontSize: 14, lineHeight: 1.6, margin: '0 0 22px' }}>
        {error || (done
          ? 'Your assessment report is attached to your application. Review the measurements and recording before choosing another attempt.'
          : processing ? 'We’re attaching your live assessment and recording to your application. Your employer reviews the measurements and recording; scores are not independently verified.'
            : notSubmitted ? 'Return to your application to resume this attempt. Nothing has been submitted to the employer yet.'
              : expired ? 'Return to your application to start again. An expired, unsubmitted attempt does not use one of your completed attempts.'
                : 'We’re checking whether your recording was submitted.')}
      </p>
      {session?.result?.score != null && <div style={{ borderTop: '1px solid #eee', borderBottom: '1px solid #eee', padding: '16px 0', marginBottom: 22 }}>
        <strong style={{ fontFamily: SERIF, fontSize: 42, fontWeight: 400 }}>{session.result.score}</strong><span style={{ color: '#999' }}> / 100</span>
        <p style={{ fontSize: 12, color: '#666', margin: '6px 0 0' }}>{session.result.calculation?.resultReason}</p>
      </div>}
      <button onClick={() => session?.applicationId ? navigate(`/application/${session.applicationId}`) : refresh()} style={{ width: '100%', border: 0, background: '#1a1a1a', color: '#fff', padding: 14, cursor: 'pointer' }}>
        {session?.applicationId ? 'Return to application' : 'Try again'}
      </button>
    </section>
  </main>
}
