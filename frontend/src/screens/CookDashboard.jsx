/**
 * Helper dashboard — the helper's home (route /dashboard, role=cook).
 *
 * Real data from /api/auth/me (profile.cookProfile + stripeConnected): the
 * identity-verified badge (tier + score, with an unverified path into /skill),
 * application-review state, a Stripe-connect earnings card, and quick actions.
 * Bookings/earnings amounts are intentionally NOT shown yet (no marketplace
 * source) — surfaced honestly rather than faked.
 */
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, animate } from 'framer-motion'
import { ShieldCheck, ShieldAlert, Award, UserCog, Share2, Landmark, Eye, Clock } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { EASE, fadeUp, scaleIn, staggerContainer, buttonPress, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const TIER_COLOR = { gold: '#C9A227', silver: '#9AA3AD', bronze: '#B08D57' }

/** Brief count-up on mount for a prominent number (e.g. the verification score). */
function CountUpNumber({ value, style }) {
  const ref = useRef(null)
  useEffect(() => {
    const node = ref.current
    if (!node || value == null) return
    const controls = animate(0, value, {
      duration: 0.6, ease: EASE,
      onUpdate: v => { node.textContent = Math.round(v) },
    })
    return () => controls.stop()
  }, [value])
  return <span ref={ref} style={style}>0</span>
}

function Header({ name }) {
  const hour = new Date().getHours()
  const part = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 24px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>
          Good {part}{name ? `, ${name}` : ''}
        </h1>
      </div>
    </div>
  )
}

function VerifiedBadge({ tier, score, onView }) {
  const tc = TIER_COLOR[tier] || '#777'
  return (
    <motion.button
      onClick={onView}
      initial="hidden" animate="show" variants={scaleIn}
      whileHover={hoverLift} whileTap={tapScale}
      style={{
        display: 'flex', alignItems: 'center', gap: 14, width: '100%', textAlign: 'left', cursor: 'pointer',
        border: `1px solid ${tc}`, background: '#fff', padding: '16px' }}>
      <ShieldCheck size={32} color={tc} strokeWidth={1.5} style={{ flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 11, letterSpacing: 1, color: tc, textTransform: 'uppercase', fontWeight: 600, margin: '0 0 2px' }}>
          {tier ? `${tier} verified` : 'verified'}
        </p>
        <p style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>Identity verified</p>
        <p style={{ fontSize: 12, color: '#777', margin: 0 }}>Clients see this badge on your profile.</p>
      </div>
      {score != null && (
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontFamily: SERIF, fontSize: 30, color: tc, lineHeight: 1 }}>
            <CountUpNumber value={score} />
          </div>
          <div style={{ fontSize: 9, color: '#aaa', letterSpacing: 1, textTransform: 'uppercase' }}>/ 100</div>
        </div>
      )}
    </motion.button>
  )
}

function UnverifiedBadge({ onTakeTest }) {
  return (
    <motion.div initial="hidden" animate="show" variants={scaleIn}
      style={{ border: '1px solid #C4561F', background: '#fff', padding: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
        <ShieldAlert size={32} color="#C4561F" strokeWidth={1.5} style={{ flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 11, letterSpacing: 1, color: '#C4561F', textTransform: 'uppercase', fontWeight: 600, margin: '0 0 2px' }}>
            Not yet verified
          </p>
          <p style={{ fontSize: 13, lineHeight: 1.5, color: '#555', margin: 0 }}>
            Complete identity verification to earn a tier badge and start appearing in client searches.
          </p>
        </div>
      </div>
      <motion.button onClick={onTakeTest} {...buttonPress} style={{
        width: '100%', padding: '14px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
        fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Award size={16} strokeWidth={1.5} /> Complete verification
      </motion.button>
    </motion.div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ padding: '28px 0 0' }}>
      <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 14px' }}>{title}</p>
      {children}
    </div>
  )
}

function QuickAction({ icon, label, onClick }) {
  return (
    <motion.button onClick={onClick} variants={fadeUp} whileHover={hoverLift} whileTap={tapScale} style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, cursor: 'pointer',
      border: '1px solid #e5e5e5', background: '#fff', padding: '28px 16px', minHeight: 128 }}>
      {icon}
      <span style={{ fontSize: 12, letterSpacing: 0.5, color: '#555', textAlign: 'center', lineHeight: 1.3 }}>{label}</span>
    </motion.button>
  )
}

