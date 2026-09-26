/**
 * Booking — two modes, one route component:
 *   /book/:cookId          -> NEW request flow (the meat of this screen)
 *   /booking/:bookingId    -> existing-booking detail (light stub for now)
 *
 * The request flow is deliberately tap-first and single-scroll: pick a day
 * (chips), a start time (chips), a duration (stepper), confirm the address, add
 * an optional note, see the fee breakdown, send. No payment here — the client
 * pays only after the helper ACCEPTS (status requested -> accepted -> confirmed),
 * so the request stays a one-tap commitment.
 *
 * Mock helper summary + client-side request for now; wires to POST /api/bookings
 * later (fields already match the Booking model: scheduledDate,
 * scheduledStartTime, estimatedDuration, eaterAddress, pricePerHour,
 * estimatedTotal, eaterNotes).
 */
import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Minus, Plus, Calendar, Clock, MapPin, Check, ShieldCheck, CreditCard, Star, Lock, Play, Flag } from 'lucide-react'
import Shell from '../components/Shell'
import useIsDesktop from '../hooks/useIsDesktop'
import { useAuth } from '../context/AuthContext'
import { subtotalOf, eaterTotal, serviceFee, cookPayout, money } from '../utils/money'
import { fadeUp, scaleIn, staggerContainer, buttonPress, tapScale, EASE } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const TIER_COLOR = { gold: '#C9A227', silver: '#9AA3AD', bronze: '#B08D57' }

const MOCK_COOKS = {
  c1: { name: 'Amara Okafor',  tier: 'gold',   price: 45 },
  c2: { name: 'Diego Ramirez', tier: 'silver', price: 38 },
  c3: { name: 'Mei Lin',       tier: 'gold',   price: 52 },
}
const FALLBACK_COOK = { name: 'Mise Helper', tier: 'silver', price: 42 }

const TIME_SLOTS = ['11:00', '12:00', '13:00', '17:00', '18:00', '19:00', '20:00']
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Next 14 days as {key, weekday, day, month, label}. */
function nextDays(n = 14) {
  const out = []
  const base = new Date()
  for (let i = 0; i < n; i++) {
    const d = new Date(base)
    d.setDate(base.getDate() + i)
    out.push({
      key: d.toISOString().slice(0, 10),
      weekday: i === 0 ? 'Today' : WEEKDAY[d.getDay()],
      day: d.getDate(),
      month: MONTH[d.getMonth()],
    })
  }
  return out
}

function Header({ onBack, title }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#FEFDFB',
      borderBottom: '1px solid #eee', padding: '14px 16px' }}>
      <button onClick={onBack} aria-label="Back" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
        border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer' }}>
        <ArrowLeft size={18} strokeWidth={1.5} color="#1a1a1a" />
      </button>
      <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>{title}</span>
    </div>
  )
}

function Section({ icon: Icon, title, children }) {
  return (
    <motion.div variants={fadeUp} style={{ padding: '20px 20px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, margin: '0 0 12px' }}>
        {Icon && <Icon size={15} strokeWidth={1.5} color="#999" />}
        <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: 0 }}>{title}</p>
      </div>
      {children}
    </motion.div>
  )
}

const chip = (active) => ({
  flexShrink: 0, cursor: 'pointer', border: '1px solid',
  borderColor: active ? '#1a1a1a' : '#e5e5e5',
  background: active ? '#1a1a1a' : '#fff',
  color: active ? '#fff' : '#555',
})

