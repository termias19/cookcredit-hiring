import { useEffect, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { getBusinessActivity } from '../utils/Api'
import { saveHiringFile } from '../utils/saveHiringCv'

const button = { padding: '10px 16px', border: '1px solid var(--cc-forest)', background: 'var(--cc-surface)', color: 'var(--cc-forest)', cursor: 'pointer', fontSize: 14 }
const titles = {
  'api_key.created': 'API key created', 'api_key.revoked': 'API key revoked',
  'webhook.created': 'Webhook created', 'webhook.updated': 'Webhook status updated',
  'webhook.replay_requested': 'Webhook replay requested',
  'member.role_changed': 'Team role changed', 'member.removed': 'Team access removed',
  'invitation.created': 'Teammate invited', 'invitation.accepted': 'Invitation accepted',
  'invitation.revoked': 'Invitation revoked', 'company.updated': 'Company details updated',
  'company.logo_changed': 'Company logo changed', 'integrations.updated': 'Integration settings updated',
  'role.created': 'Role created', 'role.updated': 'Role details updated', 'role.status_changed': 'Role status changed',
}
const detailLabels = { previousRole: 'Previous team role', seatRole: 'Team role', previousStatus: 'Previous status', status: 'Status', fields: 'Changed fields', removed: 'Removed' }

/** Administrative records only. Applicant evidence keeps its existing audit records. */
export default function BusinessActivityScreen() {
  const { getToken, org } = useBusiness()
  const [events, setEvents] = useState([])
  const [cursor, setCursor] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [action, setAction] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    if (org?.seatRole !== 'admin') return
    let active = true
    setBusy(true); setError(''); setEvents([]); setCursor(null)
    getToken().then(token => getBusinessActivity({ token, action })).then(result => {
      if (active) { setEvents(result.events); setCursor(result.nextCursor) }
    }).catch(e => { if (active) setError(e.message || 'Activity could not be loaded') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [getToken, org?.id, org?.seatRole, reload, action])
  async function more() {
    setBusy(true); setError('')
    try {
      const result = await getBusinessActivity({ token: await getToken(), before: cursor, action })
      setEvents(current => [...current, ...result.events]); setCursor(result.nextCursor)
    } catch (e) { setError(e.message || 'Activity could not be loaded') }
    finally { setBusy(false) }
  }
  async function exportActivity() {
    setBusy(true); setError(''); setNotice('')
    try {
      // Re-authorize server-side instead of exporting a stale private browser cache.
      const result = await saveHiringFile(async () => {
        const page = await getBusinessActivity({ token: await getToken(), action })
        return new Blob([JSON.stringify({ exportedAt: new Date().toISOString(),
          scope: 'Latest 50 matching workspace events', filter: { action }, ...page }, null, 2)],
          { type: 'application/json' })
      }, { suggestedName: 'workspace-activity.json', types: [{ description: 'Activity JSON', accept: { 'application/json': ['.json'] } }] })
      setNotice(result === 'saved' ? 'Activity file saved.' : result === 'requested' ? 'Download requested. Check your browser downloads.' : 'Export cancelled.')
    } catch (e) { setError(e.message || 'Activity could not be exported') }
    finally { setBusy(false) }
  }
  if (org?.seatRole !== 'admin') return <p style={{ padding: 28 }}>Only workspace admins can view this activity.</p>
  return <section style={{ padding: 28, maxWidth: 1000 }}>
    <h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 30 }}>Workspace activity</h2>
    <p style={{ margin: '12px 0', lineHeight: 1.6 }}>Team, company, role and integration changes recorded from this feature’s release onward. Older application and assessment records remain with those applications. This view does not yet include every security or billing event.</p>
    <label style={{ display: 'block', marginBottom: 12 }}>Activity type{' '}
      <select style={button} value={action} disabled={busy} onChange={event => { setAction(event.target.value); setNotice('') }}>
        <option value="">All activity</option>
        {Object.entries(titles).map(([key, title]) => <option key={key} value={key}>{title}</option>)}
      </select>
    </label>
    <button style={button} disabled={busy} onClick={exportActivity}>Export latest 50 (JSON)</button>{' '}
    {notice && <p role="status">{notice}</p>}
    <button style={button} disabled={busy} onClick={() => setReload(value => value + 1)}>Refresh activity</button>
    {error && <p role="alert">{error}</p>}
    {!busy && !error && !events.length && <p>No workspace changes recorded yet.</p>}
    <ol style={{ listStyle: 'none', padding: 0 }}>
      {events.map(event => <li key={event.id} style={{ padding: '18px 0', borderBottom: '1px solid var(--cc-border)', overflowWrap: 'anywhere' }}>
        <strong>{titles[event.action] || event.action.replaceAll('.', ' ').replaceAll('_', ' ')}</strong>
        <p style={{ margin: '6px 0', color: 'var(--cc-muted)', fontSize: 13 }}><time dateTime={event.createdAt}>{new Date(event.createdAt).toLocaleString()}</time> · By {event.actorName || event.actorId}</p>
        <p>{Object.entries(event.detail || {}).map(([key, value]) => `${detailLabels[key] || key}: ${Array.isArray(value) ? value.join(', ') : String(value).replaceAll('_', ' ')}`).join(' · ')}</p>
        <details style={{ marginTop: 8, fontSize: 12, color: 'var(--cc-muted)' }}><summary>Record references</summary><p>Event: {event.id}<br />Actor: {event.actorId}<br />Target: {event.targetId}</p></details>
      </li>)}
    </ol>
    {busy && <p role="status">Loading activity…</p>}
    {cursor && <button style={button} disabled={busy} onClick={more}>Load older activity</button>}
  </section>
}
