import { useEffect, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { useAuth } from '../context/AuthContext'
import { getEmployerCandidateApplications, saveEmployerReview } from '../utils/Api'
import HiringCvDownload from './HiringCvDownload'

const labels = { reviewing: 'Under review', shortlisted: 'Shortlisted', contacted: 'Contacted', hired: 'Hired', not_selected: 'Not selected' }
const field = { display: 'block', width: '100%', padding: 10, marginTop: 6, border: '1px solid #dedbd4', background: '#fff', color: '#25251f', font: 'inherit' }

function ReviewForm({ application, canReview }) {
  const { user } = useAuth()
  const biz = useBusiness()
  const [review, setReview] = useState(application.review)
  const [published, setPublished] = useState(application.employerUpdate)
  const [status, setStatus] = useState(review?.status || 'reviewing')
  const [notes, setNotes] = useState(review?.notes || '')
  const [message, setMessage] = useState(review?.message || '')
  const [busy, setBusy] = useState(false), [notice, setNotice] = useState(''), [error, setError] = useState('')
  async function save(publish) {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await saveEmployerReview({ token: await user.getIdToken(), applicationId: application.id,
        review: { status, notes, message, publish, revision: review?.revision || null } })
      setReview(result.review); setPublished(result.employerUpdate)
      biz?.refresh?.()
      setNotice(publish ? 'Update published to this applicant. No email was sent.' : 'Private review saved. The applicant has not been notified.')
    } catch (e) { setError(e.message || 'Review could not be saved. Your draft remains here.') }
    finally { setBusy(false) }
  }
  return <section style={{ marginTop: 16, borderTop: '1px solid #e3e0d9', paddingTop: 16 }}>
    <h3 style={{ fontFamily: 'var(--cc-display)', fontSize: 24, margin: '0 0 12px' }}>{application.roleTitle}</h3>
    <p>{application.applicantName}</p>
    {application.hasCv ? <HiringCvDownload applicationId={application.id} getToken={() => user.getIdToken()} /> : <p>No CV was supplied for this application.</p>}
    {application.questions.map(q => <div key={q.id}><strong>{q.label}</strong><p>{Array.isArray(application.answers[q.id]) ? application.answers[q.id].join(', ') : String(application.answers[q.id] ?? 'Not supplied')}</p></div>)}
    <h4>Employer review</h4>
    {review?.updatedAt && <p style={{ fontSize: 12 }}>Last saved by {review.reviewerName || "Company reviewer"}  -  {new Date(review.updatedAt).toLocaleString()}</p>}
    <fieldset disabled={!canReview || busy} style={{ border: 0, margin: 0, padding: 0, display: 'grid', gap: 16 }}>
      <label>Review status<select style={field} value={status} onChange={e => setStatus(e.target.value)}>{Object.entries(labels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Internal notes  -  visible only to your company<textarea style={field} rows={4} maxLength={5000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
      <label>Message for the applicant  -  shared only when published<textarea style={field} rows={3} maxLength={2000} value={message} onChange={e => setMessage(e.target.value)} /></label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button type="button" onClick={() => save(false)} style={{ padding: '12px 16px', border: '1px solid #1F6F5C', color: '#1F6F5C', background: '#fff' }}>Save private review</button>
        <button type="button" disabled={!message.trim()} onClick={() => save(true)} style={{ padding: '12px 16px', border: 0, color: '#fff', background: '#1F6F5C' }}>Publish update to applicant</button>
      </div>
    </fieldset>
    {!canReview && <p>Your company seat can view evidence but cannot save hiring decisions.</p>}
    {status !== (review?.status || 'reviewing') && <p role="status">Status changed. Save private review to apply it.</p>}
    {busy && <p role="status">Saving…</p>}{notice && <p role="status">{notice}</p>}{error && <p role="alert" style={{ color: '#A44320' }}>{error} Reload to see the latest review if another reviewer saved changes.</p>}
    {published && <aside style={{ padding: 14, background: '#f3f1eb', marginTop: 16 }}><strong>Currently visible to the applicant: {labels[published.status]}</strong><p style={{ whiteSpace: 'pre-wrap' }}>{published.message}</p></aside>}
  </section>
}

function ApplicationReview({ cookId, roleId }) {
  const { user } = useAuth()
  const [data, setData] = useState(null), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    if (!user) return undefined
    getTokenAndLoad()
    async function getTokenAndLoad() {
      try { const result = await getEmployerCandidateApplications({ token: await user.getIdToken(), cookId, roleId }); if (active) setData(result) }
      catch (e) { if (active) setError(e.message || 'Applications could not load.') }
    }
    return () => { active = false }
  }, [user, cookId, roleId, retry])
  return <section className="cc-business-card" style={{ padding: 20, marginBottom: 20, background: '#FEFDFB', border: '1px solid #e3e0d9' }}>
    <h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 27, margin: 0 }}>Application & review</h2>
    {error ? <p role="alert">{error} <button onClick={() => { setData(null); setError(''); setRetry(x => x + 1) }}>Retry</button></p> : !data ? <p role="status">Loading application…</p> : data.applications.length ? data.applications.map(a => <ReviewForm key={`${a.id}:${retry}`} application={a} canReview={data.canReview} />) : <p>No active application is shared with your company for this role.</p>}
  </section>
}

export default function EmployerApplicationReview({ cookId, roleId }) {
  const { user } = useAuth()
  return <ApplicationReview key={JSON.stringify([user?.uid,cookId,roleId])} cookId={cookId} roleId={roleId} />
}
