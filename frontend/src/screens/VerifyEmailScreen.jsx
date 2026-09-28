import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { auth } from '../firebase'
import { useAuth } from '../context/AuthContext'
import { authDestination, pendingDest, safeAuthDestination, rememberDestination } from '../utils/homeFor'
import AuthShell from '../components/AuthShell'
import { Mail, ArrowRight } from 'lucide-react'
import { fadeUp, fadeIn, scaleIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const RESEND_COOLDOWN = 60

export default function VerifyEmailScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, requestVerificationEmail, completeVerification, logout, verificationNotice } = useAuth()
  const [checking, setChecking] = useState(false)
  const [resending, setResending] = useState(false)
  const [err, setErr] = useState('')
  const [resent, setResent] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const checkingRef = useRef(false)
  const notice = verificationNotice?.uid === user?.uid ? verificationNotice : null

  useEffect(() => { if (cooldown <= 0) return; const id = setInterval(() => setCooldown(c => c - 1), 1000); return () => clearInterval(id) }, [cooldown])
  useEffect(() => {
    if (notice?.requestedAt && (notice.requested || notice.limited)) {
      setCooldown(Math.max(0, Math.ceil((notice.requestedAt + notice.retryAfterSeconds * 1000 - Date.now()) / 1000)))
    }
  }, [notice])

  // Returning from the inbox should continue the saved journey automatically.
  // Focus/visibility events avoid constant Firebase polling while people read mail.
  useEffect(() => {
    const onReturn = async () => {
      if (document.visibilityState === 'hidden' || checkingRef.current || !auth.currentUser) return
      checkingRef.current = true
      try {
        await auth.currentUser.reload()
        if (auth.currentUser?.emailVerified) {
          const resolved = await completeVerification()
          navigate(authDestination(resolved, location.state?.from), { replace: true })
        }
      } catch { /* Keep the explicit retry button available. */ }
      finally { checkingRef.current = false }
    }
    window.addEventListener('focus', onReturn)
    document.addEventListener('visibilitychange', onReturn)
    return () => { window.removeEventListener('focus', onReturn); document.removeEventListener('visibilitychange', onReturn) }
  }, [completeVerification, navigate, location.state?.from])

  async function handleResend() {
    if (cooldown > 0 || resending || !auth.currentUser) return
    setResending(true); setErr('')
    try {
      await auth.currentUser.reload()
      if (auth.currentUser.emailVerified) { await handleContinue(); return }
      const result = await requestVerificationEmail()
      if (result?.alreadyVerified) { await handleContinue(); return }
      setResent(true); setCooldown(result?.retryAfterSeconds || RESEND_COOLDOWN)
    } catch (error) {
      setErr(error?.status === 429 ? 'Please wait before requesting another email. Check your inbox and spam folder for the earlier message.' : 'We could not request your verification email. Please try again; you do not need to create another account.')
      if (error?.status === 429) setCooldown(error.retryAfterSeconds || RESEND_COOLDOWN)
    } finally { setResending(false) }
  }

  async function handleContinue() {
    if (checkingRef.current || !auth.currentUser) return
    checkingRef.current = true
    setChecking(true); setErr('')
    try {
      await auth.currentUser.reload()
      if (!auth.currentUser.emailVerified) { setErr('Email not verified yet. Check your inbox and click the link.'); return }
      const resolvedProfile = await completeVerification()
      navigate(authDestination(resolvedProfile, location.state?.from), { replace: true })
    } catch (error) { setErr(error.message || 'We could not check verification. Please try again.') } finally { checkingRef.current = false; setChecking(false) }
  }

  const email = user?.email || auth.currentUser?.email || 'your inbox'

  return (
    <AuthShell>
        <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ background: '#1A1A1A', padding: '52px 24px 32px', textAlign: 'center' }}>
          <img src="/cookcredit-mark-orange.svg" alt="CookCredit" width="48" height="37" style={{ display: 'block', margin: '0 auto 20px' }} />
          <motion.div variants={scaleIn} style={{ width: 56, height: 56, border: '1px solid rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
            <Mail size={24} color="white" strokeWidth={1.5} />
          </motion.div>
          <div style={{ fontFamily: SERIF, color: 'white', fontSize: 26, fontWeight: 300, marginBottom: 8 }}>Check your inbox</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14, lineHeight: 1.5 }}>Confirm your CookCredit email address</div>
          <div style={{ color: 'white', fontSize: 15, fontWeight: 500, marginTop: 4, wordBreak: 'break-all' }}>{email}</div>
        </motion.div>

        <motion.div variants={staggerContainer(0.07, 0.15)} initial="hidden" animate="show" style={{ padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
          <motion.div variants={fadeUp} style={{ border: '1px solid #e5e5e5', padding: '16px 18px', fontSize: 14, color: '#777', lineHeight: 1.6 }}>
            {notice?.requested === false
              ? notice.limited ? 'Please wait before requesting another email. Check your inbox and spam folder for the earlier message.' : 'We could not request your verification email. Use the button below to try again; your account has already been created.'
              : notice?.requested ? 'Your verification email has been requested. Delivery can take a few minutes. Check your inbox and spam folder, open the CookCredit link, then return here.'
                : 'Open the verification email from CookCredit, then return here. If it has not arrived, request a new email below.'}
          </motion.div>

          <AnimatePresence mode="wait">
            {err && (
              <motion.div key="verify-err" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} style={{ border: '1px solid rgba(197,48,48,0.3)', padding: '12px 16px', color: '#c53030', fontSize: 13, lineHeight: 1.5 }}>{err}</motion.div>
            )}
            {resent && !err && (
              <motion.div key="verify-resent" variants={scaleIn} initial="hidden" animate="show" exit={{ opacity: 0 }} style={{ border: '1px solid rgba(45,106,79,0.3)', padding: '12px 16px', color: '#1F6F5C', fontSize: 13 }}>Verification email requested. Please check your inbox shortly.</motion.div>
            )}
          </AnimatePresence>

          <motion.button variants={fadeUp} onClick={handleContinue} disabled={checking} {...buttonPress} style={{ background: checking ? '#e5e5e5' : '#1a1a1a', color: checking ? '#999' : 'white', border: 'none', padding: 16, fontSize: 16, fontWeight: 500, cursor: checking ? 'default' : 'pointer', marginTop: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            {checking ? 'Checking\u2026' : "I've verified, continue"} {!checking && <ArrowRight size={16} strokeWidth={1.5} />}
          </motion.button>

          <motion.button variants={fadeUp} onClick={handleResend} disabled={cooldown > 0 || resending} whileHover={cooldown > 0 ? undefined : { scale: 1.02 }} whileTap={cooldown > 0 ? undefined : tapScale} style={{ background: 'transparent', color: cooldown > 0 ? '#999' : '#1a1a1a', border: `1px solid ${cooldown > 0 ? '#e5e5e5' : '#1a1a1a'}`, padding: 14, fontSize: 15, fontWeight: 500, cursor: cooldown > 0 ? 'default' : 'pointer' }}>
            {resending ? 'Sending\u2026' : cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend email'}
          </motion.button>

          <motion.div variants={fadeUp} style={{ textAlign: 'center', marginTop: 8 }}>
            <motion.span whileTap={tapScale} onClick={async () => {
              const from = safeAuthDestination(location.state?.from) || pendingDest()
              await logout()
              rememberDestination(from)
              navigate('/login', { state: { from } })
            }} style={{ fontSize: 13, color: '#999', cursor: 'pointer', borderBottom: '1px solid #e5e5e5', paddingBottom: 2, display: 'inline-block' }}>Use a different account</motion.span>
          </motion.div>
        </motion.div>
    </AuthShell>
  )
}
