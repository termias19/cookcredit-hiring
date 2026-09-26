/**
 * Beam inbox (helper) — open task broadcasts in the helper's city.
 *
 * Respond with an optional note + price, or dismiss. Either action removes the beam from the list
 * (the recipient row leaves the 'pending' inbox state). Helper-only; reached via the Requests tab.
 */
import { useState, useEffect, useCallback } from 'react'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import Shell from '../components/Shell'
import { useLang } from '../context/LangContext'
import { useNotifications } from '../context/NotificationContext'
import { auth } from '../firebase'
import { getBeamInbox, respondToBeam, declineBeam } from '../utils/Api'
import { EASE, staggerContainer, listItem, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

// Cards leave to the left + fade + shrink slightly, whichever action removed them.
const cardExit = { opacity: 0, x: -32, scale: 0.98, transition: { duration: 0.22, ease: EASE } }

function Header({ t }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 24px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>{t.beam_inbox_title}</h1>
      </div>
    </div>
  )
}

function InboxCard({ beam, t, onDone }) {
  const [note, setNote] = useState('')
  const [price, setPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function respond() {
    setBusy(true); setErr('')
    try {
      await respondToBeam({
        auth, id: beam.id,
        note: note.trim() || undefined,
        price: price !== '' ? Number(price) : undefined,
      })
      onDone()
    } catch (e) {
      setErr(e?.message || t.beam_action_error)
      setBusy(false)
    }
  }
  async function dismiss() {
    setBusy(true); setErr('')
    try { await declineBeam({ auth, id: beam.id }); onDone() }
    catch (e) {
      setErr(e?.message || t.beam_action_error)
      setBusy(false)
    }
  }

  return (
    <Motion.div layout variants={listItem} initial="hidden" animate="show" exit={cardExit} whileHover={hoverLift}
      style={{ border: '1px solid #e5e5e5', background: '#fff', padding: 14 }}>
      {beam.photoUrl && <img src={beam.photoUrl} alt="Task photo" loading="lazy" style={{ width: '100%', maxHeight: 200, objectFit: 'cover', marginBottom: 10 }} />}
      <p style={{ fontSize: 15, color: '#1a1a1a', margin: '0 0 4px' }}>{beam.cravingText}</p>
      <p style={{ fontSize: 11, letterSpacing: 0.5, color: '#999', margin: '0 0 12px' }}>
        {[beam.city, beam.scope === 'nearby' ? t.beam_scope_nearby : t.beam_scope_citywide].filter(Boolean).join(' · ')}
      </p>
      <textarea value={note} onChange={e => setNote(e.target.value)} maxLength={500} rows={2} placeholder={t.beam_note_ph}
        style={{ width: '100%', border: '1px solid #e5e5e5', padding: 10, fontSize: 14, color: '#1a1a1a', resize: 'vertical', outline: 'none', marginBottom: 8 }} />
      <input value={price} onChange={e => setPrice(e.target.value.replace(/[^0-9.]/g, ''))} inputMode="decimal" placeholder={t.beam_price}
        style={{ width: '100%', border: '1px solid #e5e5e5', padding: '10px 12px', fontSize: 14, color: '#1a1a1a', outline: 'none', marginBottom: 10 }} />
      {err && <p style={{ fontSize: 13, color: '#B3261E', margin: '0 0 10px' }}>{err}</p>}
      <div style={{ display: 'flex', gap: 8 }}>
        <Motion.button onClick={dismiss} disabled={busy} whileHover={busy ? {} : { scale: 1.02 }} whileTap={busy ? {} : tapScale}
          style={{ flex: 1, padding: '11px 0', background: '#fff', border: '1px solid #e5e5e5', color: '#777', cursor: busy ? 'default' : 'pointer', fontSize: 14 }}>{t.beam_dismiss}</Motion.button>
        <Motion.button onClick={respond} disabled={busy} whileHover={busy ? {} : { scale: 1.02 }} whileTap={busy ? {} : tapScale}
          style={{ flex: 2, padding: '11px 0', background: '#1F6F5C', border: 'none', color: '#fff', cursor: busy ? 'default' : 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600 }}>{t.beam_respond}</Motion.button>
      </div>
    </Motion.div>
  )
}

export default function BeamInboxScreen() {
  const { t } = useLang()
  const { refresh } = useNotifications()
  const [beams, setBeams] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready | error

  const load = useCallback(() => {
    getBeamInbox({ auth, page: 1, perPage: 50 })
      .then(d => { setBeams(Array.isArray(d?.beams) ? d.beams : []); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])
  useEffect(() => { load() }, [load])

  function onDone(id) {
    setBeams(bs => bs.filter(b => b.id !== id))
    refresh()
  }

  return (
    <Shell wide header={<Header t={t} />}>
      <div style={{ padding: '24px 0 40px' }}>
        {status === 'loading' ? (
          <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '36px 0' }}>{t.beam_inbox_title}</p>
        ) : status === 'error' ? (
          <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '36px 0' }}>Could not load. Pull to refresh.</p>
        ) : beams.length === 0 ? (
          <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '40px 16px' }}>{t.beam_no_inbox}</p>
        ) : (
          <Motion.div variants={staggerContainer()} initial="hidden" animate="show"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 20 }}>
            <AnimatePresence>
              {beams.map(b => <InboxCard key={b.id} beam={b} t={t} onDone={() => onDone(b.id)} />)}
            </AnimatePresence>
          </Motion.div>
        )}
      </div>
    </Shell>
  )
}
