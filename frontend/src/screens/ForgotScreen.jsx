import { useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import { ArrowLeft, Mail } from 'lucide-react'
import AuthShell from '../components/AuthShell'
import { fadeUp, fadeIn, scaleIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

export default function ForgotScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useLang()
  const { resetPassword } = useAuth()
  const [email, setEmail] = useState('')
  const [sent, setSent]   = useState(false)
  const [busy, setBusy]   = useState(false)
  const [err, setErr]     = useState('')

  const iStyle = {
    width: '100%', padding: '14px 16px',
    border: '1px solid var(--cc-border)', background: 'white',
    fontSize: 15, color: 'var(--cc-ink)',
  }

  async function handleReset() {
    if (!email) return
    setBusy(true); setErr('')
    try {
      await resetPassword(email)
      setSent(true)
    } catch {
      setErr('Could not request a reset email. Please try again shortly.')
    } finally { setBusy(false) }
  }

  if (sent) return (
    <AuthShell>
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="cc-auth-heading" style={{ padding: '52px 24px 32px' }}>
          <img src="/cookcredit-mark-orange.svg" alt="CookCredit" width="48" height="37" style={{ display: 'block', margin: '0 auto 20px' }} />
          <h1 style={{ fontFamily: SERIF, color: 'white', fontSize: 28, fontWeight: 300, letterSpacing: 0.5, margin: 0 }}>
            {t.forgot_sent_title || 'Check your email'}
          </h1>
        </motion.div>
        <motion.div variants={staggerContainer(0.08, 0.1)} initial="hidden" animate="show"
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 24px', textAlign: 'center' }}>
          <motion.div variants={scaleIn} style={{ width: 56, height: 56, border: '1px solid var(--cc-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
            <Mail size={24} color="#555" strokeWidth={1.5} />
          </motion.div>
          <motion.p variants={fadeUp} style={{ fontSize: 15, color: '#777', lineHeight: 1.7, marginBottom: 8 }}>
            If a CookCredit account exists for this address, a reset link from CookCredit will arrive shortly.
          </motion.p>
          <motion.p variants={fadeUp} style={{ fontSize: 15, color: 'var(--cc-ink)', fontWeight: 500, marginBottom: 36 }}>{email}</motion.p>
          <motion.button variants={fadeUp} onClick={() => navigate('/login', { state: { from: location.state?.from } })} {...buttonPress} style={{
            background: '#1F6F5C', color: 'white', border: 'none',
            padding: '16px 40px', fontSize: 15, fontWeight: 500,
            cursor: 'pointer', letterSpacing: 0.5,
          }}>
            {t.forgot_back || 'Back to sign in'}
          </motion.button>
        </motion.div>
    </AuthShell>
  )

  return (
    <AuthShell>
        {/* Header */}
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="cc-auth-heading" style={{ padding: '52px 24px 32px' }}>
          <img src="/cookcredit-mark-orange.svg" alt="CookCredit" width="48" height="37" style={{ display: 'block', margin: '0 auto 20px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
            <button aria-label="Back to sign in" onClick={() => navigate('/login', { state: { from: location.state?.from } })} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <ArrowLeft size={20} color="rgba(255,255,255,0.7)" strokeWidth={1.5} />
            </button>
          </div>
          <h1 style={{ fontFamily: SERIF, color: 'white', fontSize: 28, fontWeight: 300, letterSpacing: 0.5, margin: 0 }}>
            {t.forgot_title || 'Reset password'}
          </h1>
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14, marginTop: 8, fontWeight: 300, letterSpacing: 0.5 }}>
            {t.forgot_subtitle || "We'll send you a reset link"}
          </p>
        </motion.div>

        {/* Form */}
        <motion.div variants={staggerContainer(0.07, 0.12)} initial="hidden" animate="show" style={{ padding: '36px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <motion.div variants={fadeUp}>
            <div style={{ fontSize: 11, color: '#999', marginBottom: 8, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 2 }}>
              {t.email || 'Email'}
            </div>
            <input style={iStyle} placeholder="you@email.com" type="email" aria-label="Email" autoComplete="email"
              value={email} onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleReset()} />
          </motion.div>

          <AnimatePresence>
            {err && (
              <motion.div key="forgot-err" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} role="alert" style={{ color: '#c53030', fontSize: 13 }}>
                {err}
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button variants={fadeUp} onClick={handleReset} disabled={!email || busy}
            whileHover={email && !busy ? { scale: 1.02 } : undefined} whileTap={email && !busy ? tapScale : undefined}
            style={{
              background: email && !busy ? 'var(--cc-forest)' : 'var(--cc-border)',
              color: email && !busy ? 'white' : '#999',
              border: 'none', padding: '16px', fontSize: 15, fontWeight: 500,
              cursor: email && !busy ? 'pointer' : 'default', letterSpacing: 0.5,
            }}>
            {busy ? '...' : (t.forgot_btn || 'Send reset link')}
          </motion.button>
        </motion.div>
    </AuthShell>
  )
}
