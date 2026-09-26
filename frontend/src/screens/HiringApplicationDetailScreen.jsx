import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import AccountShell from '../components/AccountShell'
import HiringCvDownload from '../components/HiringCvDownload'
import AttemptStatus from '../components/AttemptStatus'
import { useAuth } from '../context/AuthContext'
import { getHiringApplication, startHiringAttempt, withdrawHiringApplication } from '../utils/Api'

export default function HiringApplicationDetailScreen() {
  const { applicationId } = useParams()
  const { user } = useAuth()
  const [application, setApplication] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true, timer
    async function load() {
      try {
        const result = await getHiringApplication({ token: await user.getIdToken(), applicationId })
        if (!active) return
        setApplication(result.application); setError('')
        if (result.application.status === 'assessment_processing') timer = setTimeout(load, 5000)
      } catch (e) { if (active) setError(e.message || 'Your application could not be loaded.') }
    }
    load()
    return () => { active = false; clearTimeout(timer) }
  }, [applicationId, user, revision])
  async function start() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const result = await startHiringAttempt({ token: await user.getIdToken(), applicationId })
      window.location.assign(result.launchUrl)
    } catch (e) { setError(e.message || 'The assessment could not be opened.'); setBusy(false) }
  }
  async function withdraw() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const result = await withdrawHiringApplication({ token: await user.getIdToken(), applicationId })
      setApplication(current => ({ ...current, ...result.application })); setConfirmWithdraw(false)
    } catch (e) { setError(e.message || 'Your application could not be withdrawn.') }
    finally { setBusy(false) }
  }
  return <AccountShell title={application?.role?.title || 'Your application'} intro={application?.company?.name || 'Your CookCredit assessment and submission history.'}>
    {error && <div role="alert" style={{ marginBottom: 20, color: '#A44320' }}><p>{error}</p><button onClick={() => setRevision(value => value + 1)}>Refresh application</button></div>}
    {!application && !error && <p role="status">Loading application…</p>}
    {application && <>
      {application.applicantName && <p>{application.applicantName}</p>}
      {application.employerUpdate && <section className="cc-business-card" style={{ padding: 20, margin: '16px 0', border: '1px solid var(--cc-border)' }}><h2 className="cc-profile-heading">Employer update</h2><p style={{ textTransform: 'capitalize' }}>{application.employerUpdate.status.replaceAll('_', ' ')}</p><p style={{ whiteSpace: 'pre-wrap' }}>{application.employerUpdate.message}</p><p>{new Date(application.employerUpdate.updatedAt).toLocaleString()}</p></section>}
      {application.hasCv && <HiringCvDownload applicationId={application.id} getToken={() => user.getIdToken()} />}
      <AttemptStatus application={application} onStart={start} starting={busy} />
      <section style={{ marginTop: 24, border: '1px solid var(--cc-border)', padding: 24 }}>
        <h2 className="cc-profile-heading">Your submitted answers</h2>
        {(application.questions || []).map(question => {
          const answer = application.answers?.[question.id]
          return <div key={question.id} style={{ marginBottom: 16, fontSize: 14 }}><p style={{ color: 'var(--cc-muted)', marginBottom: 6 }}>{question.label}</p><p>{answer == null || answer === '' ? 'Not supplied' : typeof answer === 'boolean' ? (answer ? 'Yes' : 'No') : Array.isArray(answer) ? answer.join(', ') : String(answer)}</p></div>
        })}
        {!application.questions?.length && <p style={{ fontSize: 14, color: 'var(--cc-muted)' }}>This employer did not request additional answers.</p>}
      </section>
      {application.status !== 'withdrawn' && <section style={{ marginTop: 24, fontSize: 13, lineHeight: 1.7 }}>
        <p>Your employer can review the evidence shared for this application. Withdrawing stops future recording access; existing playback links expire within five minutes.</p>
        {confirmWithdraw ? <div style={{ marginTop: 12 }}><p>Withdraw this application? You will no longer be able to submit attempts for it.</p><button disabled={busy} onClick={withdraw} style={{ padding: '10px 16px', margin: '10px 12px 0 0' }}>{busy ? 'Withdrawing…' : 'Confirm withdrawal'}</button><button disabled={busy} onClick={() => setConfirmWithdraw(false)} style={{ padding: '10px 16px' }}>Keep application</button></div> : <button disabled={busy} onClick={() => setConfirmWithdraw(true)} style={{ padding: '10px 16px', marginTop: 12 }}>Withdraw application</button>}
      </section>}
    </>}
  </AccountShell>
}
