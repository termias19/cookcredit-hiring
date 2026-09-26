/**
 * Helper profile — the client's decision page (shareable public URL /cook/:id).
 *
 * Hero photo + name + identity-verified tier, the ID-verification trust block (the
 * differentiator), bio, service specialties, highlighted work, and a sticky rate +
 * "Request booking" CTA. Loads from GET /api/cooks/:id (public, biometric-safe).
 * Rating/reviews are deferred (no marketplace source yet) — we show a calm
 * "new helper" state rather than fake stars.
 */
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Star, ShieldCheck, MapPin, Clock, CalendarCheck, X, ChevronRight } from 'lucide-react'
import Shell from '../components/Shell'
import { money } from '../utils/money'
import { getCook } from '../utils/Api'
import { MARKETPLACE_ENABLED } from '../config'
import { fadeUp, fadeIn, scaleIn, staggerContainer, buttonPress, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const TIER_COLOR = { gold: '#C9A227', silver: '#9AA3AD', bronze: '#B08D57' }
const TIER_BENEFIT = {
  gold: 'Top-tier verified identity — thorough, careful, reliable.',
  silver: 'Strong, verified identity — steady and dependable.',
  bronze: 'Verified identity fundamentals — safe, reliable service.',
}

function Stars({ n, size = 13 }) {
  return (
    <span style={{ display: 'inline-flex', gap: 1 }}>
      {[1, 2, 3, 4, 5].map(i => (
        <Star key={i} size={size} strokeWidth={1.5}
          color="#C9A227" fill={i <= Math.round(n) ? '#C9A227' : 'none'} />
      ))}
    </span>
  )
}

function Header({ onBack }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '14px 32px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={onBack} aria-label="Back" style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
          border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer' }}>
          <ArrowLeft size={18} strokeWidth={1.5} color="#1a1a1a" />
        </button>
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>
          Helper profile
        </span>
      </div>
    </div>
  )
}

function Section({ title, children, delay = 0, first = false }) {
  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay }} style={{ padding: first ? 0 : '24px 0 0' }}>
      <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 12px' }}>
        {title}
      </p>
      {children}
    </motion.div>
  )
}