// ── new-request flow ──────────────────────────────────────────────────────────
function NewBooking({ cookId }) {
  const navigate = useNavigate()
  const isDesktop = useIsDesktop()
  const sheetWidth = isDesktop ? 'min(560px,100vw)' : 'min(430px,100vw)'
  const cook = MOCK_COOKS[cookId] || FALLBACK_COOK
  const tc = TIER_COLOR[cook.tier] || '#777'
  const days = useMemo(() => nextDays(14), [])

  const [date, setDate] = useState(days[0].key)
  const [time, setTime] = useState('18:00')
  const [hours, setHours] = useState(3)
  const [address, setAddress] = useState('')
  const [notes, setNotes] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const subtotal = subtotalOf(cook.price, hours)
  const fee = serviceFee(subtotal)
  const total = eaterTotal(subtotal)
  const canSubmit = date && time && hours >= 2 && address.trim().length > 4

  if (submitted) {
    return (
      <Shell header={<Header onBack={() => navigate('/browse')} title="Request sent" />} showNav={false}>
        <motion.div variants={staggerContainer(0.08)} initial="hidden" animate="show"
          style={{ padding: '56px 28px', textAlign: 'center' }}>
          <motion.div variants={scaleIn} style={{ width: 64, height: 64, margin: '0 auto 20px', borderRadius: '50%',
            background: '#1F6F5C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Check size={32} color="#fff" strokeWidth={2.5} />
          </motion.div>
          <motion.h2 variants={fadeUp} style={{ fontFamily: SERIF, fontSize: 26, fontWeight: 400, color: '#1a1a1a', margin: '0 0 10px' }}>
            Request sent to {cook.name}
          </motion.h2>
          <motion.p variants={fadeUp} style={{ fontSize: 14, lineHeight: 1.6, color: '#666', margin: '0 0 28px' }}>
            They'll review and accept your request. You'll only be charged once they
            confirm — nothing has been paid yet.
          </motion.p>
          <motion.div variants={staggerContainer(0.05)} style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '16px 18px', textAlign: 'left', marginBottom: 24 }}>
            <Row label="When" value={(() => { const d = days.find(x => x.key === date); return d ? `${d.weekday} ${d.month} ${d.day}, ${time} · ${hours} hrs` : `${time} · ${hours} hrs` })()} />
            <Row label="Estimate" value={money(total)} />
          </motion.div>
          <motion.button variants={fadeUp} onClick={() => navigate('/bookings')} {...buttonPress} style={{
            width: '100%', padding: '14px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
            fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>
            View my bookings
          </motion.button>
        </motion.div>
      </Shell>
    )
  }

  return (
    <Shell header={<Header onBack={() => navigate(-1)} title="Request booking" />} showNav={false}>
      <motion.div variants={staggerContainer(0.07)} initial="hidden" animate="show">
        {/* helper mini-summary */}
        <motion.div variants={fadeUp} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px',
          borderBottom: '1px solid #f0f0f0' }}>
          <div style={{ width: 52, height: 52, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: cook.photo ? `#eee url(${cook.photo}) center/cover` : '#EDE7DF' }}>
            {!cook.photo && <span style={{ fontFamily: SERIF, fontSize: 20, color: '#9a8c7a' }}>{(cook.name || '?').trim().charAt(0).toUpperCase()}</span>}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: SERIF, fontSize: 20, color: '#1a1a1a' }}>{cook.name}</span>
              <ShieldCheck size={15} color={tc} strokeWidth={2} />
            </div>
            <span style={{ fontSize: 12, color: '#777' }}>{money(cook.price)}/hr · {cook.tier} verified</span>
          </div>
        </motion.div>

        {/* date */}
        <Section icon={Calendar} title="Pick a day">
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4, WebkitOverflowScrolling: 'touch' }}>
            {days.map(d => (
              <motion.button key={d.key} onClick={() => setDate(d.key)} whileTap={tapScale}
                style={{ ...chip(date === d.key), padding: '10px 12px', minWidth: 58, textAlign: 'center' }}>
                <div style={{ fontSize: 10, letterSpacing: 0.5, textTransform: 'uppercase', opacity: 0.8 }}>{d.weekday}</div>
                <div style={{ fontFamily: SERIF, fontSize: 20, lineHeight: 1.1 }}>{d.day}</div>
                <div style={{ fontSize: 9, opacity: 0.7 }}>{d.month}</div>
              </motion.button>
            ))}
          </div>
        </Section>

        {/* time */}
        <Section icon={Clock} title="Start time">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {TIME_SLOTS.map(t => (
              <motion.button key={t} onClick={() => setTime(t)} whileTap={tapScale}
                style={{ ...chip(time === t), padding: '8px 14px', fontSize: 13 }}>{t}</motion.button>
            ))}
          </div>
        </Section>

        {/* duration */}
        <Section title="How long">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <motion.button onClick={() => setHours(h => Math.max(2, h - 1))} aria-label="Less" whileTap={tapScale} style={stepBtn}>
              <Minus size={18} strokeWidth={2} color="#1a1a1a" />
            </motion.button>
            <div style={{ textAlign: 'center', minWidth: 80 }}>
              <motion.span key={hours} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: EASE }} style={{ display: 'inline-block', fontFamily: SERIF, fontSize: 30, color: '#1a1a1a' }}>{hours}</motion.span>
              <span style={{ fontSize: 13, color: '#777' }}> hours</span>
            </div>
            <motion.button onClick={() => setHours(h => Math.min(8, h + 1))} aria-label="More" whileTap={tapScale} style={stepBtn}>
              <Plus size={18} strokeWidth={2} color="#1a1a1a" />
            </motion.button>
          </div>
        </Section>

        {/* address */}
        <Section icon={MapPin} title="Where">
          <input value={address} onChange={e => setAddress(e.target.value)}
            placeholder="Street address, city"
            style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', background: '#fff',
              padding: '12px 14px', fontSize: 14, color: '#1a1a1a', outline: 'none' }} />
        </Section>

        {/* notes */}
        <Section title="Anything else? (optional)">
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
            placeholder="Gate codes, pets, parking, anything to know before they arrive…"
            style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', background: '#fff',
              padding: '12px 14px', fontSize: 14, color: '#1a1a1a', outline: 'none', resize: 'vertical',
              fontFamily: 'inherit' }} />
        </Section>

        {/* fee breakdown */}
        <Section title="Estimate">
          <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show"
            style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '4px 16px' }}>
            <Row label={`${money(cook.price)} × ${hours} hrs`} value={money(subtotal)} />
            <Row label="Service fee" value={money(fee)} />
            <Row label="Estimated total" value={money(total)} bold />
          </motion.div>
          <p style={{ fontSize: 11, color: '#aaa', margin: '8px 2px 0', lineHeight: 1.5 }}>
            Final total is based on actual time. You're charged only after the helper accepts.
          </p>
        </Section>
      </motion.div>

      <div style={{ height: 92 }} />

      {/* sticky CTA */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: EASE, delay: 0.1 }}
        style={{ position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: sheetWidth, background: '#fff', borderTop: '1px solid #e5e5e5',
        padding: '12px 20px calc(12px + env(safe-area-inset-bottom, 0px))', zIndex: 60 }}>
        <motion.button onClick={() => canSubmit && setSubmitted(true)} disabled={!canSubmit}
          whileHover={canSubmit ? { scale: 1.02 } : {}} whileTap={canSubmit ? { scale: 0.97 } : {}}
          style={{ width: '100%', padding: '15px', border: 'none',
            background: canSubmit ? '#1a1a1a' : '#ccc', color: '#fff',
            cursor: canSubmit ? 'pointer' : 'not-allowed',
            fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>
          Request booking · {money(total)}
        </motion.button>
      </motion.div>
    </Shell>
  )
}

