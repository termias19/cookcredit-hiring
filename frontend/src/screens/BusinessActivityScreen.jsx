import { useEffect, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { getBusinessActivity } from '../utils/Api'

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
    <button disabled={busy} onClick={() => setReload(value => value + 1)}>Refresh activity</button>
    {error && <p role="alert">{error}</p>}
    {!busy && !error && !events.length && <p>No workspace changes recorded yet.</p>}
    <ol style={{ listStyle: 'none', padding: 0 }}>
      {events.map(event => <li key={event.id} style={{ padding: '18px 0', borderBottom: '1px solid var(--cc-border)', overflowWrap: 'anywhere' }}>
        <strong>{event.action.replaceAll('.', ' ').replaceAll('_', ' ')}</strong>
        <p><time dateTime={event.createdAt}>{new Date(event.createdAt).toLocaleString()}</time></p>
        <p>By {event.actorName || event.actorId} · Target: {event.targetId}</p>
        <p>{Object.entries(event.detail || {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : String(value)}`).join(' · ')}</p>
      </li>)}
    </ol>
    {busy && <p role="status">Loading activity…</p>}
    {cursor && <button disabled={busy} onClick={more}>Load older activity</button>}
  </section>
}
