/**
 * Beam payment sheet — the client picks how to pay the chosen helper.
 *
 * Single-market (US) build: cash on completion is the only method for now (Stripe online checkout
 * isn't wired yet). Methods come from paymentMethods() in utils/region.js — the server re-validates
 * the chosen method regardless of what's offered here. Amounts format via the market-aware money()
 * helper.
 */
import { useState, useEffect, useRef } from 'react'
import { motion as Motion } from 'framer-motion'
import { money } from '../utils/money'
import { paymentMethods } from '../utils/region'
import { DURATION, EASE, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const ORANGE = '#1F6F5C'

// Backdrop fade + panel slide-up-and-settle — mirrors the feel of the app's CSS
// `slideUp 0.3s ease-out` keyframe (see index.css / InfoModal) but done with
// framer-motion so the sheet can also animate back OUT on close, not just pop away.
const backdropVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, transition: { duration: DURATION.fast, ease: EASE } },
}
const panelVariants = {
  hidden: { opacity: 0, y: '100%' },
  show: { opacity: 1, y: 0, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, y: '100%', transition: { duration: DURATION.fast, ease: EASE } },
}

export default function BeamPaySheet({ amount, t, busy, onConfirm, onClose }) {
  // Region-derived: currently cash-on-completion only (Stripe checkout not
  // wired). The server re-validates the chosen method regardless.
  const methods = paymentMethods({ cod: t.pay_cod, codSub: t.cod_sub })
  const [method, setMethod] = useState(methods[0].id)
  const panelRef = useRef(null)

  // Dialog semantics: focus lands in the sheet, Escape closes (unless mid-payment).
  useEffect(() => {
    const prev = document.activeElement
    panelRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (prev && prev.focus) prev.focus()
    }
  }, [busy, onClose])

  return (
    <Motion.div
      variants={backdropVariants} initial="hidden" animate="show" exit="exit"
      onClick={() => !busy && onClose()} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'flex-end', justifyContent: 'center', zIndex: 50,
    }}>
      <Motion.div ref={panelRef} role="dialog" aria-modal="true" aria-label={t.pay_choose}
        variants={panelVariants}
        tabIndex={-1} onClick={(e) => e.stopPropagation()} style={{
        background: '#FEFDFB', width: '100%', maxWidth: 460,
        padding: '22px 20px 26px', borderTop: `2px solid ${ORANGE}`, outline: 'none',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
          <p style={{ fontSize: 11, letterSpacing: 2, color: '#999', textTransform: 'uppercase', margin: 0 }}>{t.payment}</p>
          {amount != null && <span style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a' }}>{money(amount)}</span>}
        </div>
        <h2 style={{ fontFamily: SERIF, fontSize: 22, fontWeight: 400, color: '#1a1a1a', margin: '0 0 14px' }}>{t.pay_choose}</h2>

        <div role="radiogroup" aria-label={t.payment} style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
          {methods.map((m) => {
            const sel = m.id === method
            return (
              <Motion.button key={m.id} role="radio" aria-checked={sel} onClick={() => setMethod(m.id)}
                whileHover={{ scale: 1.01 }} whileTap={tapScale} style={{
                display: 'flex', alignItems: 'center', gap: 10, textAlign: 'left', padding: '12px 14px',
                cursor: 'pointer', background: '#fff', border: `1px solid ${sel ? ORANGE : '#e5e5e5'}`,
                transition: 'border-color 0.2s ease',
              }}>
                <span style={{
                  width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                  border: `1px solid ${sel ? ORANGE : '#bbb'}`, background: sel ? ORANGE : '#fff',
                  boxShadow: sel ? 'inset 0 0 0 3px #fff' : 'none',
                  transition: 'border-color 0.2s ease, background 0.2s ease',
                }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 15, color: '#1a1a1a', fontWeight: 500 }}>{m.label}</span>
                  {m.sub && <span style={{ display: 'block', fontSize: 12, color: '#999', marginTop: 1 }}>{m.sub}</span>}
                </span>
              </Motion.button>
            )
          })}
        </div>

        <Motion.button onClick={() => onConfirm(method)} disabled={busy}
          whileHover={busy ? {} : { scale: 1.02 }} whileTap={busy ? {} : tapScale} style={{
          width: '100%', padding: '13px 0', background: ORANGE, color: '#fff', border: 'none',
          cursor: busy ? 'default' : 'pointer', fontSize: 14, letterSpacing: 1,
          textTransform: 'uppercase', fontWeight: 600, opacity: busy ? 0.7 : 1,
        }}>{t.place_order}</Motion.button>
        <Motion.button onClick={onClose} disabled={busy} whileTap={busy ? {} : tapScale} style={{
          width: '100%', marginTop: 8, background: 'none', border: 'none',
          cursor: busy ? 'default' : 'pointer', fontSize: 13, color: '#999', padding: '6px 0',
        }}>{t.beam_back}</Motion.button>
      </Motion.div>
    </Motion.div>
  )
}
