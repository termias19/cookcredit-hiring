/**
 * My jobs (helper) — the helper's counterpart to EaterBookingsScreen.
 *
 * Three-tab pipeline (Requests / Upcoming / History) over the helper's bookings.
 * Requests carry Accept (green) + Decline (outline) actions that optimistically
 * move the card via local state. Upcoming surfaces a status-driven primary
 * action (Start job / Mark complete). Every card shows PAYOUT (total minus the
 * ~15% platform fee) since this is the earner's view. Empty states route
 * forward so the flow never dead-ends.
 *
 * Mock data for now; wires to GET /api/bookings?role=cook later (fields already
 * match the Booking model's to_dict()).
 */
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Inbox, MapPin, Clock, Check, X, ChevronRight, Play, CheckCircle2, Sparkles } from 'lucide-react'
import Shell from '../components/Shell'
import { subtotalOf, cookPayout, money } from '../utils/money'
import { fadeUp, staggerContainer, listItem, hoverLift, buttonPress, tapScale, EASE } from '../styles/motion'

const cardExit = { opacity: 0, scale: 0.96, transition: { duration: 0.2, ease: EASE } }

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

// Helper payout derived from the booking SUBTOTAL (rate × hours) so it reconciles
// with the client total and platform cut defined in utils/money.js.
const payoutOf = b => cookPayout(subtotalOf(b.rate, b.hours))

// status -> { label, fg, bg } — mirrors the Booking.status check constraint.
const STATUS = {
  requested:            { label: 'New request',    fg: '#B87800', bg: '#FBF3E2' },
  accepted:             { label: 'Accepted',        fg: '#1F6F5C', bg: '#E8F1EC' },
  ingredient_request:   { label: 'Supplies list',   fg: '#B87800', bg: '#FBF3E2' },
  confirmed:            { label: 'Confirmed',        fg: '#1F6F5C', bg: '#E8F1EC' },
  in_progress:          { label: 'In progress',      fg: '#123F34', bg: '#DDEBE3' },
  pending_confirmation: { label: 'Awaiting client',  fg: '#C4561F', bg: '#FBEAE1' },
  completed:            { label: 'Completed',         fg: '#777',    bg: '#F2F2F2' },
  cancelled:            { label: 'Cancelled',         fg: '#C53030', bg: '#FBE9E9' },
  disputed:             { label: 'Disputed',          fg: '#C53030', bg: '#FBE9E9' },
}

const TAB_FILTER = {
  requests: new Set(['requested', 'ingredient_request']),
  upcoming: new Set(['accepted', 'confirmed', 'in_progress', 'pending_confirmation']),
  history:  new Set(['completed', 'cancelled', 'disputed']),
}

// rate = hourly rate; subtotal/payout/client-total all derive from rate × hours via utils/money.js.
const INITIAL = [
  { id: 'j1', eater: 'Hannah Weiss',     area: 'Inman Park · 1.8 mi',   date: 'Fri, Jun 6',  time: '18:00', hours: 3, rate: 45, status: 'requested', note: 'Weekly house cleaning — focus on kitchen and bathrooms.' },
  { id: 'j2', eater: 'Marcus Bell',      area: 'Old Fourth Ward · 2.4 mi', date: 'Sat, Jun 7',  time: '17:30', hours: 4, rate: 45, status: 'requested', note: 'Two kids after school — homework help and light meal prep.' },
  { id: 'j3', eater: 'Priya Raman',     area: 'Decatur · 4.0 mi',      date: 'Sun, Jun 8',  time: '12:00', hours: 2, rate: 48, status: 'confirmed', note: '' },
  { id: 'j4', eater: 'The Olu Family',     area: 'Kirkwood · 3.1 mi',     date: 'Today',       time: '19:00', hours: 3, rate: 48, status: 'in_progress', note: '' },
  { id: 'j5', eater: 'Daniel Cho',      area: 'Midtown · 5.2 mi',      date: 'Mon, Jun 9',  time: '18:30', hours: 3, rate: 45, status: 'pending_confirmation', note: '' },
  { id: 'j6', eater: 'Sara Haile',      area: 'Edgewood · 2.0 mi',     date: 'Sat, May 24', time: '18:30', hours: 3, rate: 44, status: 'completed', note: '' },
  { id: 'j7', eater: 'Tom Becker',       area: 'Grant Park · 3.6 mi',   date: 'Sun, May 18', time: '12:00', hours: 2, rate: 35, status: 'completed', note: '' },
  { id: 'j8', eater: 'Lena Marsh',       area: 'Candler Park · 1.2 mi', date: 'Fri, May 9',  time: '19:30', hours: 2, rate: 45, status: 'cancelled', note: '' },
]