export default function CookDashboard() {
  const navigate = useNavigate()
  const { profile } = useAuth()
  const cp = profile?.cookProfile || {}
  const name = (profile?.name || '').split(' ')[0]
  const verified = !!cp.skillVerified
  const appStatus = cp.applicationStatus           // none | pending | approved | rejected
  const stripeConnected = !!profile?.stripeConnected
  const canShowPublic = verified && appStatus === 'approved'

  return (
    <Shell wide header={<Header name={name} />}>
      <div style={{ padding: '28px 0 40px' }}>
        {/* application review state */}
        {appStatus === 'pending' && (
          <motion.div initial="hidden" animate="show" variants={fadeUp} style={{ marginBottom: 20 }}>
            <div style={{ border: '1px solid #C9A227', background: '#FBF3E2', padding: '14px 16px',
              display: 'flex', alignItems: 'center', gap: 12 }}>
              <Clock size={20} color="#B87800" strokeWidth={1.5} style={{ flexShrink: 0 }} />
              <p style={{ fontSize: 13, lineHeight: 1.5, color: '#7a5200', margin: 0 }}>
                Your helper application is under review. We’ll email you once it’s approved — then you’ll appear in client searches.
              </p>
            </div>
          </motion.div>
        )}

        {/* status row: verification + earnings side by side on wide screens */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20 }}>
          {verified
            ? <VerifiedBadge tier={cp.skillTier} score={cp.skillScore} onView={() => navigate('/skill')} />
            : <UnverifiedBadge onTakeTest={() => navigate('/skill')} />}

          <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ delay: 0.05 }}
            style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '16px', display: 'flex', flexDirection: 'column' }}>
            <p style={{ fontSize: 11, letterSpacing: 1, color: '#aaa', textTransform: 'uppercase', fontWeight: 600, margin: '0 0 8px' }}>Earnings</p>
            <p style={{ fontSize: 13, lineHeight: 1.55, color: '#777', margin: '0 0 14px', flex: 1 }}>
              {stripeConnected
                ? 'Your payout account is connected. Earnings will appear here once you start getting booked.'
                : 'Connect a bank account so you can get paid when bookings go live.'}
            </p>
            <motion.button onClick={() => navigate('/payouts')} {...buttonPress} style={{
              width: '100%', padding: '14px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
              fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <Landmark size={16} strokeWidth={1.5} /> {stripeConnected ? 'Manage payouts' : 'Connect bank to get paid'}
            </motion.button>
          </motion.div>
        </div>

        {/* quick actions */}
        <Section title="Quick actions">
          <motion.div initial="hidden" animate="show" variants={staggerContainer(0.06, 0.1)}
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <QuickAction icon={<Award size={26} color="#C9A227" strokeWidth={1.5} />}
              label={verified ? 'View verification' : 'Verify identity'} onClick={() => navigate('/skill')} />
            <QuickAction icon={<UserCog size={26} color="#1a1a1a" strokeWidth={1.5} />}
              label="Edit profile" onClick={() => navigate('/cook/profile/edit')} />
            {canShowPublic
              ? <QuickAction icon={<Eye size={26} color="#1F6F5C" strokeWidth={1.5} />}
                  label="View public profile" onClick={() => navigate(`/cook/${profile.id}`)} />
              : <QuickAction icon={<Share2 size={26} color="#1F6F5C" strokeWidth={1.5} />}
                  label="Share profile" onClick={() => navigate('/profile')} />}
          </motion.div>
        </Section>
      </div>
    </Shell>
  )
}
