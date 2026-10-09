import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import CookCreditBrand from '../components/CookCreditBrand'
import { getAppCheckHeaders } from '../firebase'
import http from '../utils/http'
import '../styles/access.css'

export default function HiringAccessRequestScreen() {
  const { user, profile, refreshProfile } = useAuth()
  const [form, setForm] = useState({ name: profile?.name || user?.displayName || '', email: user?.email || '', company: '', message: '', website: '', contactConsent: false })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const change = event => setForm(current => ({ ...current, [event.target.name]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }))
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      await http('/api/access/requests', { method: 'POST', body: form, headers: await getAppCheckHeaders(), throwOnError: true })
      setDone(true)
    } catch (err) { setError(err.message || 'Your request could not be sent. Please try again.') }
    finally { setBusy(false) }
  }
  return <main className="cc-access-page"><div className="cc-access-wrap">
    <CookCreditBrand />
    <p className="cc-access-eyebrow">CookCredit / Hiring access</p>
    <h1>{user ? "Set up your hiring workspace" : "Let’s meet your kitchen."}</h1>
    {user && <p className="cc-access-intro">You’re signed in as {user.email}. Each company gets its own roles, applicants and team. CookCredit approval is required before you can create that workspace.</p>}
    {done ? <section className="cc-access-card" role="status">
      <h2>Thank you for your request.</h2>
      <p>The CookCredit owner will review it. If access is approved, we’ll email the next steps. {user ? 'Your account is ready. Approval unlocks your own company workspace.' : 'Submitting a request does not create an account or grant access.'}</p>
      <Link to="/">Return to CookCredit hiring</Link>
    </section> : <>
      <p className="cc-access-intro">Tell us who you are and how you’d like to use CookCredit. Your request goes to the CookCredit owner for approval.</p>
      <form className="cc-access-card cc-access-form" onSubmit={submit}>
        <label>Your name<input name="name" required maxLength={120} autoComplete="name" value={form.name} onChange={change} /></label>
        <label>Email for your account<input name="email" type="email" required maxLength={254} autoComplete="email" value={form.email} onChange={change} /></label>
        <label>Company or organisation<input name="company" required maxLength={160} autoComplete="organization" value={form.company} onChange={change} /></label>
        <label>What would you like to try? <span>(optional)</span><textarea name="message" maxLength={1500} rows={4} value={form.message} onChange={change} /></label>
        <div className="cc-access-trap" aria-hidden="true"><label>Website<input name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={change} /></label></div>
        <label className="cc-access-check"><input type="checkbox" name="contactConsent" required checked={form.contactConsent} onChange={change} /><span>CookCredit may contact me about this access request. <a href="https://cookcredit.com/privacy.html" target="_blank" rel="noreferrer">Privacy policy</a></span></label>
        {error && <p className="cc-access-error" role="alert">{error}</p>}
        <button className="cc-access-primary" disabled={busy}>{busy ? 'Sending…' : 'Request hiring access'}</button>
      </form>
      <p className="cc-access-note">Prefer email? Write to <a href="mailto:connectwithus@cookcredit.com?subject=CookCredit%20hiring%20access">connectwithus@cookcredit.com</a> with “hiring access” in the subject.</p>
      <p className="cc-access-note" hidden={!!user}>Already approved? <Link to="/signup?next=/business/onboarding">Create your account</Link> or <Link to="/login?next=/business/roles">sign in</Link>.</p>
    </>}
    <p className="cc-access-note">Employer access is reviewed by CookCredit. Your team makes every hiring decision. No payment is required to request access.</p>
    {user && <button className="cc-access-primary" disabled={busy} onClick={async () => {
      setBusy(true); setStatus('')
      try {
        const result = await refreshProfile()
        setStatus(!result ? 'Could not check your access. Please try again.' : result.employerAccessAllowed ? 'Approved. Open your workspace to continue.' : 'Employer access is not approved yet. Submit the request above if you have not already done so.')
      } finally { setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check approval status'}</button>}
    {status && <p role="status" className="cc-access-note">{status}</p>}
  </div></main>
}
