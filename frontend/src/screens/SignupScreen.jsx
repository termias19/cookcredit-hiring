import { useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import AuthShell from '../components/AuthShell'
import { rememberDestination, rememberAccountDestination, safeAuthDestination, pendingDest, signupDestination } from '../utils/homeFor'
import GoogleSignInButton from '../components/GoogleSignInButton'
import { fadeUp, fadeIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const BLUSH = 'var(--cc-surface-soft)'

// Applicants keep their invitation; employers activate a company workspace after verification.
const ROLE_OPTIONS = [
  { key: 'eat',  label: 'Hire cooks' },
  { key: 'cook', label: 'Apply for a role' },
]

export default function SignupScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useLang()
  const { signUp, authActionPending } = useAuth()
  const [name, setName]     = useState('')
  const [email, setEmail]   = useState('')
  const [pass, setPass]     = useState('')
  // Pre-select "Cook" when arriving from a "Become a cook" CTA (LandingScreen passes state.role).
  const requested = safeAuthDestination(location.state?.from) || safeAuthDestination(new URLSearchParams(location.search).get('next')) || pendingDest()
  const applicantInvitation = requested?.startsWith('/apply/') || requested?.startsWith('/application/') || requested?.startsWith('/application-assessment-return/')
  const [role, setRole] = useState(applicantInvitation || requested === '/applications' || requested === '/profile' || location.state?.role === 'cook' ? 'cook' : 'eat')
  const [err, setErr]       = useState('')
  const [busy, setBusy]     = useState(false)
  // Honeypot: a hidden field humans never see/fill; bots that auto-fill forms will populate it,
  // and the backend rejects any signup where it's non-empty.
  const [hp, setHp]         = useState('')

  const iStyle = {
    width: '100%', padding: '14px 16px',
    border: '1px solid var(--cc-border)', background: 'white',
    fontSize: 15, color: 'var(--cc-ink)',
  }

  async function handleCreate() {
    if (busy || authActionPending) return
    if (!name.trim() || !email.trim() || !pass) { setErr('Please fill in all fields'); return }
    if (pass.length < 12) { setErr('Password must be at least 12 characters'); return }
    setBusy(true); setErr('')
    try {
      const dest = rememberDestination(signupDestination(role, requested))
      navigate(location.pathname + location.search, { replace: true, state: { ...location.state, from: dest } })
      const account = await signUp(email.trim(), pass, {
        name: name.trim(),
        phone: '',
        roles: ['eater'],
        activeRole: dest.startsWith('/business') ? 'business' : 'eater',
        hp,
      })
      rememberAccountDestination(account.uid, dest)
      navigate('/verify', { state: { from: dest }, replace: true })
    } catch (e) {
      setErr(e.code === 'auth/email-already-in-use' ? 'Email already in use' : e.message)
    } finally { setBusy(false) }
  }

  return (
    <AuthShell>
        {/* Header */}
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="cc-auth-heading" style={{ padding: '28px 24px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <img src="/cookcredit-mark-orange.svg" alt="" width="32" height="26" />
              </div>
              <span style={{ color: 'white', fontFamily: SERIF, fontSize: 25, fontWeight: 500, letterSpacing: 0 }}>CookCredit</span>
            </div>
          </div>
          <h1 style={{ fontFamily: SERIF, color: 'white', fontSize: 32, fontWeight: 300, letterSpacing: 0.5, margin: 0 }}>
            {applicantInvitation ? 'Create your applicant account' : t.create_account || 'Create account'}
          </h1>
          <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 14, marginTop: 8, fontWeight: 300, letterSpacing: 0.5 }}>
            {applicantInvitation ? 'Verify your email, then continue your application.' : role === 'eat' ? 'Create your account, then request access to your own company workspace.' : 'Create your account to apply with an employer’s link.'}
          </p>
        </motion.div>

        {/* Form */}
        <motion.div variants={staggerContainer(0.06, 0.1)} initial="hidden" animate="show" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Honeypot — off-screen, not a real field. Bots that fill every input trip it; the
              backend rejects the signup. Hidden from users + assistive tech + tab order. */}
          <input type="text" name="company" value={hp} onChange={e => setHp(e.target.value)}
            tabIndex={-1} autoComplete="off" aria-hidden="true"
            style={{ position: 'absolute', left: '-9999px', top: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }} />

          {/* Role toggle */}
          {!applicantInvitation && <motion.div variants={fadeUp}>
            <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
              {t.i_want_to || 'I want to'}
            </div>
            <div style={{ display: 'flex', gap: 0 }}>
              {ROLE_OPTIONS.map(opt => {
                const active = role === opt.key
                return (
                  <motion.button key={opt.key} aria-pressed={active} disabled={busy || authActionPending || !!applicantInvitation} onClick={() => setRole(opt.key)}
                    whileHover={{ scale: active ? 1 : 1.02 }} whileTap={tapScale}
                    animate={{ scale: active ? [1, 1.06, 1] : 1 }}
                    transition={{ duration: 0.28 }}
                    style={{
                      flex: 1, padding: '14px 0', fontSize: 15, fontWeight: 500,
                      cursor: 'pointer', letterSpacing: 0.5,
                      border: active ? `2px solid ${BLUSH}` : '1px solid var(--cc-border)',
                      background: active ? BLUSH : 'white',
                      color: active ? 'var(--cc-forest)' : '#999',
                    }}>
                    {opt.label}
                  </motion.button>
                )
              })}
            </div>
            {/* Surfaces the moat to a serious applicant (and the value to a B2B-curious visitor). */}
            <AnimatePresence>
              {role === 'cook' && (
                <motion.p key="cook-note" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }}
                  style={{ fontSize: 12, color: '#777', lineHeight: 1.5, margin: '10px 0 0' }}>
                  Your employer’s assessment link takes you to the correct role. CookCredit shares your recorded knife assessment with your permission.
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>}

          <GoogleSignInButton destination={signupDestination(role, requested)} disabled={busy || authActionPending} />
          <p style={{ textAlign: 'center', color: '#777', fontSize: 13 }}>or create an account with email</p>
          {/* Name */}
          <motion.div variants={fadeUp}>
            <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
              {t.full_name || 'Full name'}
            </div>
            <input style={iStyle} placeholder="Your name" type="text" aria-label="Full name" autoComplete="name" maxLength={200}
              value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          </motion.div>

          {/* Email */}
          <motion.div variants={fadeUp}>
            <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
              {t.email || 'Email'}
            </div>
            <input style={iStyle} placeholder="you@email.com" type="email" aria-label="Email" autoComplete="email"
              value={email} onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          </motion.div>

          {/* Password */}
          <motion.div variants={fadeUp}>
            <div style={{ fontSize: 11, color: '#626262', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
              {t.password || 'Password'}
            </div>
            <input style={iStyle} placeholder="12+ characters" type="password" aria-label="Password" autoComplete="new-password" minLength={12}
              value={pass} onChange={e => setPass(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          </motion.div>


          <AnimatePresence>
            {err && (
              <motion.div key="signup-err" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} role="alert" style={{ color: '#c53030', fontSize: 13 }}>
                {err}
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button variants={fadeUp} onClick={handleCreate} disabled={busy || authActionPending} {...buttonPress} style={{
            marginTop: 8,
            background: busy ? 'var(--cc-border)' : 'var(--cc-forest)', color: busy ? '#999' : 'white',
            border: 'none', padding: '16px', fontSize: 15, fontWeight: 500,
            cursor: busy ? 'default' : 'pointer', letterSpacing: 0.5,
          }}>
            {busy ? '\u2026' : 'Create account'}
          </motion.button>

          <motion.div variants={fadeUp} style={{ textAlign: 'center', fontSize: 13, color: '#999' }}>
            {t.already_have || 'Already have an account?'}{' '}
          <motion.button type="button" whileTap={tapScale} onClick={() => navigate('/login', { state: { from: signupDestination(role, requested) } })}
              style={{ background: 'none', border: 0, font: 'inherit', padding: 0, color: 'var(--cc-ink)', cursor: 'pointer', fontWeight: 500, borderBottom: '1px solid var(--cc-ink)', paddingBottom: 1, display: 'inline-block' }}>
              {t.log_in || 'Log in'}
            </motion.button>
          </motion.div>
        </motion.div>
    </AuthShell>
  )
}
