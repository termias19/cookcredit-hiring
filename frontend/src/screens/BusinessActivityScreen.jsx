import { useEffect, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { getBusinessActivity } from '../utils/Api'

const button = { padding: '10px 16px', border: '1px solid var(--cc-forest)', background: 'var(--cc-surface)', color: 'var(--cc-forest)', cursor: 'pointer', fontSize: 14 }
const titles = {
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
  useEffect(() => {
    if (org?.seatRole !== 'admin') return
    let active = true
    setBusy(true); setError(''); setEvents([]); setCursor(null)
    getToken().then(token => getBusinessActivity({ token })).then(result => {
      if (active) { setEvents(result.events); setCursor(result.nextCursor) }
    }).catch(e => { if (active) setError(e.message || 'Activity could not be loaded') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [getToken, org?.id, org?.seatRole, reload])
  async function more() {
    setBusy(true); setError('')
    try {
      const result = await getBusinessActivity({ token: await getToken(), before: cursor })
      setEvents(current => [...current, ...result.events]); setCursor(result.nextCursor)
    } catch (e) { setError(e.message || 'Activity could not be loaded') }
    finally { setBusy(false) }
  }
  if (org?.seatRole !== 'admin') return <p style={{ padding: 28 }}>Only workspace admins can view this activity.</p>
  return <section style={{ padding: 28, maxWidth: 1000 }}>
    <h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 30 }}>Workspace activity</h2>
    <p style={{ margin: '12px 0', lineHeight: 1.6 }}>Team, company and role changes recorded from this feature’s release onward. Older application and assessment records remain with those applications. This view does not yet include every security or billing event.</p>
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