const TABS = [
  { key: 'requests', label: 'Requests' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'history',  label: 'History' },
]

function StatusChip({ status }) {
  const s = STATUS[status] || STATUS.requested
  return (
    <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase',
      color: s.fg, background: s.bg, padding: '4px 9px', borderRadius: 2, whiteSpace: 'nowrap' }}>
      {s.label}
    </span>
  )
}

function MetaRow({ b }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 6 }}>
      <p style={{ fontSize: 13, color: '#666', margin: 0, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <Clock size={13} strokeWidth={1.5} color="#999" /> {b.date} · {b.time} · {b.hours} hrs
      </p>
      <p style={{ fontSize: 13, color: '#999', margin: 0, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <MapPin size={13} strokeWidth={1.5} color="#bbb" /> {b.area}
      </p>
    </div>
  )
}

function PayoutBlock({ b, align = 'right' }) {
  return (
    <div style={{ textAlign: align }}>
      <div style={{ fontFamily: SERIF, fontSize: 22, color: '#1F6F5C', lineHeight: 1.05 }}>
        {money(payoutOf(b))}
      </div>
      <div style={{ fontSize: 10, color: '#aaa', letterSpacing: 0.5 }}>your payout</div>
    </div>
  )
}

// Requests tab card — client context + Accept / Decline.
function RequestCard({ b, onAccept, onDecline }) {
  return (
    <motion.div variants={listItem} initial="hidden" animate="show" exit={cardExit} whileHover={hoverLift}
      style={{ background: '#fff', border: '1px solid #C9A227', padding: 14, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', gap: 14 }}>
        <div style={{ width: 56, height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: b.photo ? `#eee url(${b.photo}) center/cover` : '#EDE7DF' }}>
          {!b.photo && <span style={{ fontFamily: SERIF, fontSize: 20, color: '#9a8c7a' }}>{(b.eater || '?').trim().charAt(0).toUpperCase()}</span>}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span style={{ fontFamily: SERIF, fontSize: 19, color: '#1a1a1a', flex: 1, minWidth: 0,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.eater}</span>
            <span style={{ flexShrink: 0 }}><StatusChip status={b.status} /></span>
          </div>
          <MetaRow b={b} />
        </div>
      </div>

      {b.note && (
        <p style={{ fontSize: 13, lineHeight: 1.5, color: '#555', margin: '12px 0 0', paddingLeft: 12,
          borderLeft: '2px solid #eee', fontStyle: 'italic' }}>
          “{b.note}”
        </p>
      )}

      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        gap: 12, marginTop: 'auto', paddingTop: 14, borderTop: '1px solid #f0f0f0' }}>
        <PayoutBlock b={b} align="left" />
        <div style={{ display: 'flex', gap: 8 }}>
          <motion.button onClick={onDecline} whileTap={tapScale} style={{
            padding: '11px 16px', background: '#fff', color: '#555', border: '1px solid #e5e5e5',
            cursor: 'pointer', fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <X size={15} strokeWidth={2} /> Decline
          </motion.button>
          <motion.button onClick={onAccept} {...buttonPress} style={{
            padding: '11px 18px', background: '#1F6F5C', color: '#fff', border: 'none',
            cursor: 'pointer', fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Check size={15} strokeWidth={2.5} /> Accept
          </motion.button>
        </div>
      </div>
    </motion.div>
  )
}

// Upcoming tab card — status-driven primary action.
function UpcomingCard({ b, onAdvance, onOpen }) {
  // 'accepted' = helper said yes but the client hasn't paid yet; 'pending_confirmation' = job
  // done, awaiting client sign-off. Both wait on the client, so neither exposes a primary action.
  const cta = b.status === 'in_progress'
    ? { label: 'Mark complete', Icon: CheckCircle2 }
    : (b.status === 'accepted' || b.status === 'pending_confirmation')
      ? null
      : { label: 'Start job', Icon: Play }

  return (
    <motion.div variants={listItem} initial="hidden" animate="show" exit={cardExit} whileHover={hoverLift}
      style={{ background: '#fff', border: '1px solid #e5e5e5', padding: 14, display: 'flex', flexDirection: 'column' }}>
      <button onClick={onOpen} style={{
        display: 'flex', gap: 14, width: '100%', textAlign: 'left', cursor: 'pointer',
        background: 'none', border: 'none', padding: 0 }}>
        <div style={{ width: 56, height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: b.photo ? `#eee url(${b.photo}) center/cover` : '#EDE7DF' }}>
          {!b.photo && <span style={{ fontFamily: SERIF, fontSize: 20, color: '#9a8c7a' }}>{(b.eater || '?').trim().charAt(0).toUpperCase()}</span>}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span style={{ fontFamily: SERIF, fontSize: 19, color: '#1a1a1a', flex: 1, minWidth: 0,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.eater}</span>
            <span style={{ flexShrink: 0 }}><StatusChip status={b.status} /></span>
          </div>
          <MetaRow b={b} />
        </div>
      </button>

      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        gap: 12, marginTop: 'auto', paddingTop: 14, borderTop: '1px solid #f0f0f0' }}>
        <PayoutBlock b={b} align="left" />
        {cta ? (
          <motion.button onClick={onAdvance} {...buttonPress} style={{
            padding: '12px 18px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
            fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
            display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            <cta.Icon size={15} strokeWidth={2} /> {cta.label}
          </motion.button>
        ) : (
          <span style={{ fontSize: 12, color: '#C4561F', maxWidth: 160, textAlign: 'right', lineHeight: 1.4 }}>
            {b.status === 'pending_confirmation'
              ? "Waiting on the client to confirm the job's done."
              : 'Waiting on the client to confirm & pay.'}
          </span>
        )}
      </div>
    </motion.div>
  )
}

// History tab card — compact, payout + status chip.
function HistoryCard({ b, onOpen }) {
  return (
    <motion.button onClick={onOpen} variants={listItem} initial="hidden" animate="show" exit={cardExit} whileHover={hoverLift} whileTap={tapScale} style={{
      display: 'flex', alignItems: 'center', gap: 14, width: '100%', textAlign: 'left', cursor: 'pointer',
      background: '#fff', border: '1px solid #e5e5e5', padding: 14 }}>
      <div style={{ width: 52, height: 52, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: b.photo ? `#eee url(${b.photo}) center/cover` : '#EDE7DF' }}>
        {!b.photo && <span style={{ fontFamily: SERIF, fontSize: 18, color: '#9a8c7a' }}>{(b.eater || '?').trim().charAt(0).toUpperCase()}</span>}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
          <span style={{ fontFamily: SERIF, fontSize: 18, color: '#1a1a1a', flex: 1, minWidth: 0,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.eater}</span>
          <span style={{ flexShrink: 0 }}><StatusChip status={b.status} /></span>
        </div>
        <p style={{ fontSize: 13, color: '#666', margin: '0 0 2px' }}>{b.date} · {b.hours} hrs</p>
        <p style={{ fontSize: 13, color: b.status === 'completed' ? '#1F6F5C' : '#999', margin: 0 }}>
          {b.status === 'completed' ? `+${money(payoutOf(b))} earned` : money(payoutOf(b))}
        </p>
      </div>
      <ChevronRight size={18} color="#ccc" strokeWidth={1.5} style={{ flexShrink: 0 }} />
    </motion.button>
  )
}

function Header({ tab, setTab, counts }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 0' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: '0 0 20px' }}>My jobs</h1>
        <div style={{ display: 'flex', gap: 24 }}>
          {TABS.map(t => (
            <motion.button key={t.key} onClick={() => setTab(t.key)} whileTap={tapScale} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 12px',
              fontSize: 13, letterSpacing: 1, textTransform: 'uppercase',
              fontWeight: tab === t.key ? 600 : 400, color: tab === t.key ? '#1a1a1a' : '#aaa',
              borderBottom: tab === t.key ? '2px solid #1a1a1a' : '2px solid transparent',
              display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {t.label}
              {t.key === 'requests' && counts.requests > 0 && (
                <motion.span key={counts.requests} initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  transition={{ duration: 0.2, ease: EASE }} style={{ fontSize: 10, fontWeight: 700, color: '#fff', background: '#C9A227',
                  borderRadius: 999, minWidth: 16, height: 16, padding: '0 4px', display: 'inline-flex',
                  alignItems: 'center', justifyContent: 'center' }}>
                  {counts.requests}
                </motion.span>
              )}
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  )
}

function EmptyState({ tab, navigate }) {
  const copy = {
    requests: { line: 'No new requests right now.', cta: 'Polish your profile', to: '/profile' },
    upcoming: { line: 'No jobs on the calendar yet.', cta: 'Get verified', to: '/skill' },
    history:  { line: 'Your completed jobs will live here.', cta: 'View your profile', to: '/profile' },
  }[tab]
  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ textAlign: 'center', padding: '56px 20px' }}>
      <Inbox size={32} color="#ddd" strokeWidth={1.5} />
      <p style={{ fontSize: 14, color: '#999', margin: '14px 0 20px' }}>{copy.line}</p>
      <motion.button onClick={() => navigate(copy.to)} {...buttonPress} style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px',
        background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
        fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>
        <Sparkles size={15} strokeWidth={1.5} /> {copy.cta}
      </motion.button>
    </motion.div>
  )
}

export default function CookBookingsScreen() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('requests')
  const [jobs, setJobs] = useState(INITIAL)
  const [toast, setToast] = useState(null)

  const flash = msg => {
    setToast(msg)
    setTimeout(() => setToast(null), 2200)
  }

  const setStatus = (id, status, msg) => {
    setJobs(prev => prev.map(j => (j.id === id ? { ...j, status } : j)))
    if (msg) flash(msg)
  }

  const counts = useMemo(() => ({
    requests: jobs.filter(j => TAB_FILTER.requests.has(j.status)).length,
  }), [jobs])

  const list = useMemo(
    () => jobs.filter(j => TAB_FILTER[tab].has(j.status)),
    [jobs, tab],
  )

  // pending weekly earnings (accepted/confirmed/in_progress) — a confident helper-view stat.
  const pipeline = useMemo(
    () => jobs.filter(j => TAB_FILTER.upcoming.has(j.status))
      .reduce((sum, j) => sum + payoutOf(j), 0),
    [jobs],
  )

  const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20 }

  return (
    <Shell wide header={<Header tab={tab} setTab={setTab} counts={counts} />}>
      <div style={{ padding: '24px 0 20px' }}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22, ease: EASE }}>
            {tab === 'upcoming' && list.length > 0 && (
              <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
                border: '1px solid #e5e5e5', background: '#fff', padding: '12px 16px', marginBottom: 16, maxWidth: 420 }}>
                <span style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase' }}>
                  Booked earnings
                </span>
                <span style={{ fontFamily: SERIF, fontSize: 24, color: '#1F6F5C' }}>{money(pipeline)}</span>
              </motion.div>
            )}

            <motion.div variants={staggerContainer()} initial="hidden" animate="show" style={grid}>
              <AnimatePresence>
                {tab === 'requests' && list.map(b => (
                  <RequestCard key={b.id} b={b}
                    onAccept={() => setStatus(b.id, 'accepted', 'Accepted — waiting on the client to confirm & pay.')}
                    onDecline={() => setStatus(b.id, 'cancelled', `Declined ${b.eater}'s request.`)} />
                ))}

                {tab === 'upcoming' && list.map(b => (
                  <UpcomingCard key={b.id} b={b}
                    onOpen={() => navigate(`/booking/${b.id}`)}
                    onAdvance={() => b.status === 'in_progress'
                      ? setStatus(b.id, 'pending_confirmation', `Marked complete — ${b.eater} will confirm the job's done.`)
                      : setStatus(b.id, 'in_progress', `Job started for ${b.eater}. Let's get started!`)} />
                ))}

                {tab === 'history' && list.map(b => (
                  <HistoryCard key={b.id} b={b} onOpen={() => navigate(`/booking/${b.id}`)} />
                ))}
              </AnimatePresence>
            </motion.div>

            {list.length === 0 && <EmptyState tab={tab} navigate={navigate} />}
          </motion.div>
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {toast && (
          <motion.div key="toast" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }} transition={{ duration: 0.22, ease: EASE }}
            style={{ position: 'fixed', bottom: 'calc(76px + env(safe-area-inset-bottom, 0px))',
            left: '50%', transform: 'translateX(-50%)', width: 'min(390px, 92vw)',
            background: '#1F6F5C', color: '#fff', padding: '12px 16px', fontSize: 13, letterSpacing: 0.3,
            display: 'flex', alignItems: 'center', gap: 8, zIndex: 80, boxShadow: '0 6px 24px rgba(0,0,0,0.18)' }}>
            <Check size={16} strokeWidth={2.5} color="#7FC8A0" />
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </Shell>
  )
}
