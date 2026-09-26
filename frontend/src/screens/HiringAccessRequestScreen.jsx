import { useState } from 'react'
import { Link } from 'react-router-dom'
import CookCreditBrand from '../components/CookCreditBrand'
import { getAppCheckHeaders } from '../firebase'
import http from '../utils/http'
import '../styles/access.css'

export default function HiringAccessRequestScreen() {
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '', website: '', contactConsent: false })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
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
    <h1>Let’s meet your kitchen.</h1>
    {done ? <section className="cc-access-card" role="status">
      <h2>Thank you for your request.</h2>
      <p>The CookCredit owner will review it. If access is approved, we’ll email the next steps. Submitting a request does not create an account or grant access.</p>
      <a href="https://cookcredit.com/hiring/">Return to CookCredit hiring</a>
    </section> : <>
      <p className="cc-access-intro">Tell us who you are and how you’d like to use CookCredit. Every request is reviewed before access is granted.</p>
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
      <p className="cc-access-note">Already approved? <Link to="/signup?next=/business/onboarding">Create your account</Link> or <Link to="/login" state={{ from: '/business/onboarding' }}>sign in</Link>.</p>
    </>}
    <p className="cc-access-note">Employer access is reviewed by CookCredit. Your team makes every hiring decision. No subscription payment is required.</p>
  </div></main>
}
