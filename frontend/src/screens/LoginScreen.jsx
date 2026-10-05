import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import AuthShell from '../components/AuthShell'
import GoogleSignInButton from '../components/GoogleSignInButton'
import { authDestination, rememberDestination, rememberAccountDestination, authEntryDestination, authEntryLink } from '../utils/homeFor'
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
  const destination = authEntryDestination(location)
  const { t } = useLang()
  const { login, authActionPending } = useAuth()
  const [email, setEmail] = useState(location.state?.email || '')
  const [pass, setPass]   = useState('')
  const [err, setErr]     = useState('')
  const [busy, setBusy]   = useState(false)

  const iStyle = {
    width: '100%', padding: '14px 16px',
    border: '1px solid var(--cc-border)', background: 'white',
    fontSize: 15, color: 'var(--cc-ink)',
  }

  async function handleLogin() {
    if (busy || authActionPending) return
    if (!email || !pass) { setErr('Please enter your email and password'); return }
    setBusy(true); setErr('')
    try {
      if (destination) {
        rememberDestination(destination)
        navigate(location.pathname + location.search, { replace: true, state: { ...location.state, from: destination } })
      }
      const result = await login(email, pass)
      const dest = authDestination(result.profile, destination, result.uid)
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
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="cc-auth-heading" style={{ padding: '28px 24px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img src="/cookcredit-mark-orange.svg" alt="" width="32" height="26" />
          </div>
          <span style={{ color: 'white', fontFamily: SERIF, fontSize: 25, fontWeight: 500, letterSpacing: 0 }}>CookCredit</span>
        </div>
        <h1 style={{ fontFamily: SERIF, color: 'white', fontSize: 32, fontWeight: 300, letterSpacing: 0.5, margin: 0 }}>
          {t.welcome_back || 'Welcome back'}
        </h1>
        <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 14, marginTop: 8, fontWeight: 300, letterSpacing: 0.5 }}>
          {destination?.startsWith('/business/') ? 'Sign in to your hiring workspace.' : destination ? 'Sign in to continue your application or assessment.' : 'Sign in to hire cooks or continue your application.'}
        </p>
      </motion.div>

      {/* Form */}
      <motion.div variants={staggerContainer(0.07, 0.12)} initial="hidden" animate="show" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {(!destination || ['/applications', '/business/roles', '/business/onboarding'].includes(destination)) &&
          <nav aria-label="Choose your sign-in destination" style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 14 }}>
            <Link to="/login?next=/business/roles" aria-current={destination?.startsWith('/business/') ? 'page' : undefined} style={{ color: 'var(--cc-forest)', fontWeight: 600 }}>Hiring manager sign-in</Link>
            <Link to="/login?next=/applications" aria-current={destination === '/applications' ? 'page' : undefined} style={{ color: 'var(--cc-forest)', fontWeight: 600 }}>Applicant sign-in</Link>
          </nav>}
        <GoogleSignInButton destination={destination} disabled={busy || authActionPending} />
        <p style={{ textAlign: 'center', color: '#777', fontSize: 13 }}>or sign in with email</p>
        <motion.div variants={fadeUp}>
          <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
            {t.email || 'Email'}
          </div>
          <input style={iStyle} placeholder="you@email.com" type="email" aria-label="Email" autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} />
        </motion.div>
        <motion.div variants={fadeUp}>
          <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
            {t.password || 'Password'}
          </div>
          <input style={iStyle} type="password" placeholder="••••••••" aria-label="Password" autoComplete="current-password"
            value={pass} onChange={e => setPass(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()} />
        </motion.div>

        <motion.button type="button" variants={fadeUp} whileTap={tapScale} onClick={() => navigate('/forgot', { state: { from: destination } })}
          style={{ border: 0, background: 'none', textAlign: 'right', color: 'var(--cc-ink)', fontSize: 13, cursor: 'pointer', borderBottom: '1px solid var(--cc-border)', display: 'inline-block', alignSelf: 'flex-end', paddingBottom: 2 }}>
          {t.forgot_password || 'Forgot password?'}
        </motion.button>

        <AnimatePresence>
          {err && (
            <motion.div key="login-err" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} role="alert" style={{ color: '#c53030', fontSize: 13 }}>
              {err}
            </motion.div>
          )}
        </AnimatePresence>

        <motion.button variants={fadeUp} onClick={handleLogin} disabled={busy || authActionPending} {...buttonPress} style={{
          background: busy ? 'var(--cc-border)' : 'var(--cc-forest)', color: busy ? '#999' : 'white',
          border: 'none', padding: '16px', fontSize: 15, fontWeight: 500,
          cursor: busy ? 'default' : 'pointer', letterSpacing: 0.5,
        }}>
          {busy ? '...' : (t.sign_in || 'Sign In')}
        </motion.button>

        <motion.div variants={fadeUp} style={{ textAlign: 'center', fontSize: 13, color: '#999' }}>
          {t.no_account || "Don't have an account?"}{' '}
          <motion.button type="button" whileTap={tapScale} onClick={() => navigate(authEntryLink('/signup', destination))}
            style={{ background: 'none', border: 0, font: 'inherit', padding: 0, color: 'var(--cc-ink)', cursor: 'pointer', fontWeight: 500, borderBottom: '1px solid var(--cc-ink)', paddingBottom: 1, display: 'inline-block' }}>
            {t.sign_up || 'Sign up'}
          </motion.button>
        </motion.div>
      </motion.div>
    </AuthShell>
  )
}
