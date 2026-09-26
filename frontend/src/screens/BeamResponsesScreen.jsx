/**
 * Beam responders — the client reviews helpers who responded and picks one.
 *
 * Polls for new responders while the beam is open. On pick, the beam is fulfilled and the client
 * is linked to the chosen helper's public profile. Prices format via the market-aware money() helper.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import { ShieldCheck, MapPin, Check } from 'lucide-react'
import Shell from '../components/Shell'
import BeamPaySheet from '../components/BeamPaySheet'
import { useLang } from '../context/LangContext'
import { useNotifications } from '../context/NotificationContext'
import { auth } from '../firebase'
import { money } from '../utils/money'
import { tierColor } from '../utils/region'
import { getBeamResponses, chooseResponder, cancelBeam, payOrder, verifyOrder } from '../utils/Api'
import { EASE, fadeUp, scaleIn, staggerContainer, listItem, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

export default function BeamResponsesScreen() {
  const { beamId } = useParams()
  const navigate = useNavigate()
  const { t } = useLang()
  const { refresh } = useNotifications()
  const [beam, setBeam] = useState(null)
  const [responses, setResponses] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [busy, setBusy] = useState(false)
  const [payingFor, setPayingFor] = useState(null) // the responder card being paid for
  const [payNote, setPayNote] = useState(null)      // post-payment / cash-on-delivery banner
  const [searchParams, setSearchParams] = useSearchParams()
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const d = await getBeamResponses({ auth, id: beamId })
      setBeam(d?.beam || null)
      setResponses(Array.isArray(d?.responses) ? d.responses : [])
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [beamId])

  useEffect(() => { load() }, [load])

  // Poll while the beam is still open and accepting responders.
  useEffect(() => {
    if (!beam || beam.status !== 'open') return
    pollRef.current = setInterval(load, 10000)
    return () => clearInterval(pollRef.current)
  }, [beam, load])

  // Returning from Chapa's hosted checkout (?order=<id>) -> verify once and surface the result.
  useEffect(() => {
    const orderId = searchParams.get('order')
    if (!orderId) return
    ;(async () => {
      try {
        const res = await verifyOrder({ auth, orderId })
        setPayNote(res?.paid ? t.pay_confirmed : t.pay_pending)
      } catch { setPayNote(t.pay_pending) }
      searchParams.delete('order')
      setSearchParams(searchParams, { replace: true })
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Confirm the pick with the chosen payment method. Cash-on-delivery just records the order;
  // online methods (telebirr / Chapa / CBE Birr) create the order then redirect to Chapa checkout.
  async function confirmPay(method) {
    if (!payingFor) return
    setBusy(true)
    try {
      const res = await chooseResponder({ auth, beamId, responseId: payingFor.responseId, paymentMethod: method })
      const order = res?.order
      if (order && method !== 'cod') {
        const pay = await payOrder({ auth, orderId: order.id })
        if (pay?.checkoutUrl) { window.location.href = pay.checkoutUrl; return }
        setPayNote(t.pay_pending)
      } else if (method === 'cod') {
        setPayNote(t.cod_placed)
      }
      setPayingFor(null)
      refresh()
      await load()
    } catch {
      setPayNote(t.pay_failed)
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    setBusy(true)
    try { await cancelBeam({ auth, id: beamId }); refresh(); await load() }
    catch { /* ignore */ } finally { setBusy(false) }
  }

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 24px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <button onClick={() => navigate('/beam')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 13, color: '#777' }}>{t.beam_back}</button>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(26px, 4vw, 34px)', fontWeight: 400, color: '#1a1a1a', margin: '8px 0 0' }}>{t.beam_responses_title}</h1>
      </div>
    </div>
  )

  const chosen = responses.find(r => r.status === 'chosen')

  return (
    <Shell wide header={header}>
      <div style={{ padding: '24px 0 40px' }}>
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
        {beam && (
          <Motion.div variants={fadeUp} initial="hidden" animate="show"
            style={{ border: '1px solid #e5e5e5', background: '#fff', padding: 14, marginBottom: 16 }}>
            {beam.photoUrl && <img src={beam.photoUrl} alt="Task photo" loading="lazy" style={{ width: '100%', maxHeight: 180, objectFit: 'cover', marginBottom: 10 }} />}
            <p style={{ fontSize: 15, color: '#1a1a1a', margin: '0 0 6px' }}>{beam.cravingText}</p>
            <p style={{ fontSize: 11, letterSpacing: 0.5, color: '#999', margin: 0 }}>
              {[beam.city, beam.scope === 'nearby' ? t.beam_scope_nearby : t.beam_scope_citywide].filter(Boolean).join(' · ')}
            </p>
          </Motion.div>
        )}

        {payNote && (
          <Motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: EASE }}
            style={{ border: '1px solid #1F6F5C', background: '#FFF7F0', padding: '10px 14px', marginBottom: 14, fontSize: 13, color: '#7a4a1f' }}>{payNote}</Motion.div>
        )}

        {status === 'loading' ? (
          <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '30px 0' }}>{t.beam_waiting}</p>
        ) : status === 'error' ? (
          <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '30px 0' }}>Could not load. Pull to refresh.</p>
        ) : chosen ? (
          <Motion.div variants={scaleIn} initial="hidden" animate="show" style={{ textAlign: 'center', padding: '8px 0 0' }}>
            <p style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a', margin: '0 0 6px' }}>{t.beam_picked} {chosen.name}</p>
            <Motion.button onClick={() => navigate(`/cook/${chosen.cookId}`)} whileHover={{ scale: 1.02 }} whileTap={tapScale} style={{
              marginTop: 10, padding: '12px 22px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer',
              fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
            }}>{t.beam_connected}</Motion.button>
          </Motion.div>
        ) : responses.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '36px 16px' }}>
            <p style={{ fontSize: 14, color: '#999', margin: 0 }}>
              {beam?.matchedCount === 0 ? t.beam_none_matched : t.beam_waiting}
            </p>
            {beam?.status === 'open' && (
              <Motion.button onClick={cancel} disabled={busy} whileHover={{ scale: 1.02 }} whileTap={tapScale}
                style={{ marginTop: 18, background: 'none', border: '1px solid #e5e5e5', padding: '10px 18px', cursor: 'pointer', fontSize: 13, color: '#777' }}>{t.beam_cancel}</Motion.button>
            )}
          </div>
        ) : null}
        </div>

        {status !== 'loading' && status !== 'error' && !chosen && responses.length > 0 && (
          <>
            <Motion.div variants={staggerContainer()} initial="hidden" animate="show"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 20, marginTop: beam || payNote ? 20 : 0 }}>
              {responses.map(r => {
                const tc = tierColor(r.skillTier)
                const cityLine = [r.baseCity, r.baseState].filter(Boolean).join(', ')
                const picked = payingFor?.responseId === r.responseId
                return (
                  <Motion.div key={r.responseId} variants={listItem} whileHover={hoverLift}
                    style={{
                      position: 'relative', border: `1px solid ${picked ? '#1F6F5C' : '#e5e5e5'}`,
                      background: picked ? '#FFF9F3' : '#fff', padding: 14,
                      transition: 'border-color 0.22s ease, background 0.22s ease',
                    }}>
                    <AnimatePresence>
                      {picked && (
                        <Motion.div key="picked-badge" initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.5 }}
                          transition={{ duration: 0.22, ease: EASE }}
                          style={{
                            position: 'absolute', top: -10, right: -10, width: 26, height: 26, borderRadius: '50%',
                            background: '#1F6F5C', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}>
                          <Check size={14} color="#fff" strokeWidth={2.5} />
                        </Motion.div>
                      )}
                    </AnimatePresence>
                    <div style={{ display: 'flex', gap: 12 }}>
                      <div style={{ width: 56, height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: r.photoUrl ? `#eee url(${r.photoUrl}) center/cover` : '#EDE7DF' }}>
                        {!r.photoUrl && <span style={{ fontFamily: SERIF, fontSize: 22, color: '#9a8c7a' }}>{(r.name || '?').trim().charAt(0).toUpperCase()}</span>}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <h3 style={{ fontFamily: SERIF, fontSize: 18, fontWeight: 500, color: '#1a1a1a', margin: 0 }}>{r.name}</h3>
                          <ShieldCheck size={14} color={tc} strokeWidth={2} />
                        </div>
                        {cityLine && <div style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#999', margin: '2px 0 0' }}><MapPin size={12} strokeWidth={1.5} /> {cityLine}</div>}
                        {(r.cuisines || []).length > 0 && <p style={{ fontSize: 12, color: '#777', margin: '4px 0 0' }}>{r.cuisines.join(' · ')}</p>}
                      </div>
                      {r.price != null && <div style={{ fontFamily: SERIF, fontSize: 20, color: '#1a1a1a' }}>{money(r.price)}</div>}
                    </div>
                    {r.note && <p style={{ fontSize: 14, color: '#444', margin: '10px 0 0', lineHeight: 1.5 }}>{r.note}</p>}
                    <Motion.button onClick={() => setPayingFor(r)} disabled={busy} whileHover={busy ? {} : { scale: 1.02 }} whileTap={busy ? {} : tapScale} style={{
                      width: '100%', marginTop: 12, padding: '11px 0', background: '#1F6F5C', color: '#fff', border: 'none',
                      cursor: busy ? 'default' : 'pointer', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
                    }}>{t.beam_pick}</Motion.button>
                  </Motion.div>
                )
              })}
            </Motion.div>
            {beam?.status === 'open' && (
              <div style={{ maxWidth: 640, margin: '0 auto' }}>
                <Motion.button onClick={cancel} disabled={busy} whileHover={{ scale: 1.01 }} whileTap={tapScale}
                  style={{ width: '100%', marginTop: 16, background: 'none', border: '1px solid #e5e5e5', padding: '10px 0', cursor: 'pointer', fontSize: 13, color: '#777' }}>{t.beam_cancel}</Motion.button>
              </div>
            )}
          </>
        )}
      </div>

      <AnimatePresence>
        {payingFor && (
          <BeamPaySheet
            key="beam-pay-sheet"
            amount={payingFor.price}
            t={t}
            busy={busy}
            onConfirm={confirmPay}
            onClose={() => setPayingFor(null)}
          />
        )}
      </AnimatePresence>
    </Shell>
  )
}