function Row({ label, value, bold }) {
  return (
    <motion.div variants={fadeUp} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderTop: bold ? '1px solid #f0f0f0' : 'none' }}>
      <span style={{ fontSize: 13, color: bold ? '#1a1a1a' : '#666', fontWeight: bold ? 600 : 400 }}>{label}</span>
      <span style={{ fontSize: bold ? 16 : 13, color: '#1a1a1a', fontWeight: bold ? 600 : 400,
        fontFamily: bold ? SERIF : 'inherit' }}>{value}</span>
    </motion.div>
  )
}

const stepBtn = {
  width: 44, height: 44, border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}

// ── existing-booking detail (confirm-and-pay + live status) ─────────────────────
// Canonical lifecycle: requested -> accepted -> confirmed(=client paid) ->
// in_progress -> pending_confirmation(=client signs off) -> completed.
const STAGES = ['requested', 'accepted', 'confirmed', 'in_progress', 'pending_confirmation', 'completed']
const STAGE_LABEL = {
  requested: 'Requested', accepted: 'Accepted', confirmed: 'Paid',
  in_progress: 'Working', pending_confirmation: 'Sign-off', completed: 'Done',
}

const MOCK_DETAIL = {
  b1: { cook: 'Amara Okafor',     tier: 'gold',   date: 'Fri, Jun 6', time: '18:00', hours: 3, rate: 45, address: '128 Edgewood Ave NE, Atlanta', status: 'confirmed' },
  b2: { cook: 'Mei Lin',       tier: 'gold',   date: 'Sun, Jun 8', time: '17:00', hours: 4, rate: 52, address: '450 Commerce Dr, Decatur',    status: 'requested' },
  b3: { cook: 'Diego Ramirez', tier: 'silver', date: 'Mon, Jun 2', time: '19:00', hours: 2, rate: 38, address: '77 Peachtree St, Atlanta',    status: 'pending_confirmation' },
  b4: { cook: 'Sara Haile',     tier: 'bronze', date: 'Sat, May 24', time: '18:30', hours: 3, rate: 40, address: '12 Krog St NE, Atlanta',     status: 'completed' },
  b5: { cook: 'Tom Becker',    tier: 'bronze', date: 'Sun, May 18', time: '12:00', hours: 2, rate: 35, address: '900 Marietta St, Marietta',  status: 'cancelled' },
  b7: { cook: 'Lena M.',        tier: 'silver', date: 'Sun, Jun 8', time: '17:00', hours: 4, rate: 48, address: '210 Ponce de Leon, Atlanta', status: 'confirmed' },
}
const FALLBACK_DETAIL = { cook: 'Mise Helper', tier: 'silver', date: 'Soon', time: '18:00', hours: 3, rate: 42, address: 'Your address', status: 'requested' }

