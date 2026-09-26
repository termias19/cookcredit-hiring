import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AccountShell from '../components/AccountShell'
import { useAuth } from '../context/AuthContext'
import { listMyHiringApplications } from '../utils/Api'

export default function ApplicantHomeScreen() {
  const { user } = useAuth()
  const [rows, setRows] = useState([])
  const [cursor, setCursor] = useState(null)
  const [nextCursor, setNextCursor] = useState(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    async function load() {
      setBusy(true); setError('')
      try {
        const result = await listMyHiringApplications({ token: await user.getIdToken(), cursor })
        if (!active) return
        setRows(previous => cursor ? [...new Map([...previous, ...result.applications].map(row => [row.id, row])).values()] : result.applications)
        setNextCursor(result.page.nextCursor)
      } catch (e) { if (active) setError(e.message || 'Applications could not be loaded.') }
      finally { if (active) setBusy(false) }
    }
    load()
    return () => { active = false }
  }, [user, cursor, reload])
  return <AccountShell title="My applications" intro="Resume an assessment and review the evidence you have shared with an employer.">
    {error && <div role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>Retry</button></div>}
    {!busy && !error && !rows.length && <section style={{ border: '1px solid var(--cc-border)', padding: 26 }}>
      <h2 className="cc-profile-heading">Start with your employer’s link</h2>
      <p style={{ color: 'var(--cc-muted)', fontSize: 14, lineHeight: 1.7 }}>After you submit an application through a company’s CookCredit invitation, it appears here. Practicing the standalone assessment does not apply for a job.</p>
      <Link to="/assessment" className="cc-profile-link" style={{ marginTop: 20 }}>About the knife assessment</Link>
    </section>}
    <div style={{ display: 'grid', gap: 14 }}>
      {rows.map(row => <article key={row.id} style={{ padding: 24, border: '1px solid var(--cc-border)' }}>
        <p style={{ fontSize: 13, color: 'var(--cc-muted)' }}>{row.company.name}</p>
        <h2 className="cc-profile-heading" style={{ margin: '8px 0' }}><Link to={`/application/${row.id}`} style={{ color: 'inherit' }}>{row.role.title}</Link></h2>
        <p style={{ fontSize: 13, color: '#1F6F5C' }}>{row.status.replaceAll('_', ' ')} · Submitted {new Date(row.submittedAt).toLocaleDateString()}</p>
      </article>)}
    </div>
    {busy && <p role="status" style={{ padding: '20px 0' }}>Loading applications…</p>}
    {!busy && nextCursor && <button style={{ marginTop: 20, padding: '12px 20px' }} onClick={() => setCursor(nextCursor)}>Load more</button>}
  </AccountShell>
}
