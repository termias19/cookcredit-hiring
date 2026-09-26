/**
 * Helper payouts (route /payouts, helper-only) — Stripe Connect bank connection.
 * Real: connection state from /api/auth/me (stripeConnected) + Stripe Connect
 * onboarding (onboardCook -> hosted onboarding_url). Balances/history are NOT
 * shown yet (no bookings backend) — surfaced honestly rather than faked.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Landmark, Check } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { onboardCook } from '../utils/Api'
import { fadeUp, scaleIn, staggerContainer } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

function Header({ onBack }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#FEFDFB',
      borderBottom: '1px solid #eee', padding: '14px 16px' }}>
      <button onClick={onBack} aria-label="Back" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
        border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer' }}>
        <ArrowLeft size={18} strokeWidth={1.5} color="#1a1a1a" />
      </button>
      <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>Payouts</span>
    </div>
  )
}

export default function CookPayoutsScreen() {
  const navigate = useNavigate()
  const { user, profile } = useAuth()
  const [connecting, setConnecting] = useState(false)
  const [connected] = useState(!!profile?.stripeConnected)
  const [err, setErr] = useState('')

  async function connect() {
    setConnecting(true); setErr('')
    try {
      // Stripe Connect onboarding returns a hosted URL (key: onboarding_url) to redirect to.
      const res = await onboardCook({ auth: { currentUser: user } })
      const target = res?.onboarding_url || res?.url
      if (target) { window.location.href = target; return }
      setErr('Could not start bank connection. Please try again.')
    } catch {
      setErr('Could not start bank connection. Please try again.')
    } finally {
      setConnecting(false)
    }
  }

  return (
    <Shell header={<Header onBack={() => navigate('/dashboard')} />} showNav={false}>
      <motion.div variants={staggerContainer(0.08)} initial="hidden" animate="show">
        {/* bank connection */}
        <div style={{ padding: '20px 20px 0' }}>
          <AnimatePresence mode="wait" initial={false}>
            {connected ? (
              <motion.div key="connected" variants={fadeUp} initial="hidden" animate="show" exit={{ opacity: 0 }}
                style={{ border: '1px solid #1F6F5C', background: '#E8F1EC', padding: '14px 16px',
                display: 'flex', alignItems: 'center', gap: 12 }}>
                <motion.div variants={scaleIn} style={{ display: 'flex' }}>
                  <Check size={20} color="#1F6F5C" strokeWidth={2} />
                </motion.div>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>Bank connected</p>
                  <p style={{ fontSize: 12, color: '#1F6F5C', margin: 0 }}>You're set up to get paid. Earnings will appear here once you start getting booked.</p>
                </div>
              </motion.div>
            ) : (
              <motion.div key="not-connected" variants={fadeUp} initial="hidden" animate="show" exit={{ opacity: 0 }}
                style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                  <Landmark size={22} color="#555" strokeWidth={1.5} />
                  <p style={{ fontSize: 13, lineHeight: 1.5, color: '#555', margin: 0 }}>
                    Connect your bank with Stripe to receive payouts. Clients are charged at booking;
                    your earnings land after each job.
                  </p>
                </div>
                {err && <p style={{ fontSize: 12, color: '#D32F2F', margin: '0 0 10px' }}>{err}</p>}
                <motion.button onClick={connect} disabled={connecting} whileHover={connecting ? {} : { scale: 1.02 }}
                  whileTap={connecting ? {} : { scale: 0.97 }} style={{
                  width: '100%', padding: '14px', background: connecting ? '#ccc' : '#1a1a1a', color: '#fff',
                  border: 'none', cursor: connecting ? 'default' : 'pointer',
                  fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>
                  {connecting ? 'Connecting…' : 'Connect bank with Stripe'}
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* history — empty until bookings exist (no fabricated earnings) */}
        <motion.div variants={fadeUp} style={{ padding: '22px 20px 24px' }}>
          <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 12px' }}>Payout history</p>
          <div style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '24px 16px', textAlign: 'center' }}>
            <div style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a', marginBottom: 4 }}>No payouts yet</div>
            <p style={{ fontSize: 13, color: '#999', margin: 0 }}>Your completed jobs and payouts will show up here.</p>
          </div>
        </motion.div>
      </motion.div>
    </Shell>
  )
}