function StatusTimeline({ status }) {
  // ingredient_request is an accepted booking awaiting a supplies add-on, so it
  // sits at the 'accepted' stage. pending_confirmation is now its own late stage.
  const ALIAS = { ingredient_request: 'accepted' }
  const effective = ALIAS[status] || status
  const idx = STAGES.indexOf(effective)

  if (status === 'cancelled') {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, ease: EASE }}
        style={{ padding: '16px 20px', background: '#FBE9E9', color: '#C53030', fontSize: 13, textAlign: 'center' }}>
        This booking was cancelled.
      </motion.div>
    )
  }
  if (status === 'disputed') {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, ease: EASE }}
        style={{ padding: '16px 20px', background: '#FFF4E5', color: '#B7791F', fontSize: 13, textAlign: 'center' }}>
        This booking is under dispute — our team is reviewing it.
      </motion.div>
    )
  }
  // Unknown / off-pipeline status: neutral fallback rather than an empty timeline.
  if (idx === -1) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, ease: EASE }}
        style={{ padding: '16px 20px', background: '#F5F5F3', color: '#777', fontSize: 13, textAlign: 'center' }}>
        Status: {String(status).replace(/_/g, ' ')}
      </motion.div>
    )
  }
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: EASE }}
      style={{ display: 'flex', padding: '20px 20px 8px' }}>
      {STAGES.map((s, i) => {
        const done = i <= idx
        const here = i === idx
        return (
          <div key={s} style={{ flex: 1, textAlign: 'center', position: 'relative' }}>
            {i > 0 && <motion.div initial={false} animate={{ background: i <= idx ? '#1F6F5C' : '#e5e5e5' }}
              transition={{ duration: 0.3, ease: EASE }}
              style={{ position: 'absolute', top: 9, left: '-50%', width: '100%', height: 2 }} />}
            <motion.div initial={false} animate={{ background: done ? '#1F6F5C' : '#fff', borderColor: done ? '#1F6F5C' : '#e5e5e5' }}
              transition={{ duration: 0.3, ease: EASE }}
              style={{ position: 'relative', width: 20, height: 20, margin: '0 auto 6px', borderRadius: '50%',
              border: '2px solid', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <AnimatePresence>
                {done && (
                  <motion.span key="check" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0, opacity: 0 }} transition={{ duration: 0.2, ease: EASE }}
                    style={{ display: 'flex' }}>
                    <Check size={11} color="#fff" strokeWidth={3} />
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.div>
            <span style={{ fontSize: 9, letterSpacing: 0.3, color: here ? '#1a1a1a' : '#aaa',
              fontWeight: here ? 600 : 400 }}>{STAGE_LABEL[s]}</span>
          </div>
        )
      })}
    </motion.div>
  )
}

