import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import OwnerPricing from '../components/OwnerPricing'
import CookCreditBrand from '../components/CookCreditBrand'
import http from '../utils/http'
import '../styles/access.css'

const STATUS = ['pending', 'approved', 'declined', 'revoked', 'all']
const date = value => value ? new Date(value).toLocaleString() : 'Not yet'

export default function OwnerAccessScreen() {
  const { user, profile } = useAuth()
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState({ requests: [], nextCursor: null, inbox: {} })
  const [cursor, setCursor] = useState('')
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [history, setHistory] = useState({})
  const [manual, setManual] = useState({ email: '', name: '', company: '' })
  const allowed = profile?.isAccessOwner === true
  const call = useCallback(async (path, opts = {}) => http('/api/access/owner' + path, {
    ...opts, token: await user.getIdToken(), throwOnError: true,
  }), [user])
  useEffect(() => {
    let live = true
    if (!allowed) return undefined
    setLoading(true); setError('')
    call(`/requests?status=${status}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`).then(data => {
      if (live) setPage(data)
    }).catch(err => { if (live) setError(err.message) }).finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [allowed, call, status, cursor, reload])
  async function decide(row, action, sendEmail = false) {
    if (busy) return
    setBusy(row.id); setError(''); setNotice('')
    try {
      await call(`/requests/${row.id}/decision`, { method: 'POST', body: { action, revision: row.revision, sendEmail } })
      setNotice(action === 'resend' || sendEmail ? 'Access approved. The invitation email is queued; refresh to see delivery status.' : action === 'approve' ? 'Access approved. No invitation email was requested.' : `Access ${action === 'decline' ? 'declined' : 'revoked'}. No email was sent.`)
      setHistory({}); setReload(value => value + 1)
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }
  async function add(event) {
    event.preventDefault()
    if (busy) return
    setBusy('manual'); setError(''); setNotice('')
    try {
      const result = await call('/requests', { method: 'POST', body: manual })
      setManual({ email: '', name: '', company: '' }); setStatus(result.request.status); setCursor('')
      setReload(value => value + 1); setNotice('Request saved. Review it below before approving. No invitation was sent.')
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }
  async function showHistory(row) {
    try {
      const result = await call(`/requests/${row.id}/events`)
      setHistory(current => ({ ...current, [row.id]: result.events }))
    } catch (err) { setError(err.message) }
  }
  return <main className="cc-access-page"><div className="cc-access-wrap cc-access-owner">
    <CookCreditBrand /><p className="cc-access-eyebrow">Owner / Hiring access</p><h1>You choose who comes in.</h1>
    {!allowed ? <p role="alert">Only the verified owner account can manage hiring access. For help, contact connectwithus@cookcredit.com.</p> : <>
      <OwnerPricing call={call} />
      <p className="cc-access-intro">Website and email requests wait here for your decision. Approvals give people access to set up their own workspace; they do not join yours.</p>
      <p className="cc-access-note">Inbox import: {page.inbox.enabled ? 'enabled' : 'not connected yet'}. Hiring-related requests from your connected inboxes wait for your review. Public contact: connectwithus@cookcredit.com. Message bodies and attachments are not stored.</p>
      {page.inbox.enabled && (page.inbox.mailboxes || []).map(mailbox => <p key={mailbox.address} className="cc-access-note">{mailbox.address} · last checked {date(mailbox.checkedAt)}{mailbox.error && <span className="cc-access-error"> · {mailbox.error}</span>}</p>)}
      <details className="cc-access-card"><summary>Add someone who contacted you</summary><form className="cc-access-form" onSubmit={add}>
        <label>Email<input type="email" required maxLength={254} value={manual.email} onChange={e => setManual({ ...manual, email: e.target.value })} /></label>
        <label>Name (optional)<input maxLength={120} value={manual.name} onChange={e => setManual({ ...manual, name: e.target.value })} /></label>
        <label>Company (optional)<input maxLength={160} value={manual.company} onChange={e => setManual({ ...manual, company: e.target.value })} /></label>
        <button disabled={!!busy} className="cc-access-secondary">Save pending request</button>
      </form></details>
      <div className="cc-access-toolbar"><label>Show <select value={status} onChange={e => { setStatus(e.target.value); setCursor(''); setHistory({}) }}>{STATUS.map(value => <option key={value} value={value}>{value}</option>)}</select></label><button onClick={() => setReload(value => value + 1)} disabled={loading || !!busy}>Refresh</button></div>
      {notice && <p role="status" className="cc-access-notice">{notice}</p>}{error && <p role="alert" className="cc-access-error">{error}</p>}
      {loading ? <p role="status">Loading requests…</p> : <div className="cc-access-requests">
        {!page.requests.length && !error && <p>No {status === 'all' ? '' : status} requests on this page.</p>}
        {page.requests.map(row => <article className="cc-access-card" key={row.id}>
          <div className="cc-access-request-head"><div><h2>{row.company || row.name || row.email}</h2><p>{row.name}{row.name ? ' · ' : ''}{row.email}</p></div><span className="cc-access-pill">{row.status}</span></div>
          <p className="cc-access-note">From {row.source} · {date(row.createdAt)} · Invitation email: {row.invitationEmail.replaceAll('_', ' ')}</p>
          {row.message && <p className="cc-access-message">{row.message}</p>}
          <div className="cc-access-actions">
            {row.status !== 'approved' ? <>
              <button disabled={!!busy} className="cc-access-primary" onClick={() => decide(row, 'approve', true)}>Approve &amp; email invitation</button>
              <button disabled={!!busy} onClick={() => decide(row, 'approve')}>Approve without email</button>
              {row.status === 'pending' && <button disabled={!!busy} onClick={() => decide(row, 'decline')}>Decline</button>}
            </> : <>
              <button disabled={!!busy} className="cc-access-primary" onClick={() => decide(row, 'resend')}>Send invitation email</button>
              <button disabled={!!busy} onClick={() => decide(row, 'revoke')}>Revoke access</button>
            </>}
            <button disabled={!!busy} onClick={() => showHistory(row)}>View history</button>
          </div>
          {history[row.id] && <ul className="cc-access-history">{history[row.id].map((event, i) => <li key={i}>{event.action} · {date(event.createdAt)}</li>)}</ul>}
        </article>)}
      </div>}
      <div className="cc-access-actions">{cursor && <button onClick={() => setCursor('')} disabled={loading}>First page</button>}{page.nextCursor && <button onClick={() => setCursor(page.nextCursor)} disabled={loading}>Next page</button>}</div>
      <p className="cc-access-note">Revoking access blocks this email’s hiring API access. It does not delete their account, company, recordings, or other team members. Applicants can apply through an employer’s role link without employer-access approval.</p>
      <Link to="/business/roles">Return to your workspace</Link>
    </>}
  </div></main>
}
