import { useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import AuthShell from '../components/AuthShell'
import { authDestination, rememberDestination, rememberAccountDestination } from '../utils/homeFor'
import { profileFailure } from '../utils/profileFailure'
import { fadeUp, fadeIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

// Map a Firebase auth error code to copy the user can act on — a rate-limited user should not be
// told "wrong password" and keep hammering a correct one.
function loginErrorFor(code) {
  switch (code) {
    case 'auth/too-many-requests': return 'Too many attempts — wait a moment and try again'
    case 'auth/network-request-failed': return 'Network error — check your connection'
    case 'auth/user-disabled': return 'This account has been disabled'
    default: return 'Incorrect email or password'
  }
}

export default function LoginScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useLang()
  const { login } = useAuth()
  const [email, setEmail] = useState(location.state?.email || '')
  const [pass, setPass]   = useState('')
  const [err, setErr]     = useState('')
  const [busy, setBusy]   = useState(false)

  const iStyle = {
    width: '100%', padding: '14px 16px',
    border: '1px solid #e5e5e5', background: 'white',
    fontSize: 15, color: '#1a1a1a',
  }

  async function handleLogin() {
    if (busy) return
    if (!email || !pass) { setErr('Please enter your email and password'); return }
    setBusy(true); setErr('')
    try {
      if (location.state?.from) rememberDestination(location.state.from)
      const result = await login(email, pass)
      const dest = authDestination(result.profile, location.state?.from, result.uid)
      rememberAccountDestination(result.uid, dest)
      if (result?.needsVerification) { navigate('/verify', { state: { from: dest }, replace: true }); return }
      navigate(dest, { replace: true })
    } catch (e) {
      setErr(e?.status ? profileFailure(e).message : loginErrorFor(e?.code))
    } finally { setBusy(false) }
  }

  return (
    <AuthShell>
      {/* Header */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ background: '#1A1A1A', padding: '52px 24px 32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img src="/cookcredit-mark-orange.svg" alt="" width="32" height="26" />
          </div>
          <span style={{ color: 'white', fontFamily: SERIF, fontSize: 25, fontWeight: 500, letterSpacing: 0 }}>CookCredit</span>
        </div>
        <h1 style={{ fontFamily: SERIF, color: 'white', fontSize: 32, fontWeight: 300, letterSpacing: 0.5, margin: 0 }}>
          {t.welcome_back || 'Welcome back'}
        </h1>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14, marginTop: 8, fontWeight: 300, letterSpacing: 0.5 }}>
          Sign in to your CookCredit account.
        </p>
      </motion.div>

      {/* Form */}
      <motion.div variants={staggerContainer(0.07, 0.12)} initial="hidden" animate="show" style={{ padding: '36px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <motion.div variants={fadeUp}>
          <div style={{ fontSize: 11, color: '#999', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
            {t.email || 'Email'}
          </div>
          <input style={iStyle} placeholder="you@email.com" type="email" aria-label="Email" autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} />
        </motion.div>
        <motion.div variants={fadeUp}>
          <div style={{ fontSize: 11, color: '#999', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
            {t.password || 'Password'}
          </div>
          <input style={iStyle} type="password" placeholder="••••••••" aria-label="Password" autoComplete="current-password"
            value={pass} onChange={e => setPass(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()} />
        </motion.div>

        <motion.button type="button" variants={fadeUp} whileTap={tapScale} onClick={() => navigate('/forgot', { state: { from: location.state?.from } })}
          style={{ border: 0, background: 'none', textAlign: 'right', color: '#1a1a1a', fontSize: 13, cursor: 'pointer', borderBottom: '1px solid #e5e5e5', display: 'inline-block', alignSelf: 'flex-end', paddingBottom: 2 }}>
          {t.forgot_password || 'Forgot password?'}
        </motion.button>

        <AnimatePresence>
          {err && (
            <motion.div key="login-err" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} role="alert" style={{ color: '#c53030', fontSize: 13 }}>
              {err}
            </motion.div>
          )}
        </AnimatePresence>

        <motion.button variants={fadeUp} onClick={handleLogin} disabled={busy} {...buttonPress} style={{
          background: busy ? '#e5e5e5' : '#1a1a1a', color: busy ? '#999' : 'white',
          border: 'none', padding: '16px', fontSize: 15, fontWeight: 500,
          cursor: busy ? 'default' : 'pointer', letterSpacing: 0.5,
        }}>
          {busy ? '...' : (t.sign_in || 'Sign In')}
        </motion.button>

        <motion.div variants={fadeUp} style={{ textAlign: 'center', fontSize: 13, color: '#999' }}>
          {t.no_account || "Don't have an account?"}{' '}
          <motion.span whileTap={tapScale} onClick={() => navigate('/signup', { state: { from: location.state?.from } })}
            style={{ color: '#1a1a1a', cursor: 'pointer', fontWeight: 500, borderBottom: '1px solid #1a1a1a', paddingBottom: 1, display: 'inline-block' }}>
            {t.sign_up || 'Sign up'}
          </motion.span>
        </motion.div>
      </motion.div>
    </AuthShell>
  )
}