function ReviewSheet({ cook, onClose }) {
  const isDesktop = useIsDesktop()
  const [stars, setStars] = useState(5)
  const [text, setText] = useState('')
  const [sent, setSent] = useState(false)
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
      style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }} onClick={onClose}>
      <motion.div onClick={e => e.stopPropagation()}
        initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 30 }}
        transition={{ duration: 0.3, ease: EASE }}
        style={{ width: isDesktop ? 'min(560px,100vw)' : 'min(430px,100vw)', background: '#fff',
        padding: '24px 22px calc(24px + env(safe-area-inset-bottom,0px))' }}>
        <AnimatePresence mode="wait">
          {sent ? (
            <motion.div key="sent" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.25, ease: EASE }} style={{ textAlign: 'center', padding: '20px 0' }}>
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.3, ease: EASE }} style={{ display: 'inline-flex' }}>
                <Check size={36} color="#1F6F5C" strokeWidth={2.5} />
              </motion.div>
              <p style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a', margin: '12px 0 0' }}>Thanks for the review</p>
            </motion.div>
          ) : (
            <motion.div key="form" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
              <h3 style={{ fontFamily: SERIF, fontSize: 24, fontWeight: 400, color: '#1a1a1a', margin: '0 0 4px' }}>
                How was {cook}?
              </h3>
              <p style={{ fontSize: 13, color: '#777', margin: '0 0 16px' }}>Your review helps other clients.</p>
              <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
                {[1, 2, 3, 4, 5].map(i => (
                  <motion.button key={i} onClick={() => setStars(i)} whileTap={{ scale: 0.85 }}
                    aria-label={`${i} star${i > 1 ? 's' : ''}`} aria-pressed={i <= stars}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                    <Star size={32} color="#C9A227" fill={i <= stars ? '#C9A227' : 'none'} strokeWidth={1.5} />
                  </motion.button>
                ))}
              </div>
              <textarea value={text} onChange={e => setText(e.target.value)} rows={3} placeholder="Tell us how the visit went…"
                style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', padding: '12px 14px',
                  fontSize: 14, outline: 'none', resize: 'vertical', fontFamily: 'inherit', marginBottom: 16 }} />
              <motion.button onClick={() => setSent(true)} {...buttonPress} style={{ width: '100%', padding: '14px', background: '#1F6F5C',
                color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1,
                textTransform: 'uppercase', fontWeight: 600 }}>Submit review</motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}

