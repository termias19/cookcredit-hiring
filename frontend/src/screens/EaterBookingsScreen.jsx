/**
 * My bookings (client) — the list "View my bookings" lands on.
 *
 * Upcoming / Past toggle over the client's bookings. Each card shows the
 * helper, date + time, a color-coded status chip (matching the Booking.status
 * vocabulary), and the total; tapping opens /booking/:id. Empty states route
 * back to Browse so the flow always has a next step.
 *
 * Mock data for now; wires to GET /api/bookings later (fields already match the
 * Booking model's to_dict()).
 */
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { CalendarCheck, ChevronRight, Search } from 'lucide-react'
import Shell from '../components/Shell'
import { money } from '../utils/money.js'
import { fadeUp, staggerContainer, listItem, hoverLift, buttonPress, tapScale, EASE } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

// status -> { label, fg, bg } — mirrors the Booking.status check constraint.
const STATUS = {
  requested:            { label: 'Requested',     fg: '#B87800', bg: '#FBF3E2' },
  accepted:             { label: 'Accepted',       fg: '#1F6F5C', bg: '#E8F1EC' },
  ingredient_request:   { label: 'Supplies list',  fg: '#B87800', bg: '#FBF3E2' },
  confirmed:            { label: 'Confirmed',       fg: '#1F6F5C', bg: '#E8F1EC' },
  in_progress:          { label: 'In progress',     fg: '#123F34', bg: '#DDEBE3' },
  pending_confirmation: { label: 'Confirm & pay',   fg: '#C4561F', bg: '#FBEAE1' },
  completed:            { label: 'Completed',        fg: '#777',    bg: '#F2F2F2' },
  cancelled:            { label: 'Cancelled',        fg: '#C53030', bg: '#FBE9E9' },
  disputed:             { label: 'Disputed',         fg: '#C53030', bg: '#FBE9E9' },
}
const UPCOMING = new Set(['requested', 'accepted', 'ingredient_request', 'confirmed', 'in_progress', 'pending_confirmation'])

const MOCK_BOOKINGS = [
  { id: 'b1', cook: 'Amara Okafor',  date: 'Fri, Jun 6',  time: '18:00', hours: 3, total: 148.50, status: 'confirmed' },
  { id: 'b2', cook: 'Mei Lin',       date: 'Sun, Jun 8',  time: '17:00', hours: 4, total: 228.80, status: 'requested' },
  { id: 'b3', cook: 'Diego Ramirez', date: 'Mon, Jun 2',  time: '19:00', hours: 2, total: 83.60,  status: 'pending_confirmation' },
  { id: 'b4', cook: 'Sara Haile',    date: 'Sat, May 24', time: '18:30', hours: 3, total: 132.00, status: 'completed' },
  { id: 'b5', cook: 'Tom Becker',    date: 'Sun, May 18', time: '12:00', hours: 2, total: 77.00,  status: 'cancelled' },
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

function BookingCard({ b, onClick }) {
  const action = b.status === 'pending_confirmation'
  return (
    <motion.button onClick={onClick} variants={listItem} initial="hidden" animate="show"
      exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.2, ease: EASE } }}
      whileHover={hoverLift} whileTap={tapScale} style={{
      display: 'flex', flexDirection: 'column', textAlign: 'left', cursor: 'pointer',
      background: '#fff', border: `1px solid ${action ? '#C4561F' : '#e5e5e5'}`, padding: 0, overflow: 'hidden' }}>
      <div style={{ width: '100%', height: 140, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: b.photo ? `#eee url(${b.photo}) center/cover` : '#EDE7DF' }}>
        {!b.photo && <span style={{ fontFamily: SERIF, fontSize: 30, color: '#9a8c7a' }}>{(b.cook || '?').trim().charAt(0).toUpperCase()}</span>}
      </div>
      <div style={{ flex: 1, padding: '14px 16px 16px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
          <span style={{ fontFamily: SERIF, fontSize: 19, color: '#1a1a1a',
            flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.cook}</span>
          <span style={{ flexShrink: 0 }}><StatusChip status={b.status} /></span>
        </div>
        <p style={{ fontSize: 13, color: '#666', margin: '0 0 2px' }}>{b.date} · {b.time} · {b.hours} hrs</p>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto', paddingTop: 8 }}>
          <p style={{ fontSize: 13, color: '#999', margin: 0 }}>{money(b.total)}</p>
          <ChevronRight size={18} color="#ccc" strokeWidth={1.5} style={{ flexShrink: 0 }} />
        </div>
      </div>
    </motion.button>
  )
}

function Header({ tab, setTab }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 0' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: '0 0 20px' }}>My bookings</h1>
        <div style={{ display: 'flex', gap: 24 }}>
          {['upcoming', 'past'].map(t => (
            <motion.button key={t} onClick={() => setTab(t)} whileTap={tapScale} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 12px',
              fontSize: 13, letterSpacing: 1, textTransform: 'uppercase',
              fontWeight: tab === t ? 600 : 400, color: tab === t ? '#1a1a1a' : '#aaa',
              borderBottom: tab === t ? '2px solid #1a1a1a' : '2px solid transparent' }}>
              {t}
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function EaterBookingsScreen() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('upcoming')

  const list = useMemo(
    () => MOCK_BOOKINGS.filter(b => (tab === 'upcoming' ? UPCOMING.has(b.status) : !UPCOMING.has(b.status))),
    [tab],
  )

  const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 20 }

  return (
    <Shell wide header={<Header tab={tab} setTab={setTab} />}>
      <div style={{ padding: '24px 0 20px' }}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22, ease: EASE }}>
            <motion.div variants={staggerContainer()} initial="hidden" animate="show" style={grid}>
              <AnimatePresence>
                {list.map(b => <BookingCard key={b.id} b={b} onClick={() => navigate(`/booking/${b.id}`)} />)}
              </AnimatePresence>
            </motion.div>
            {list.length === 0 && (
              <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ textAlign: 'center', padding: '56px 20px' }}>
                <CalendarCheck size={32} color="#ddd" strokeWidth={1.5} />
                <p style={{ fontSize: 14, color: '#999', margin: '14px 0 20px' }}>
                  {tab === 'upcoming' ? 'No upcoming bookings yet.' : 'No past bookings.'}
                </p>
                <motion.button onClick={() => navigate('/browse')} {...buttonPress} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px',
                  background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
                  fontSize: 13, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>
                  <Search size={15} strokeWidth={1.5} /> Find a helper
                </motion.button>
              </motion.div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </Shell>
  )
}