export default function CookProfileScreen() {
  const { cookId } = useParams()
  const navigate = useNavigate()
  // Result keyed by the cookId it belongs to: while the effect for a new cookId is
  // in flight, status derives to 'loading' at render time (no sync setState in effect).
  const [res, setRes] = useState({ id: null, cook: null, status: 'loading' })
  const [showSkillInfo, setShowSkillInfo] = useState(false)

  useEffect(() => {
    let live = true
    getCook(cookId)
      .then(d => {
        if (!live) return
        if (d && d.id && !d.error) setRes({ id: cookId, cook: d, status: 'ready' })
        else setRes({ id: cookId, cook: null, status: 'notfound' })
      })
      .catch(() => { if (live) setRes({ id: cookId, cook: null, status: 'notfound' }) })
    return () => { live = false }
  }, [cookId])

  const status = res.id === cookId ? res.status : 'loading'
  const cook = res.id === cookId ? res.cook : null

  if (status !== 'ready' || !cook) {
    return (
      <Shell wide header={<Header onBack={() => navigate(-1)} />} showNav={false}>
        <div style={{ padding: '64px 24px', textAlign: 'center', color: '#999', fontSize: 14 }}>
          {status === 'loading' ? 'Loading…' : 'This helper profile isn’t available.'}
        </div>
      </Shell>
    )
  }

  const tier = cook.skillTier
  const tc = TIER_COLOR[tier] || '#777'
  const benefit = TIER_BENEFIT[tier] || 'Verified identity — safe, reliable service.'
  const photo = cook.photoUrl
  const city = [cook.baseCity, cook.baseState].filter(Boolean).join(', ')
  const years = cook.yearsExperience
  const tags = [...(cook.cuisines || []), ...(cook.specialties || [])]
  const dishes = (cook.dishes || []).filter(Boolean)
  const hasRating = cook.rating != null && (cook.reviewCount || 0) > 0
  const score = cook.skillScore

  return (
    <Shell wide header={<Header onBack={() => navigate(-1)} />} showNav={false}>
      <motion.div variants={staggerContainer(0.05, 0.04)} initial="hidden" animate="show"
        style={{ padding: '28px 0 40px', display: 'flex', gap: 28, alignItems: 'flex-start', flexWrap: 'wrap' }}>

        {/* LEFT — sticky profile card: photo, identity, verification, price + booking CTA */}
        <motion.div variants={fadeUp} style={{
          flex: '1 1 320px', maxWidth: 380, position: 'sticky', top: 28,
          border: '1px solid #e5e5e5', background: '#fff', overflow: 'hidden' }}>

          <motion.div role="img" aria-label={cook.name} variants={fadeIn} style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: photo ? `#eee url(${photo}) center/cover` : '#EDE7DF' }}>
            {!photo && <span style={{ fontFamily: SERIF, fontSize: 72, color: '#9a8c7a' }}>{(cook.name || '?').trim().charAt(0).toUpperCase()}</span>}
          </motion.div>

          <div style={{ padding: '20px 20px 22px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
              <h1 style={{ fontFamily: SERIF, fontSize: 26, fontWeight: 400, color: '#1a1a1a', margin: 0 }}>{cook.name}</h1>
              {cook.skillVerified && <ShieldCheck size={18} color={tc} strokeWidth={2} />}
            </div>
            <p style={{ fontSize: 11, letterSpacing: 1, color: tc, textTransform: 'uppercase', fontWeight: 600, margin: '0 0 10px' }}>
              {tier ? `${tier} verified` : 'Helper'}{years ? ` · ${years} yrs experience` : ''}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13, color: '#555', flexWrap: 'wrap' }}>
              {hasRating && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Stars n={cook.rating} /> {cook.rating} <span style={{ color: '#aaa' }}>({cook.reviewCount})</span>
                </span>
              )}
              {city && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#999' }}>
                  <MapPin size={14} strokeWidth={1.5} /> {city}
                </span>
              )}
            </div>

            {/* skill-verification trust block — the differentiator (tappable explainer) */}
            {cook.skillVerified && (
              <motion.button type="button" onClick={() => setShowSkillInfo(true)}
                variants={scaleIn} transition={{ delay: 0.1 }}
                whileHover={hoverLift} whileTap={tapScale}
                aria-haspopup="dialog" aria-label="How identity verification works"
                style={{ width: '100%', marginTop: 16, border: `1px solid ${tc}`, background: '#fff',
                  padding: '14px 16px', cursor: 'pointer', textAlign: 'left',
                  display: 'flex', alignItems: 'center', gap: 14 }}>
                <ShieldCheck size={28} color={tc} strokeWidth={1.5} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>Identity verified</p>
                  <p style={{ fontSize: 11, color: '#777', margin: '0 0 4px' }}>
                    Passed Mise's ID and background check{tier ? ` (${tier} tier)` : ''}.
                  </p>
                  <p style={{ fontSize: 11, color: tc, fontWeight: 600, margin: 0,
                    display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                    {benefit} <ChevronRight size={12} strokeWidth={2} />
                  </p>
                </div>
                {score != null && (
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontFamily: SERIF, fontSize: 22, color: tc, lineHeight: 1 }}>{score}</div>
                    <div style={{ fontSize: 9, color: '#aaa', letterSpacing: 1, textTransform: 'uppercase' }}>/ 100</div>
                  </div>
                )}
              </motion.button>
            )}

            {/* price + booking CTA */}
            <div style={{ borderTop: '1px solid #f0f0f0', marginTop: 18, paddingTop: 18 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
                <span style={{ fontFamily: SERIF, fontSize: 28, color: '#1a1a1a', lineHeight: 1 }}>
                  {cook.pricePerHour != null ? money(cook.pricePerHour) : '—'}
                </span>
                <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                  <Clock size={11} strokeWidth={1.5} /> per hour
                </span>
              </div>
              {MARKETPLACE_ENABLED ? (
                <motion.button onClick={() => navigate(`/book/${cookId}`)} {...buttonPress} style={{
                  width: '100%', boxSizing: 'border-box', padding: '14px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
                  fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <CalendarCheck size={16} strokeWidth={1.5} /> Request booking
                </motion.button>
              ) : (
                <div style={{ width: '100%', boxSizing: 'border-box', padding: '14px', background: '#f2efea', color: '#999', textAlign: 'center',
                  fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <Clock size={15} strokeWidth={1.5} /> Booking opens soon
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* RIGHT — bio, specialties, highlighted work, reviews */}
        <div style={{ flex: '2 1 420px', minWidth: 0 }}>
          {cook.bio && (
            <Section title="About" delay={0.08} first>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: '#333', margin: 0 }}>{cook.bio}</p>
            </Section>
          )}

          {tags.length > 0 && (
            <Section title="Specialties" delay={0.12} first={!cook.bio}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {tags.map((s, i) => (
                  <span key={i} style={{ padding: '6px 12px', fontSize: 12, color: '#555',
                    border: '1px solid #e5e5e5', background: '#fff', letterSpacing: 0.3 }}>{s}</span>
                ))}
              </div>
            </Section>
          )}

          {dishes.length > 0 && (
            <Section title="Highlighted work" delay={0.16} first={!cook.bio && tags.length === 0}>
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                {dishes.map((d, i) => (
                  d.photoUrl
                    ? <div key={i} title={d.name} style={{ width: 140, height: 100, flexShrink: 0, background: `#eee url(${d.photoUrl}) center/cover` }} />
                    : <div key={i} style={{ width: 140, height: 100, flexShrink: 0, background: '#f4f1ec', border: '1px solid #e5e5e5',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 8,
                        fontSize: 13, color: '#555' }}>{d.name}</div>
                ))}
              </div>
            </Section>
          )}

          {/* reviews — real once the marketplace ships; until then, a calm verified-only state */}
          <Section title="Reviews" delay={0.2} first={!cook.bio && tags.length === 0 && dishes.length === 0}>
            {hasRating ? (
              <p style={{ fontSize: 13, color: '#555', margin: 0 }}>{cook.rating} average across {cook.reviewCount} reviews.</p>
            ) : (
              <p style={{ fontSize: 13, color: '#999', lineHeight: 1.55, margin: 0 }}>
                New on Mise — identity verified, no reviews yet.
              </p>
            )}
          </Section>
        </div>
      </motion.div>

      {/* skill-verification explainer sheet */}
      <AnimatePresence>
        {showSkillInfo && (
          <motion.div role="presentation" onClick={() => setShowSkillInfo(false)}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
            style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(26,26,26,0.45)',
              display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
            <motion.div role="dialog" aria-modal="true" aria-label="How identity verification works"
              onClick={e => e.stopPropagation()}
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 40 }} transition={{ duration: 0.28 }}
              style={{ width: 'min(430px,100vw)', background: '#FEFDFB', borderTop: `2px solid ${tc}`,
                padding: '22px 22px calc(22px + env(safe-area-inset-bottom, 0px))',
                maxHeight: '82vh', overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
                <ShieldCheck size={26} color={tc} strokeWidth={1.5} style={{ flexShrink: 0, marginTop: 2 }} />
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 4px' }}>Identity verification</p>
                  <h2 style={{ fontFamily: SERIF, fontSize: 24, fontWeight: 400, color: '#1a1a1a', margin: 0 }}>How identity verification works</h2>
                </div>
                <button type="button" onClick={() => setShowSkillInfo(false)} aria-label="Close"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 34, height: 34,
                    border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer', flexShrink: 0 }}>
                  <X size={17} strokeWidth={1.5} color="#1a1a1a" />
                </button>
              </div>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: '#333', margin: '0 0 16px' }}>
                Every Mise helper completes a short ID and liveness check. Our system verifies the real government ID and a live selfie scan — not a self-report — to confirm:
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0, marginBottom: 18 }}>
                {[
                  ['Government ID', 'A valid, unexpired photo ID matched to the helper.'],
                  ['Liveness check', 'A live selfie scan confirms the person is real and present — not a photo or recording.'],
                  ['Background check', 'A nationwide criminal background screening.'],
                ].map(([label, desc], i) => (
                  <div key={label} style={{ padding: '12px 0', borderTop: i ? '1px solid #f0f0f0' : 'none' }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>{label}</p>
                    <p style={{ fontSize: 13, lineHeight: 1.5, color: '#777', margin: 0 }}>{desc}</p>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 12, lineHeight: 1.6, color: '#999', margin: 0 }}>
                Verification is done by a third-party provider on the helper's actual government ID and background check, so the badge reflects a verified identity — not a claim.
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </Shell>
  )
}