function BookingDetail({ bookingId }) {
  const navigate = useNavigate()
  const isDesktop = useIsDesktop()
  const sheetWidth = isDesktop ? 'min(560px,100vw)' : 'min(430px,100vw)'
  const { profile } = useAuth()
  const activeRole = profile?.activeRole || profile?.active_role || 'eater'
  const isCook = activeRole === 'cook'
  const base = MOCK_DETAIL[bookingId] || FALLBACK_DETAIL
  const [status, setStatus] = useState(base.status)
  const [paying, setPaying] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const tc = TIER_COLOR[base.tier] || '#777'

  const subtotal = subtotalOf(base.rate, base.hours)
  const fee = serviceFee(subtotal)
  const total = eaterTotal(subtotal)

  return (
    <Shell header={<Header onBack={() => navigate('/bookings')} title="Booking" />} showNav={false}>
      <StatusTimeline status={status} />

      <motion.div variants={staggerContainer(0.07)} initial="hidden" animate="show">
        {/* helper summary */}
        <motion.div variants={fadeUp} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px 18px' }}>
          <div style={{ width: 56, height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: base.photo ? `#eee url(${base.photo}) center/cover` : '#EDE7DF' }}>
            {!base.photo && <span style={{ fontFamily: SERIF, fontSize: 22, color: '#9a8c7a' }}>{(base.cook || '?').trim().charAt(0).toUpperCase()}</span>}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: SERIF, fontSize: 21, color: '#1a1a1a' }}>{base.cook}</span>
              <ShieldCheck size={15} color={tc} strokeWidth={2} />
            </div>
            <span style={{ fontSize: 12, color: '#777' }}>{base.tier} verified · {money(base.rate)}/hr</span>
          </div>
        </motion.div>

        <Section icon={Calendar} title="When & where">
          <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show"
            style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '4px 16px' }}>
            <Row label="Date" value={`${base.date} · ${base.time}`} />
            <Row label="Duration" value={`${base.hours} hours`} />
            <Row label="Address" value={base.address} />
          </motion.div>
        </Section>

        <Section title="Payment">
          <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show"
            style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '4px 16px' }}>
            <Row label={`${money(base.rate)} × ${base.hours} hrs`} value={money(subtotal)} />
            <Row label="Service fee" value={money(fee)} />
            <Row label="Total" value={money(total)} bold />
          </motion.div>
        </Section>
      </motion.div>

      <div style={{ height: 96 }} />

      {/* status-driven action bar */}
      <div style={{ position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: sheetWidth, background: '#fff', borderTop: '1px solid #e5e5e5',
        padding: '12px 20px calc(12px + env(safe-area-inset-bottom,0px))', zIndex: 60 }}>
        <AnimatePresence mode="wait">
          <motion.div key={`${isCook}-${status}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22, ease: EASE }}>
            {isCook ? (
              <>
                {status === 'requested' && (
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#777', padding: '6px 0' }}>
                    Respond to this request from your jobs list.
                  </div>
                )}
                {(status === 'accepted' || status === 'ingredient_request') && (
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#777', padding: '6px 0' }}>
                    Waiting for the client to confirm &amp; pay.
                  </div>
                )}
                {status === 'confirmed' && (
                  <motion.button onClick={() => setStatus('in_progress')} {...buttonPress} style={{ width: '100%', padding: '15px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <Play size={16} strokeWidth={1.5} /> Start job
                  </motion.button>
                )}
                {status === 'in_progress' && (
                  <motion.button onClick={() => setStatus('pending_confirmation')} {...buttonPress} style={{ width: '100%', padding: '15px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <Flag size={16} strokeWidth={1.5} /> Mark complete
                  </motion.button>
                )}
                {status === 'pending_confirmation' && (
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#777', padding: '6px 0' }}>
                    Job done — waiting for the client to confirm.
                  </div>
                )}
                {status === 'completed' && (
                  <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.3, ease: EASE }}
                    style={{ textAlign: 'center', fontSize: 13, color: '#1F6F5C', fontWeight: 600, padding: '6px 0' }}>
                    Job complete — payout {money(cookPayout(subtotal))} on its way.
                  </motion.div>
                )}
                {status === 'cancelled' && (
                  <motion.button onClick={() => navigate('/bookings')} {...buttonPress} style={{ width: '100%', padding: '14px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600 }}>Back to my jobs</motion.button>
                )}
              </>
            ) : (
              <>
                {status === 'requested' && (
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#777', padding: '6px 0' }}>
                    Waiting for {base.cook} to accept your request.
                  </div>
                )}
                {(status === 'accepted' || status === 'ingredient_request') && (
                  <motion.button onClick={() => setPaying(true)} {...buttonPress} style={{ width: '100%', padding: '15px', background: '#C4561F',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <CreditCard size={16} strokeWidth={1.5} /> Confirm & pay {money(total)}
                  </motion.button>
                )}
                {status === 'confirmed' && (
                  <div>
                    <motion.p initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3, ease: EASE }}
                      style={{ textAlign: 'center', fontSize: 13, color: '#1F6F5C', fontWeight: 600, margin: '0 0 10px' }}>
                      Paid — {base.cook} will arrive {base.date}.
                    </motion.p>
                    <motion.button onClick={() => setStatus('cancelled')} whileTap={tapScale} style={{ width: '100%', padding: '14px', background: '#fff',
                      color: '#C53030', border: '1px solid #e5e5e5', cursor: 'pointer', fontSize: 13, letterSpacing: 1,
                      textTransform: 'uppercase', fontWeight: 600 }}>
                      Cancel booking
                    </motion.button>
                  </div>
                )}
                {status === 'in_progress' && (
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#1F6F5C', fontWeight: 600, padding: '6px 0' }}>
                    {base.cook} is on the job now.
                  </div>
                )}
                {status === 'pending_confirmation' && (
                  <motion.button onClick={() => setStatus('completed')} {...buttonPress} style={{ width: '100%', padding: '15px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <Check size={16} strokeWidth={2} /> Confirm the job's done
                  </motion.button>
                )}
                {status === 'completed' && (
                  <motion.button onClick={() => setReviewing(true)} {...buttonPress} style={{ width: '100%', padding: '15px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <Star size={16} strokeWidth={1.5} /> Leave a review
                  </motion.button>
                )}
                {status === 'cancelled' && (
                  <motion.button onClick={() => navigate('/browse')} {...buttonPress} style={{ width: '100%', padding: '14px', background: '#1F6F5C',
                    color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, letterSpacing: 1, textTransform: 'uppercase',
                    fontWeight: 600 }}>Find another helper</motion.button>
                )}
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* mock pay sheet */}
      <AnimatePresence>
        {paying && (
          <motion.div key="pay-sheet" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
            style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }} onClick={() => setPaying(false)}>
            <motion.div onClick={e => e.stopPropagation()}
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 30 }}
              transition={{ duration: 0.3, ease: EASE }}
              style={{ width: sheetWidth, background: '#fff',
              padding: '24px 22px calc(24px + env(safe-area-inset-bottom,0px))' }}>
              <h3 style={{ fontFamily: SERIF, fontSize: 24, fontWeight: 400, color: '#1a1a1a', margin: '0 0 16px' }}>
                Confirm payment
              </h3>
              <div style={{ border: '1px solid #e5e5e5', padding: '12px 14px', display: 'flex', alignItems: 'center',
                gap: 10, marginBottom: 16 }}>
                <CreditCard size={20} color="#555" strokeWidth={1.5} />
                <span style={{ fontSize: 14, color: '#1a1a1a' }}>Visa •••• 4242</span>
                <button type="button" onClick={() => {}} style={{ marginLeft: 'auto', fontSize: 12, color: '#1a1a1a',
                  background: 'none', border: 'none', padding: 0, cursor: 'pointer', textDecoration: 'underline' }}>Change</button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 16, marginBottom: 18 }}>
                <span style={{ color: '#1a1a1a', fontWeight: 600 }}>Total</span>
                <span style={{ fontFamily: SERIF, fontSize: 20, color: '#1a1a1a' }}>{money(total)}</span>
              </div>
              <motion.button onClick={() => { setPaying(false); setStatus('confirmed') }} {...buttonPress} style={{ width: '100%', padding: '15px',
                background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, letterSpacing: 1,
                textTransform: 'uppercase', fontWeight: 600, display: 'inline-flex', alignItems: 'center',
                justifyContent: 'center', gap: 8 }}>
                <Lock size={15} strokeWidth={1.5} /> Pay {money(total)}
              </motion.button>
              <p style={{ fontSize: 11, color: '#aaa', textAlign: 'center', margin: '12px 0 0' }}>
                Secured by Stripe. You can cancel free up to 24h before.
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {reviewing && <ReviewSheet key="review-sheet" cook={base.cook} onClose={() => setReviewing(false)} />}
      </AnimatePresence>
    </Shell>
  )
}

export default function BookingScreen() {
  const { cookId, bookingId } = useParams()
  return cookId ? <NewBooking cookId={cookId} /> : <BookingDetail bookingId={bookingId} />
}
