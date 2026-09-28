import { useEffect, useState } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { applyActionCode, checkActionCode, verifyPasswordResetCode, confirmPasswordReset } from 'firebase/auth'
import { auth } from '../firebase'
import { useAuth } from '../context/AuthContext'
import AuthShell from '../components/AuthShell'
import { verifyAccountLink, sameAccountEmail } from '../utils/verifyAccountLink'
import { authDestination } from '../utils/homeFor'

export default function AccountActionScreen() {
  const [params] = useSearchParams()
  const code = params.get('oobCode') || ''
  const mode = params.get('mode')
  const { completeVerification, logout } = useAuth()
  const navigate = useNavigate()
  const [verifiedEmail, setVerifiedEmail] = useState('')
  const [destination, setDestination] = useState(null)
  const [state, setState] = useState('checking')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    // Verification requires an explicit click below, so email scanners cannot consume a code.
    if (!code || !['verifyEmail', 'resetPassword'].includes(mode)) { setState('invalid'); return }
    if (mode === 'verifyEmail') { setState('verify'); return }
    verifyPasswordResetCode(auth, code).then(() => { if (live) setState('reset') }).catch(() => { if (live) setState('invalid') })
    return () => { live = false }
  }, [code, mode])
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    if (state === 'reset' && (password.length < 12 || password !== confirm)) { setError('Use at least 12 characters and enter the same password twice.'); return }
    setBusy(true); setError('')
    try {
      if (state === 'verify') {
        const result = await verifyAccountLink({ auth, code, checkCode: checkActionCode, applyCode: applyActionCode, complete: completeVerification })
        setVerifiedEmail(result.email)
        const next = result.profile ? authDestination(result.profile) : null
        setDestination(next)
        if (next) { window.history.replaceState(null, '', '/account/action'); navigate(next, { replace: true }); return }
      } else await confirmPasswordReset(auth, code, password)
      setState('done')
      // Remove the one-time code from the address bar after it is consumed.
      window.history.replaceState(null, '', '/account/action')
    } catch (e) { setError(e.code === 'auth/weak-password' ? 'Choose a stronger password.' : 'This link could not be used. Request a new link and try again.') }
    finally { setBusy(false) }
  }
  return <AuthShell><header style={{ background: '#1a1a1a', color: '#fff', padding: '40px 24px' }}><p style={{ fontFamily: 'var(--cc-display)', fontSize: 27, marginBottom: 24 }}>CookCredit</p><h1 style={{ fontFamily: 'var(--cc-display)', fontSize: 32, fontWeight: 400 }}>{mode === 'resetPassword' ? 'Reset your password' : 'Verify your email'}</h1></header>
    <div style={{ padding: '32px 24px', lineHeight: 1.7 }}>
      {state === 'checking' && <p role="status">Checking your link…</p>}
      {state === 'invalid' && <><p role="alert">This link is missing, expired, or has already been used.</p><Link style={linkStyle} to="/forgot">Request a password reset</Link><p><Link style={linkStyle} to="/login">Sign in to resend a verification email</Link></p></>}
      {state === 'done' && <><p role="status">{mode === 'resetPassword' ? 'Your password has been changed. Sign in with your new password.' : `Email verified: ${verifiedEmail}.`}</p>
        {mode === 'verifyEmail' && auth.currentUser && !sameAccountEmail(auth.currentUser, verifiedEmail) && <p>You are currently signed in as {auth.currentUser.email}. Switch accounts to continue with the email you just verified.</p>}
        <button style={{ ...linkStyle, background: 'none', border: 0, padding: '14px 0', cursor: 'pointer' }} onClick={async () => {
          if (mode === 'verifyEmail' && sameAccountEmail(auth.currentUser, verifiedEmail)) navigate(destination || '/verify', { replace: true })
          else { if (auth.currentUser) await logout(); navigate('/login', { replace: true, state: { email: verifiedEmail } }) }
        }}>{destination ? 'Continue to your account' : 'Sign in to continue'}</button></>}
      {['verify', 'reset'].includes(state) && <form onSubmit={submit} style={{ display: 'grid', gap: 20 }}>
        {state === 'verify' ? <p>Confirm that this is your email address to finish creating your CookCredit account.</p> : <><label>New password<input style={field} type="password" autoComplete="new-password" required minLength={12} value={password} onChange={e => setPassword(e.target.value)} /></label><label>Confirm new password<input style={field} type="password" autoComplete="new-password" required minLength={12} value={confirm} onChange={e => setConfirm(e.target.value)} /></label><p style={{ fontSize: 13 }}>Use at least 12 characters. A longer, unique passphrase works well.</p></>}
        {error && <p role="alert" style={{ color: '#a52b2b' }}>{error}</p>}
        <button disabled={busy} style={{ padding: 16, background: '#1F6F5C', border: 0, color: '#fff', fontSize: 15 }}>{busy ? 'Please wait…' : state === 'verify' ? 'Verify my email' : 'Save new password'}</button>
      </form>}
    </div></AuthShell>
}
const field = { display: 'block', width: '100%', marginTop: 8, padding: '14px 16px', background: '#fff', border: '1px solid #e3e0d9', fontSize: 15 }
const linkStyle = { color: '#1F6F5C', textUnderlineOffset: 3 }
