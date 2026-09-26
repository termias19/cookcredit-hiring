/**
 * Beam — a client broadcasts a task to verified helpers in their city.
 *
 * Optional photo (camera on mobile), a short description, and a nearby|city-wide scope. On send,
 * approved helpers in the city are notified and the client is taken to the responders screen. Below
 * the composer: the client's recent beams, so they can re-open one and pick a helper.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import { Send, Camera, X, Sparkles } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import { useNotifications } from '../context/NotificationContext'
import { auth } from '../firebase'
import { createBeam, uploadCravingPhoto, getMyBeams, beamAgentChat } from '../utils/Api'
import { fadeUp, staggerContainer, listItem, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

function Header({ t }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 24px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>{t.beam_title}</h1>
      </div>
    </div>
  )
}

export default function BeamScreen() {
  const navigate = useNavigate()
  const { profile } = useAuth()
  const { t, lang } = useLang()
  const { refresh } = useNotifications()

  const defaultCity = profile?.eaterProfile?.addressCity || ''
  const [taskText, setTaskText] = useState('')
  const [scope, setScope] = useState('citywide')
  // Empty until the client types; the input falls back to their saved city (which may load
  // after first render). Deriving it avoids a setState-in-effect just to backfill the default.
  const [city, setCity] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [mine, setMine] = useState([])
  const [mineStatus, setMineStatus] = useState('loading')   // loading | ready | error

  // ── beam assistant (AI concierge) ──
  const [aiOpen, setAiOpen] = useState(false)
  const [aiMsgs, setAiMsgs] = useState([])      // [{role: 'user'|'assistant', content}]
  const [aiInput, setAiInput] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const [aiErr, setAiErr] = useState('')
  const [aiNote, setAiNote] = useState('')
  const [aiGone, setAiGone] = useState(false)   // backend has no agent configured -> hide
  const aiThreadRef = useRef(null)

  async function aiSend() {
    const text = aiInput.trim()
    if (!text || aiBusy) return
    const msgs = [...aiMsgs, { role: 'user', content: text }]
    setAiMsgs(msgs); setAiInput(''); setAiBusy(true); setAiErr(''); setAiNote('')
    try {
      const d = await beamAgentChat({ auth, messages: msgs, city: city || defaultCity, lang })
      if (d && typeof d.reply === 'string') {
        setAiMsgs([...msgs, { role: 'assistant', content: d.reply }])
        if (d.draft) {
          // The agent drafted the beam — prefill the composer; the human reviews and sends.
          setTaskText(d.draft.craving_text)
          setCity(d.draft.city)
          setScope(d.draft.scope)
          setAiNote(t.beam_ai_filled)
        }
      } else if (d?.error) {
        // 503 = agent not configured on this deployment -> hide the panel.
        if (/unavailable/i.test(d.error)) { setAiGone(true) } else { setAiErr(d.error) }
      } else {
        setAiErr(t.beam_ai_unavailable)
      }
    } catch (e) {
      setAiErr(e?.message || t.beam_ai_unavailable)
    } finally {
      setAiBusy(false)
      requestAnimationFrame(() => {
        const el = aiThreadRef.current
        if (el) el.scrollTop = el.scrollHeight
      })
    }
  }

  const loadMine = useCallback(() => {
    getMyBeams({ auth, page: 1 })
      .then(d => { setMine(Array.isArray(d?.beams) ? d.beams : []); setMineStatus('ready') })
      .catch(() => setMineStatus('error'))
  }, [])
  useEffect(() => { loadMine() }, [loadMine])
  const retryMine = () => { setMineStatus('loading'); loadMine() }

  function pickPhoto(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }
  function clearPhoto() {
    setFile(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
  }

  async function send() {
    const text = taskText.trim()
    if (!text) { setError(t.beam_required); return }
    const cityVal = (city || defaultCity).trim()
    if (!cityVal) { setError(t.beam_need_city); return }
    setSending(true); setError('')
    try {
      let photoUrl
      if (file) {
        const up = await uploadCravingPhoto({ auth, file })
        photoUrl = up?.url
      }
      const res = await createBeam({ auth, cravingText: text, scope, city: cityVal, photoUrl })
      refresh()
      const id = res?.beam?.id
      if (id) navigate(`/beam/${id}/responses`)
      else { loadMine(); setTaskText(''); clearPhoto() }
    } catch (err) {
      setError(err?.message || 'Could not send your beam. Please try again.')
    } finally {
      setSending(false)
    }
  }

  const STATUS = {
    open: t.beam_status_open, fulfilled: t.beam_status_fulfilled,
    expired: t.beam_status_expired, cancelled: t.beam_status_cancelled,
  }

  return (
    <Shell wide header={<Header t={t} />}>
      <div style={{ padding: '24px 0 40px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        {/* Beam assistant — conversational agent that drafts the beam; the human
            reviews the prefilled composer and presses Send. Hidden entirely when
            the backend reports the agent isn't configured (503). */}
        {!aiGone && (
          <div style={{ border: '1px solid #e5e5e5', background: '#fff', marginBottom: 18 }}>
            <button onClick={() => setAiOpen(o => !o)} style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
              background: 'none', border: 'none', padding: '12px 14px', cursor: 'pointer',
            }}>
              <Sparkles size={16} color="#1F6F5C" strokeWidth={1.5} />
              <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: '#1a1a1a' }}>{t.beam_ai_title}</span>
              <span style={{ fontSize: 12, color: '#999' }}>{aiOpen ? '—' : t.beam_ai_open}</span>
            </button>
            <AnimatePresence initial={false}>
              {aiOpen && (
                <Motion.div
                  key="ai-panel"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                  style={{ overflow: 'hidden' }}
                >
                  <div style={{ borderTop: '1px solid #f0f0f0', padding: '12px 14px' }}>
                    {aiMsgs.length === 0 && (
                      <p style={{ fontSize: 13, color: '#777', margin: '0 0 10px', lineHeight: 1.5 }}>{t.beam_ai_hint}</p>
                    )}
                    <div ref={aiThreadRef} style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {aiMsgs.map((m, i) => (
                        <div key={i} style={{
                          alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%',
                          background: m.role === 'user' ? '#1a1a1a' : '#F5F1EA',
                          color: m.role === 'user' ? '#fff' : '#1a1a1a',
                          padding: '8px 12px', fontSize: 14, lineHeight: 1.5,
                        }}>{m.content}</div>
                      ))}
                      {aiBusy && <div style={{ alignSelf: 'flex-start', color: '#999', fontSize: 13 }}>…</div>}
                    </div>
                    {aiNote && <p style={{ fontSize: 13, color: '#2E7D32', margin: '10px 0 0' }}>{aiNote}</p>}
                    {aiErr && <p style={{ fontSize: 13, color: '#B3261E', margin: '10px 0 0' }}>{aiErr}</p>}
                    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                      <input value={aiInput} onChange={e => setAiInput(e.target.value)} maxLength={2000}
                        placeholder={t.beam_ai_ph}
                        onKeyDown={e => e.key === 'Enter' && aiSend()}
                        style={{ flex: 1, border: '1px solid #e5e5e5', padding: '10px 12px', fontSize: 14, color: '#1a1a1a', outline: 'none' }} />
                      <Motion.button onClick={aiSend} disabled={aiBusy || !aiInput.trim()}
                        whileHover={aiBusy || !aiInput.trim() ? {} : { scale: 1.02 }}
                        whileTap={aiBusy || !aiInput.trim() ? {} : tapScale}
                        style={{
                        padding: '10px 18px', background: '#1a1a1a', color: '#fff', border: 'none',
                        fontSize: 13, fontWeight: 600, letterSpacing: 0.5, cursor: aiBusy ? 'default' : 'pointer',
                        opacity: aiBusy || !aiInput.trim() ? 0.6 : 1,
                      }}>{t.beam_ai_send}</Motion.button>
                    </div>
                  </div>
                </Motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        <Motion.div variants={fadeUp} initial="hidden" animate="show">
          <label style={{ display: 'block', fontSize: 12, letterSpacing: 1, textTransform: 'uppercase', color: '#999', margin: '0 0 8px' }}>{t.beam_what}</label>
          <textarea value={taskText} onChange={e => setTaskText(e.target.value)} maxLength={500} rows={3} placeholder={t.beam_what_ph}
            style={{ width: '100%', border: '1px solid #e5e5e5', background: '#fff', padding: 12, fontSize: 15, color: '#1a1a1a', resize: 'vertical', outline: 'none' }} />

          <div style={{ display: 'flex', gap: 8, margin: '14px 0 0' }}>
            {[['citywide', t.beam_scope_citywide], ['nearby', t.beam_scope_nearby]].map(([val, lbl]) => (
              <Motion.button key={val} onClick={() => setScope(val)} whileTap={tapScale} style={{
                flex: 1, padding: '10px 0', fontSize: 13, letterSpacing: 0.5, cursor: 'pointer',
                border: '1px solid', borderColor: scope === val ? '#1a1a1a' : '#e5e5e5',
                background: scope === val ? '#1a1a1a' : '#fff', color: scope === val ? '#fff' : '#555',
              }}>{lbl}</Motion.button>
            ))}
          </div>

          <label style={{ display: 'block', fontSize: 12, letterSpacing: 1, textTransform: 'uppercase', color: '#999', margin: '16px 0 8px' }}>{t.beam_city}</label>
          <input value={city || defaultCity} onChange={e => setCity(e.target.value)} maxLength={120}
            style={{ width: '100%', border: '1px solid #e5e5e5', background: '#fff', padding: '10px 12px', fontSize: 15, color: '#1a1a1a', outline: 'none' }} />

          <div style={{ margin: '16px 0 0' }}>
            {preview ? (
              <Motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.22 }} style={{ position: 'relative', width: '100%' }}>
                <img src={preview} alt="" style={{ width: '100%', maxHeight: 240, objectFit: 'cover', border: '1px solid #e5e5e5' }} />
                <Motion.button onClick={clearPhoto} aria-label={t.beam_photo_remove} whileHover={{ scale: 1.08 }} whileTap={tapScale} style={{
                  position: 'absolute', top: 8, right: 8, width: 30, height: 30, background: 'rgba(0,0,0,0.6)',
                  border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}><X size={16} /></Motion.button>
              </Motion.div>
            ) : (
              <label style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                border: '1px dashed #ccc', background: '#fff', padding: '14px 0', cursor: 'pointer', fontSize: 13, color: '#777',
              }}>
                <Camera size={18} strokeWidth={1.5} /> {t.beam_photo}
                <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={pickPhoto} style={{ display: 'none' }} />
              </label>
            )}
          </div>

          {error && <p style={{ color: '#D32F2F', fontSize: 13, margin: '12px 0 0' }}>{error}</p>}

          <Motion.button onClick={send} disabled={sending}
            whileHover={sending ? {} : { scale: 1.02 }}
            whileTap={sending ? {} : tapScale}
            animate={sending ? { scale: [1, 1.045, 1] } : { scale: 1 }}
            transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
            style={{
            width: '100%', marginTop: 18, padding: '14px 0', background: sending ? '#888' : '#1a1a1a',
            color: '#fff', border: 'none', cursor: sending ? 'default' : 'pointer',
            fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
            <Send size={16} strokeWidth={1.5} /> {sending ? t.beam_sending : t.beam_send}
          </Motion.button>
          <p style={{ fontSize: 12, color: '#999', margin: '8px 0 0', textAlign: 'center' }}>{t.beam_send_hint}</p>
        </Motion.div>
      </div>

        <h2 style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 400, color: '#1a1a1a', margin: '28px 0 12px' }}>{t.beam_your_beams}</h2>
        {mineStatus === 'loading' ? (
          <p style={{ fontSize: 13, color: '#999', margin: 0 }}>…</p>
        ) : mineStatus === 'error' ? (
          <div>
            <p style={{ fontSize: 13, color: '#777', margin: '0 0 10px' }}>{t.beam_mine_error}</p>
            <button onClick={retryMine} style={{
              background: '#1a1a1a', color: '#fff', border: 'none', padding: '10px 20px',
              fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', cursor: 'pointer',
            }}>{t.load_retry}</button>
          </div>
        ) : mine.length === 0 ? (
          <p style={{ fontSize: 13, color: '#999', margin: 0 }}>{t.beam_empty_mine}</p>
        ) : (
          <Motion.div variants={staggerContainer()} initial="hidden" animate="show"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
            {mine.map(b => (
              <Motion.button key={b.id} onClick={() => navigate(`/beam/${b.id}/responses`)}
                variants={listItem} whileHover={hoverLift} whileTap={tapScale} style={{
                display: 'block', textAlign: 'left', cursor: 'pointer',
                background: '#fff', border: '1px solid #e5e5e5', padding: 14,
              }}>
                <p style={{ fontSize: 14, color: '#1a1a1a', margin: '0 0 6px', lineHeight: 1.4,
                  display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{b.cravingText}</p>
                <p style={{ fontSize: 11, letterSpacing: 0.5, color: '#999', margin: 0 }}>
                  {STATUS[b.status] || b.status}{b.responseCount ? ` · ${b.responseCount}` : ''}
                </p>
              </Motion.button>
            ))}
          </Motion.div>
        )}
      </div>
    </Shell>
  )
}
