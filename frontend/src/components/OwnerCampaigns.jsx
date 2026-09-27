import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import http from '../utils/http'

const empty = { subject: '', body: '', postalAddress: '', intervalDays: 0 }
const templates = [
  { subject: 'Make your next CookCredit hiring invitation count', body: 'Ready to invite applicants? Open your CookCredit Hiring workspace, choose an open role and share its application link. Your team can review the profile, CV and assessment the applicant chooses to share.\n\nVisit https://hiring.cookcredit.com to return to your workspace.' },
  { subject: 'Keep your CookCredit profile ready for your next opportunity', body: 'You can update your CookCredit profile and CV from your account. When an employer sends you an application link, use that link to apply to the correct role. You choose whether to share your assessment with the employer.\n\nVisit https://hiring.cookcredit.com to open your account.' },
]
export default function OwnerCampaigns() {
  const { user } = useAuth()
  const [data, setData] = useState(null), [form, setForm] = useState(null), [when, setWhen] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const call = async (path = '', options = {}) => http('/api/customer-mail/owner/campaigns' + path, { ...options, token: await user.getIdToken(), throwOnError: true })
  async function load(cursor = '') {
    setBusy(true); setError('')
    try { setData(await call(cursor ? '?cursor=' + encodeURIComponent(cursor) : '')) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function act(row, action) {
    setBusy(true); setError(''); setNotice('')
    try {
      const body = { ...row, action }
      if (action === 'schedule') body.nextRunAt = new Date(when).toISOString()
      await call(row.id ? '/' + row.id : '', { method: row.id ? 'PUT' : 'POST', body })
      setData(await call()); setForm(null)
      setNotice(action === 'schedule' ? 'Scheduled for opted-in accounts. You can pause or trash it here.' : 'Campaign saved. Paused or trashed campaigns stop unsent messages; messages already in flight may still arrive.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <details className="cc-access-request" onToggle={e => { if (e.currentTarget.open && !data && !busy) load() }}>
    <summary>Email campaigns</summary>
    <p>Prepare offers for accounts that explicitly subscribe. Account and payment messages send separately. No campaign is sent until you schedule it.</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {data && <>
      <p>{data.audience} opted-in accounts. Delivery totals: {Object.entries(data.deliveryCounts).map(([status, count]) => `${count} ${status}`).join(', ') || 'None yet'}.</p>
      <button disabled={busy} onClick={() => { setForm({ ...empty }); setWhen('') }}>New draft</button>{' '}
      <button disabled={busy} onClick={() => load()}>Refresh</button>
      {templates.map((template, index) => <button key={index} disabled={busy} onClick={() => { setForm({ ...empty, ...template }); setWhen('') }}>Use {index ? 'applicant' : 'employer'} template</button>)}
      {form && <form onSubmit={e => { e.preventDefault(); act(form, 'save') }} style={{ display: 'grid', gap: 16, margin: '20px 0' }}>
        <label>Subject<input required maxLength={150} value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} /></label>
        <label>Message<textarea required rows={7} maxLength={10000} value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} /></label>
        <label>Business mailing address<textarea maxLength={500} value={form.postalAddress} onChange={e => setForm({ ...form, postalAddress: e.target.value })} /></label>
        <label>Repeat<select value={form.intervalDays} onChange={e => setForm({ ...form, intervalDays: Number(e.target.value) })}><option value={0}>Once</option><option value={7}>Weekly</option><option value={30}>Every 30 days</option></select></label>
        <label>Send at (your local time)<input type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} /></label>
        <details><summary>Preview message</summary><h3>{form.subject}</h3><p style={{ whiteSpace: 'pre-wrap' }}>{form.body}</p><p>Advertisement from CookCredit · Unsubscribe from offers</p><p style={{ whiteSpace: 'pre-wrap' }}>{form.postalAddress}</p></details>
        <button disabled={busy}>Save draft</button>
        {form.id && <button type="button" disabled={busy || !when || !form.postalAddress.trim()} onClick={() => act(form, 'schedule')}>Schedule for opted-in accounts</button>}
        <button type="button" disabled={busy} onClick={() => setForm(null)}>Cancel</button>
      </form>}
      {data.campaigns.map(row => <article key={row.id} style={{ borderTop: '1px solid #ddd', padding: '18px 0' }}>
        <h3>{row.subject}</h3><p>{row.status}{row.nextRunAt ? ' · ' + new Date(row.nextRunAt).toLocaleString() : ''}</p>
        {row.status !== 'trashed' && <><button disabled={busy} onClick={() => { setForm({ ...row }); setWhen('') }}>Edit / schedule</button>{' '}<button disabled={busy} onClick={() => act(row, 'pause')}>Pause</button>{' '}<button disabled={busy} onClick={() => act(row, 'trash')}>Move to trash</button></>}
        {row.status === 'trashed' && <button disabled={busy} onClick={() => act(row, 'restore')}>Restore draft</button>}
      </article>)}
      {data.nextCursor && <button disabled={busy} onClick={() => load(data.nextCursor)}>Next page</button>}
    </>}
  </details>
}
