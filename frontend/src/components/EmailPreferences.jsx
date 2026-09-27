import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import http from '../utils/http'

export default function EmailPreferences() {
  const { user } = useAuth()
  const [offers, setOffers] = useState(false), [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('')
  useEffect(() => {
    let active = true
    if (!user?.emailVerified) return undefined
    user.getIdToken().then(token => http('/api/customer-mail/preferences', { token, throwOnError: true }))
      .then(data => { if (active) { setOffers(data.offers); setLoaded(true) } })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [user])
  async function save() {
    setBusy(true); setError(''); setMessage('')
    try {
      await http('/api/customer-mail/preferences', { method: 'PUT', token: await user.getIdToken(), body: { offers }, throwOnError: true })
      setMessage('Email preference saved.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section style={{ border: '1px solid var(--cc-border)', padding: 24 }}>
    <h2 className="cc-profile-heading">Email preferences</h2>
    <p>Account verification, security and billing messages stay enabled.</p>
    <label style={{ display: 'block', margin: '18px 0' }}><input type="checkbox" disabled={!loaded || busy} checked={offers} onChange={e => setOffers(e.target.checked)} /> Send me CookCredit Hiring news and offers. I can unsubscribe at any time.</label>
    <button type="button" disabled={!loaded || busy} onClick={save}>Save email preference</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>
}
