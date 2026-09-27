import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AccountShell from '../components/AccountShell'
import http from '../utils/http'

export default function EmailUnsubscribeScreen() {
  const [params] = useSearchParams(), [message, setMessage] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function unsubscribe() {
    setBusy(true); setError('')
    try { const result = await http('/api/customer-mail/unsubscribe', { method: 'POST', body: { token: params.get('token') }, throwOnError: true }); setMessage(result.message) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <AccountShell title="Unsubscribe from Hiring offers" intro="Your account, applications and payment emails will stay active.">
    {message ? <p role="status">{message}</p> : <button disabled={busy || !params.get('token')} onClick={unsubscribe}>Unsubscribe from offers</button>}
    {error && <p role="alert">{error}</p>}
  </AccountShell>
}
