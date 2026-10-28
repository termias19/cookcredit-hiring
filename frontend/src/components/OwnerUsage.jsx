import { useEffect, useState } from 'react'

const metrics = [['activeUsers', 'Active accounts'], ['signups', 'Signups'],
  ['applications', 'Applications started'], ['completedAssessments', 'Completed assessments']]
const date = value => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export default function OwnerUsage({ call }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function refresh() {
    setBusy(true); setError('')
    try { setData(await call('/usage')) }
    catch (cause) { setError(cause.message) }
    finally { setBusy(false) }
  }
  useEffect(() => {
    let live = true
    call('/usage').then(next => { if (live) setData(next) })
      .catch(cause => { if (live) setError(cause.message) })
    return () => { live = false }
  }, [call])
  return <section className="cc-access-card" aria-labelledby="owner-usage-title">
    <h2 id="owner-usage-title">Hiring usage</h2>
    <p>Four rolling seven-day periods, most recent first. Dates use your local time. Signups count accounts created in Hiring, not all CookCredit accounts.</p>
    <button disabled={busy || (!data && !error)} onClick={refresh}>Refresh usage</button>
    {error && <p role="alert" className="cc-access-error">Usage could not be loaded: {error}</p>}
    {(!data && !error) || busy ? <p role="status">Loading usage…</p> : null}
    {data && <>
      <p className="cc-access-note">Updated {date(data.generatedAt)}{error ? ' · Previous results shown.' : ''}</p>
      <p className="cc-access-note">{data.activityDefinition}</p>
      <p className="cc-access-note">{data.testClassification}</p>
      {data.weeks.map(week => <div key={week.start} className="cc-owner-usage-week">
        <h3>{date(week.start)} – {date(week.end)}</h3>
        <div className="cc-owner-usage-scroll" role="region" aria-label={`Usage from ${date(week.start)}`} tabIndex={0}>
          <table className="cc-owner-usage-table">
            <caption className="cc-access-note">Other accounts and known test activity</caption>
            <thead><tr><th scope="col">Metric</th><th scope="col">Other accounts</th><th scope="col">Owner / test accounts</th></tr></thead>
            <tbody>{metrics.map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{week.other[key]}</td><td>{week.test[key]}</td></tr>)}</tbody>
          </table>
        </div>
      </div>)}
    </>}
  </section>
}
