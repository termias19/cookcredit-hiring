import { useState } from 'react'

const money = row => new Intl.NumberFormat('en-US', { style: 'currency', currency: row.currency }).format(row.amount / 100)

export default function OwnerPricing({ call }) {
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function refresh() {
    const next = await call('/pricing')
    setData(next)
    return next
  }
  async function load(event) {
    if (!event.currentTarget.open || data || busy) return
    setBusy(true)
    try { await refresh() } catch (cause) { setError(cause.message) }
    finally { setBusy(false) }
  }
  function edit(row) {
    const current = data.prices.find(price => price.active && price.plan === row.plan && price.interval === row.interval)
    setForm({ plan: row.plan, interval: row.interval, amount: (row.amount / 100).toFixed(2),
      limits: { ...row.limits }, previousId: current?.id || null })
    setError(''); setNotice('')
  }
  async function save(event) {
    event.preventDefault()
    if (busy) return
    if (!/^\d+(\.\d{1,2})?$/.test(form.amount)) { setError('Enter a USD amount with at most two decimal places.'); return }
    const [dollars, cents = ''] = form.amount.split('.')
    const amount = Number(dollars) * 100 + Number(cents.padEnd(2, '0'))
    setBusy(true); setError(''); setNotice('')
    try {
      await call('/pricing', { method: 'POST', body: { ...form, amount, currency: 'usd' } })
      await refresh(); setForm(null); setNotice('Draft saved. Review its price and limits before publishing.')
    } catch (cause) { setError(cause.message) }
    finally { setBusy(false) }
  }
  async function publish(row) {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await call(`/pricing/${row.id}/publish`, { method: 'POST' })
      await refresh(); setNotice('Price published for new subscriptions. Existing subscriptions keep their price and limits.')
    } catch (cause) { setError(cause.message) }
    finally { setBusy(false) }
  }
  return <details className="cc-access-card" onToggle={load}>
    <summary>Subscription prices and limits</summary>
    <p>Prices are in USD. Annual amounts cover the full year. Publishing a new version affects new subscriptions only.</p>
    {error && <p role="alert" className="cc-access-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Saving or loading pricing…</p>}
    {data && <>
      <p>{data.billingEnabled ? 'Paid checkout is enabled.' : 'Paid checkout is disabled. Saving or publishing prices does not enable charging.'} {!data.stripeConfigured && 'Connect Stripe securely before publishing. Drafts can be saved now.'}</p>
      <div className="cc-access-actions">{data.recommendations.map(row => <button key={row.plan + row.interval} disabled={busy} onClick={() => edit(data.prices.find(p => p.active && p.plan === row.plan && p.interval === row.interval) || row)}>Set {row.plan} / {row.interval}</button>)}</div>
      {form && <form className="cc-access-form" onSubmit={save}>
        <h3>{form.plan} / {form.interval}</h3>
        <label>Price (USD per {form.interval})<input required inputMode="decimal" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
        {Object.entries({ seats: 'Total seats, including pending invitations', openRoles: 'Open roles', monthlyRequests: 'API assessment requests per calendar month' }).map(([key, label]) => <label key={key}>{label}<input type="number" required min="1" max={key === 'monthlyRequests' ? 100000 : 1000} step="1" value={form.limits[key]} onChange={e => setForm({ ...form, limits: { ...form.limits, [key]: Number(e.target.value) } })} /></label>)}
        <p>API limits apply only to plans with API access. Manual applications do not consume this allowance. No automatic overage charges.</p>
        <button disabled={busy}>Save draft</button><button type="button" disabled={busy} onClick={() => setForm(null)}>Cancel</button>
      </form>}
      {data.prices.map(row => <article className="cc-access-card" key={row.id}>
        <h3>{row.plan} — {money(row)} / {row.interval}</h3>
        <p>{row.limits.seats} seats · {row.limits.openRoles} open roles{row.plan === 'integration' ? ` · ${row.limits.monthlyRequests} API requests/month` : ''} · {row.active ? 'Current price' : row.state === 'draft' ? 'Draft' : 'Previous price'}</p>
        <button disabled={busy} onClick={() => edit(row)}>Create revised draft</button>
        {row.state === 'draft' && <button disabled={busy || !data.stripeConfigured} onClick={() => publish(row)}>Publish {money(row)} / {row.interval}</button>}
      </article>)}
    </>}
  </details>
}
