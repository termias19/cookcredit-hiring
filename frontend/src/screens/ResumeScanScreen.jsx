/**
 * Resume scanner (helper-facing) — the centerpiece. Drop or paste a resume; key-points extract
 * INSTANTLY (real taxonomy trie pass on the actual text — no submit click), render as editable
 * confirm-chips, reconcile against the camera-verified score, and show which open roles you match.
 *
 * Tonight this runs fully client-side on the bundled taxonomy (genuine extraction, not faked).
 * The two-phase design (instant client preview → server-accurate refine) is documented in
 * ELITE_B2B_DESIGN.md; the server /api/resume/parse drops in behind the same key-point shape.
 */
import { useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, X, Plus, ShieldCheck, CircleAlert, ArrowLeft, Check } from 'lucide-react'
import Shell from '../components/Shell'
import { NODES, scanText, labelOf } from '../data/culinaryTaxonomy'
import { matchRole, reconcileClaims } from '../utils/match'
import { ROLES_SEED } from '../data/businessMock'
import { useAuth } from '../context/AuthContext'
import { parseResume } from '../utils/Api'
import { fadeUp, scaleIn, staggerContainer, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C', GOLD = '#C9A227', TERRA = '#C4561F'

const SAMPLE = `Housekeeper and household helper, 6 years across multiple households in Atlanta. Strong cleaning technique — bathroom sanitizing, kitchen cleaning, window washing. Background check certification; cpr certified. Experience with companion care and errands. Comfortable with pet care and childcare. Full-time availability for busy families.`

// A helper's own verified score (mock) drives the claim-vs-truth reconciliation.
const MY_VERIFIED = 88

const CAT_ORDER = ['technique', 'cuisine', 'certification', 'station', 'food_safety']
const CAT_LABEL = { technique: 'Techniques', cuisine: 'Service specialties', certification: 'Certifications', station: 'Experience & work arrangement', food_safety: 'Safety & protocol' }

export default function ResumeScanScreen() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [text, setText] = useState(SAMPLE)
  const [removed, setRemoved] = useState(new Set())   // chip IDs the helper removed (correction)
  const [added, setAdded] = useState([])              // chip IDs the helper added back
  const [refining, setRefining] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [fileMsg, setFileMsg] = useState('')
  const [saveState, setSaveState] = useState('idle')  // idle | saving | saved | signin | error
  const fileRef = useRef(null)

  // Real extraction (taxonomy trie pass) — fast in-memory, so compute live on every change.
  const scanned = useMemo(() => scanText(text), [text])

  const points = useMemo(() => {
    const base = scanned.filter(p => !removed.has(p.canonical_id))
    const extra = added.filter(id => !base.some(p => p.canonical_id === id) && !removed.has(id))
      .map(id => ({ canonical_id: id, label: labelOf(id), category: NODES.find(n => n.id === id)?.category, confidence: 1, manual: true }))
    return [...base, ...extra]
  }, [scanned, removed, added])

  const cook = useMemo(() => ({ verifiedScore: MY_VERIFIED, resumePoints: points.map(p => p.canonical_id) }), [points])
  const claims = reconcileClaims(cook)
  const roleMatches = useMemo(
    () => ROLES_SEED.map(r => ({ role: r, m: matchRole(cook, r) })).sort((a, b) => b.m.total - a.m.total),
    [cook]
  )

  function onFile(file) {
    if (!file) return
    const isText = file.type === 'text/plain' || (file.name || '').toLowerCase().endsWith('.txt')
    if (isText) {
      setRefining(true); setFileMsg('')
      file.text().then(t => { setText(t.slice(0, 8000)); setRefining(false) })
    } else {
      // We don't parse PDF/Word in the browser — that's the server's job (/api/resume/parse). Be
      // honest rather than silently substituting demo text: ask for pasted text for the preview.
      setFileMsg('PDF and Word résumés are read on the server. For the instant preview here, paste your résumé text below.')
    }
  }

  async function saveToProfile() {
    if (saveState === 'saving') return
    setSaveState('saving')
    try {
      const token = await user?.getIdToken?.()
      if (!token) { setSaveState('signin'); return }
      // Persist the de-identified key-points so this résumé shows on the helper's candidate card. The
      // server re-parses the text authoritatively and stores POINTS ONLY — never the raw résumé.
      await parseResume({ token, text })
      setSaveState('saved')
    } catch { setSaveState('error') }
  }

  const addable = NODES.filter(n => !points.some(p => p.canonical_id === n.id))

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '14px 20px' }}>
      <button onClick={() => navigate('/profile')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
        <ArrowLeft size={14} color="#999" strokeWidth={1.5} />
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>Profile</span>
      </button>
      <h1 style={{ fontFamily: SERIF, fontSize: 28, fontWeight: 400, color: '#1a1a1a', margin: 0 }}>Resume scanner</h1>
      <p style={{ fontSize: 13, color: '#777', margin: '4px 0 0' }}>Drop your resume — we pull out your skills and show the roles you fit. Nothing to submit.</p>
    </div>
  )

  return (
    <Shell header={header} showNav={false}>
      <div style={{ padding: '18px 20px 32px' }}>
        {/* drop zone */}
        <motion.div
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]) }}
          onClick={() => fileRef.current?.click()}
          whileHover={{ borderColor: GREEN, backgroundColor: '#FBF3EC' }}
          whileTap={tapScale}
          transition={{ duration: 0.18 }}
          style={{ border: '1px dashed #cfcabf', background: '#FBFAF7', padding: '22px 16px', textAlign: 'center', cursor: 'pointer' }}>
          <UploadCloud size={24} color="#999" strokeWidth={1.5} />
          <div style={{ fontSize: 13, color: '#555', marginTop: 8 }}>Drop a résumé or <span style={{ color: GREEN, borderBottom: `1px solid ${GREEN}` }}>choose a file</span> <span style={{ color: '#aaa' }}>· .txt previews instantly; PDF/Word are read on the server</span></div>
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt" hidden
            onChange={e => onFile(e.target.files?.[0])} aria-label="Upload resume" />
        </motion.div>
        {fileMsg && <p style={{ fontSize: 12, color: '#C4561F', margin: '8px 0 0' }}>{fileMsg}</p>}

        {/* paste fallback — genuinely live extraction */}
        <textarea value={text} onChange={e => setText(e.target.value)} rows={4} aria-label="Resume text"
          placeholder="…or paste your resume text here"
          style={{ width: '100%', marginTop: 10, padding: '10px 12px', border: '1px solid #e5e5e5', fontSize: 13,
            color: '#1a1a1a', resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.5 }} />

        {/* extracted key-points, editable */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', margin: '20px 0 10px' }}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: '#999', textTransform: 'uppercase', margin: 0 }}>
            What we found{refining ? ' · refining…' : ` · ${points.length}`}
          </p>
          <button onClick={() => setShowAdd(s => !s)} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: GREEN }}>
            <Plus size={13} strokeWidth={1.5} /> Add
          </button>
        </div>

        {CAT_ORDER.map(cat => {
          const inCat = points.filter(p => p.category === cat)
          if (!inCat.length) return null
          return (
            <motion.div key={cat} layout variants={fadeUp} initial="hidden" animate="show" style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, letterSpacing: 1.5, color: '#bbb', textTransform: 'uppercase', marginBottom: 6 }}>{CAT_LABEL[cat]}</div>
              <motion.div variants={staggerContainer(0.04)} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <AnimatePresence initial={false}>
                  {inCat.map(p => (
                    <motion.span key={p.canonical_id} layout variants={scaleIn} initial="hidden" animate="show"
                      exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.15 } }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid #e5e5e5', background: '#fff', padding: '5px 8px 5px 10px', fontSize: 12, color: '#1a1a1a', opacity: refining ? 0.5 : 1, transition: 'opacity .2s' }}>
                      {p.label}
                      <motion.button whileTap={tapScale} onClick={() => { setRemoved(s => new Set(s).add(p.canonical_id)); setAdded(a => a.filter(x => x !== p.canonical_id)) }}
                        aria-label={`Remove ${p.label}`} style={{ display: 'inline-flex', background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#bbb' }}>
                        <X size={12} strokeWidth={2} />
                      </motion.button>
                    </motion.span>
                  ))}
                </AnimatePresence>
              </motion.div>
            </motion.div>
          )
        })}

        {showAdd && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} transition={{ duration: 0.2 }}
            style={{ border: '1px solid #e5e5e5', padding: 10, margin: '6px 0 4px', maxHeight: 160, overflowY: 'auto' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {addable.slice(0, 30).map(n => (
                <motion.button key={n.id} whileHover={{ borderColor: GREEN, color: GREEN }} whileTap={tapScale}
                  onClick={() => { setAdded(a => [...a, n.id]); setRemoved(s => { const x = new Set(s); x.delete(n.id); return x }) }}
                  style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '4px 9px', fontSize: 12, color: '#555', cursor: 'pointer' }}>+ {n.label}</motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* persist the confirmed key-points → this résumé then appears on the helper's candidate card */}
        <motion.button onClick={saveToProfile} disabled={saveState === 'saving' || !points.length}
          whileHover={points.length && saveState !== 'saving' && saveState !== 'saved' ? { scale: 1.01 } : undefined}
          whileTap={points.length && saveState !== 'saving' ? tapScale : undefined}
          animate={saveState === 'saved' ? { scale: [1, 1.03, 1] } : { scale: 1 }}
          transition={{ duration: 0.3 }}
          style={{ width: '100%', marginTop: 16, padding: 12,
            border: saveState === 'saved' ? `1px solid ${GREEN}` : 'none',
            background: saveState === 'saved' ? '#E8F1EC' : points.length ? '#1a1a1a' : '#e5e5e5',
            color: saveState === 'saved' ? GREEN : points.length ? '#fff' : '#999',
            fontSize: 14, fontWeight: 500, letterSpacing: 0.5,
            cursor: points.length && saveState !== 'saving' ? 'pointer' : 'default',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <AnimatePresence mode="wait" initial={false}>
            {saveState === 'saving' ? (
              <motion.span key="saving" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>Saving…</motion.span>
            ) : saveState === 'saved' ? (
              <motion.span key="saved" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <Check size={15} strokeWidth={2} /> Saved to your profile
              </motion.span>
            ) : (
              <motion.span key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>Save résumé to my profile</motion.span>
            )}
          </AnimatePresence>
        </motion.button>
        {saveState === 'signin' && <p style={{ fontSize: 12, color: TERRA, margin: '8px 0 0' }}>Sign in to save your résumé to your profile.</p>}
        {saveState === 'error' && <p style={{ fontSize: 12, color: TERRA, margin: '8px 0 0' }}>Could not save — check your connection and try again.</p>}

        {/* claim vs camera truth */}
        <AnimatePresence>
          {claims.length > 0 && (
            <motion.div key={claims[0].status} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
              style={{ border: `1px solid ${claims[0].status === 'contradicted' ? TERRA : GREEN}`, background: claims[0].status === 'contradicted' ? '#FBF1EC' : '#E8F1EC', padding: '12px 14px', marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {claims[0].status === 'verified'
                  ? <ShieldCheck size={16} color={GREEN} strokeWidth={2} />
                  : <CircleAlert size={16} color={claims[0].status === 'contradicted' ? TERRA : GOLD} strokeWidth={2} />}
                <span style={{ fontSize: 13, color: '#1a1a1a', fontWeight: 500 }}>
                  {claims[0].status === 'verified' ? 'Your skill claim is camera-verified'
                    : claims[0].status === 'partial' ? 'Skill claim partly backed by your camera score'
                    : 'Your skill claim is not backed by your camera score'}
                </span>
              </div>
              <p style={{ fontSize: 12, color: '#777', margin: '6px 0 0' }}>
                {claims[0].detail} — the verified score is the part employers trust most. {claims[0].status !== 'verified' && 'Re-take the skill test to raise it.'}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* roles you match */}
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#999', textTransform: 'uppercase', margin: '22px 0 10px' }}>Roles you match</p>
        <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show">
          {roleMatches.map(({ role, m }) => (
            <motion.div key={role.id} layout variants={fadeUp} initial="hidden" animate="show" whileHover={hoverLift} style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '12px 14px', marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontFamily: SERIF, fontSize: 17, color: '#1a1a1a' }}>{role.title}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: m.band === 'Gated' ? TERRA : m.total >= 0.6 ? GREEN : GOLD }}>
                  {m.band === 'Gated' ? 'Not eligible' : m.band}
                </span>
              </div>
              <div style={{ height: 4, background: '#e5e5e5', margin: '8px 0 6px' }}>
                <motion.i initial={{ width: 0 }} animate={{ width: `${m.percent}%` }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  style={{ display: 'block', height: '100%', background: m.band === 'Gated' ? TERRA : '#1a1a1a' }} />
              </div>
              <div style={{ fontSize: 11, color: '#999' }}>
                {m.gates.passed ? `${m.reqMet}/${m.reqTotal} requirements met` : `Missing: ${m.gates.failures.join(', ')}`}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </Shell>
  )
}
