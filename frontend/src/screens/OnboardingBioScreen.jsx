/**
 * Helper onboarding — "Your story" (/onboarding/bio, showNav=false flow).
 *
 * Where someone decides to become a Mise helper: display name, bio, photo,
 * service specialties, extra skills, hourly rate, and service radius. A sticky
 * CTA carries them to identity verification (/skill) — an ID + on-camera
 * liveness check — which is what earns the verified tier. Local form state
 * only; POSTs to the cook-profile API later.
 */
import { useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Camera, Plus, X, ShieldCheck, ArrowRight } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { uploadPortfolioImage } from '../utils/Api'
import { money, cookPayout, currency, PLATFORM_FEE_PERCENT } from '../utils/money.js'
import { fadeUp, staggerContainer, listItem, tapScale, EASE } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const BIO_MAX = 280

const CUISINE_OPTIONS = [
  'House cleaning', 'Cooking & meal prep', 'Laundry & ironing', 'Childcare / nannying',
  'Elder & companion care', 'Errands & general household tasks', 'Deep cleaning', 'Organizing', 'Pet care',
]

function Header({ onBack }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#FEFDFB',
      borderBottom: '1px solid #eee', padding: '14px 16px' }}>
      <button onClick={onBack} aria-label="Back" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
        border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer' }}>
        <ArrowLeft size={18} strokeWidth={1.5} color="#1a1a1a" />
      </button>
      <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>
        Become a helper
      </span>
    </div>
  )
}

function FieldLabel({ children, htmlFor }) {
  return (
    <label htmlFor={htmlFor} style={{ display: 'block', fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 8px' }}>
      {children}
    </label>
  )
}

const inputStyle = {
  width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', background: '#fff',
  padding: '12px 14px', fontSize: 14, color: '#1a1a1a', outline: 'none', fontFamily: 'inherit',
}

export default function OnboardingBioScreen() {
  const navigate = useNavigate()
  const { updateProfile, user } = useAuth()
  const fileRef = useRef(null)
  const [photo, setPhoto] = useState(null)
  const [photoBusy, setPhotoBusy] = useState(false)

  async function handlePhoto(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoBusy(true)
    try {
      const res = await uploadPortfolioImage({ auth: { currentUser: user }, file })
      if (res?.url) { setPhoto(res.url); try { await updateProfile({ photoUrl: res.url }) } catch { /* avatar set on next load */ } }
    } catch { /* upload failed — leave the placeholder */ } finally {
      setPhotoBusy(false)
      e.target.value = ''
    }
  }

  const [name, setName] = useState('')
  const [bio, setBio] = useState('')
  const [cuisines, setCuisines] = useState([])
  const [specialties, setSpecialties] = useState([])
  const [specInput, setSpecInput] = useState('')
  const [rate, setRate] = useState('')
  const [radius, setRadius] = useState('')

  const toggleCuisine = (c) =>
    setCuisines(prev => (prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]))

  const addSpecialty = () => {
    const v = specInput.trim()
    if (!v) return
    if (!specialties.some(s => s.toLowerCase() === v.toLowerCase())) {
      setSpecialties(prev => [...prev, v])
    }
    setSpecInput('')
  }

  const removeSpecialty = (s) => setSpecialties(prev => prev.filter(x => x !== s))

  const ready = useMemo(
    () => name.trim() && bio.trim() && cuisines.length >= 1 && Number(rate) > 0,
    [name, bio, cuisines, rate],
  )

  const handleContinue = () => {
    if (!ready) return
    // The helper application (bio/cuisines/rate) is submitted AFTER identity
    // verification, so the team reviews bio + score together. Carry the draft
    // forward; do NOT grant the cook role here — that happens only on team approval.
    const application = {
      uid: user?.uid,   // so /skill only honors this draft for its owner
      bio: bio.trim(),
      cuisines,
      specialties,
      pricePerHour: Number(rate),
      travelRadiusMiles: Number(radius) || null,
    }
    try { updateProfile({ name: name.trim() }) } catch { /* best-effort: display name */ }
    try { sessionStorage.setItem('cookApplication', JSON.stringify(application)) } catch { /* ignore */ }
    // Past bio now — the durable resume-onboarding intent is satisfied (next return won't force /onboarding/bio).
    try { localStorage.removeItem('cc_pending_onboarding') } catch { /* ignore */ }
    navigate('/skill', { state: { application } })
  }

  return (
    <Shell header={<Header onBack={() => navigate(-1)} />} showNav={false}>
      <motion.div variants={staggerContainer(0.07)} initial="hidden" animate="show">
        {/* hero / intro */}
        <motion.div variants={fadeUp} style={{ padding: '24px 28px 8px' }}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>
            Become a helper
          </p>
          <h1 style={{ fontFamily: SERIF, fontSize: 32, fontWeight: 400, color: '#1a1a1a', margin: '0 0 10px', lineHeight: 1.1 }}>
            Your story
          </h1>
          <p style={{ fontSize: 14, lineHeight: 1.6, color: '#666', margin: 0 }}>
            This is the profile clients see when they invite you into their home. Make it yours — the
            numbers and verification come next.
          </p>
        </motion.div>

        {/* profile photo */}
        <motion.div variants={fadeUp} style={{ padding: '22px 28px 0' }}>
          <FieldLabel>Profile photo</FieldLabel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <motion.button type="button" aria-label="Add photo" onClick={() => fileRef.current?.click()} disabled={photoBusy}
              whileHover={photoBusy ? {} : { scale: 1.03 }} whileTap={photoBusy ? {} : tapScale} style={{
              width: 76, height: 76, flexShrink: 0, border: '1px solid #e5e5e5',
              background: photo ? `#eee url(${photo}) center/cover` : '#FAF8F4',
              cursor: photoBusy ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {!photo && <Camera size={24} color="#bbb" strokeWidth={1.5} />}
            </motion.button>
            <input ref={fileRef} type="file" accept="image/*" onChange={handlePhoto} style={{ display: 'none' }} />
            <div>
              <p style={{ fontSize: 13, color: '#555', margin: '0 0 2px', fontWeight: 600 }}>Add a warm, well-lit photo</p>
              <p style={{ fontSize: 12, color: '#999', margin: 0, lineHeight: 1.5 }}>
                Helpers with a real face photo get booked far more often.
              </p>
            </div>
          </div>
        </motion.div>

        {/* display name */}
        <motion.div variants={fadeUp} style={{ padding: '22px 28px 0' }}>
          <FieldLabel htmlFor="ob-name">Display name</FieldLabel>
          <input id="ob-name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Amara Okafor"
            style={inputStyle} />
        </motion.div>

        {/* bio */}
        <motion.div variants={fadeUp} style={{ padding: '22px 28px 0' }}>
          <FieldLabel htmlFor="ob-bio">Your story</FieldLabel>
          <textarea id="ob-bio" value={bio} onChange={e => setBio(e.target.value.slice(0, BIO_MAX))}
            placeholder="Your experience, what you specialize in, and what clients can expect when you're in their home."
            rows={4} style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.55 }} />
          <p style={{ fontSize: 11, color: bio.length > BIO_MAX - 20 ? '#C4561F' : '#aaa', margin: '6px 0 0', textAlign: 'right' }}>
            {bio.length} / {BIO_MAX}
          </p>
        </motion.div>

        {/* service specialties multi-select */}
        <motion.div variants={fadeUp} style={{ padding: '16px 28px 0' }}>
          <FieldLabel>Service specialties</FieldLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {CUISINE_OPTIONS.map(c => {
              const on = cuisines.includes(c)
              return (
                <motion.button key={c} onClick={() => toggleCuisine(c)} whileTap={tapScale}
                  animate={{ borderColor: on ? '#1a1a1a' : '#e5e5e5', background: on ? '#1a1a1a' : '#fff', color: on ? '#fff' : '#555' }}
                  transition={{ duration: 0.18, ease: EASE }} style={{
                  padding: '7px 13px', fontSize: 12, letterSpacing: 0.3, cursor: 'pointer',
                  border: '1px solid' }}>
                  {c}
                </motion.button>
              )
            })}
          </div>
        </motion.div>

        {/* specialties free-add */}
        <motion.div variants={fadeUp} style={{ padding: '22px 28px 0' }}>
          <FieldLabel htmlFor="ob-spec">Skills & certifications</FieldLabel>
          <div style={{ display: 'flex', gap: 8 }}>
            <input id="ob-spec" value={specInput} onChange={e => setSpecInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSpecialty() } }}
              placeholder="e.g. CPR certified, pet first-aid" style={{ ...inputStyle, flex: 1 }} />
            <motion.button onClick={addSpecialty} aria-label="Add skill" whileTap={tapScale} style={{
              flexShrink: 0, width: 46, border: '1px solid #1a1a1a', background: '#1F6F5C', color: '#fff',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Plus size={18} strokeWidth={2} />
            </motion.button>
          </div>
          {specialties.length > 0 && (
            <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <AnimatePresence>
                {specialties.map(s => (
                  <motion.span key={s} variants={listItem} initial="hidden" animate="show" exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.18 } }}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '6px 8px 6px 12px', fontSize: 12, color: '#1a1a1a',
                    border: '1px solid #e5e5e5', background: '#fff', letterSpacing: 0.3 }}>
                    {s}
                    <button onClick={() => removeSpecialty(s)} aria-label={`Remove ${s}`} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 2,
                      border: 'none', background: 'none', cursor: 'pointer', color: '#aaa' }}>
                      <X size={13} strokeWidth={2} />
                    </button>
                  </motion.span>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </motion.div>

        {/* rate + radius */}
        <motion.div variants={fadeUp} style={{ padding: '22px 28px 0', display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <FieldLabel htmlFor="ob-rate">Hourly rate</FieldLabel>
            <div style={{ display: 'flex', alignItems: 'center', border: '1px solid #e5e5e5', background: '#fff' }}>
              <span style={{ fontFamily: SERIF, fontSize: 20, color: '#999', padding: '0 4px 0 14px' }}>{currency().symbol.trim()}</span>
              <input id="ob-rate" value={rate} onChange={e => setRate(e.target.value.replace(/[^\d]/g, '').slice(0, 4))}
                inputMode="numeric" placeholder="45"
                style={{ ...inputStyle, border: 'none', padding: '12px 14px 12px 4px' }} />
              <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, padding: '0 14px 0 0', whiteSpace: 'nowrap' }}>/ hr</span>
            </div>
            <AnimatePresence>
              {Number(rate) > 0 && (
                <motion.p key="rate-hint" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2, ease: EASE }}
                  style={{ fontSize: 11, color: '#777', margin: '6px 0 0', lineHeight: 1.5, overflow: 'hidden' }}>
                  You&rsquo;ll net ~{money(cookPayout(Number(rate)))}/hr after the {PLATFORM_FEE_PERCENT}% platform fee.
                </motion.p>
              )}
            </AnimatePresence>
          </div>
          <div style={{ flex: 1 }}>
            <FieldLabel htmlFor="ob-radius">Service area</FieldLabel>
            <div style={{ display: 'flex', alignItems: 'center', border: '1px solid #e5e5e5', background: '#fff' }}>
              <input id="ob-radius" value={radius} onChange={e => setRadius(e.target.value.replace(/[^\d]/g, '').slice(0, 3))}
                inputMode="numeric" placeholder="10"
                style={{ ...inputStyle, border: 'none', padding: '12px 4px 12px 14px' }} />
              <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, padding: '0 14px 0 0', whiteSpace: 'nowrap' }}>mi radius</span>
            </div>
          </div>
        </motion.div>

        {/* identity verification note — the differentiator */}
        <motion.div variants={fadeUp} style={{ margin: '24px 28px 0', border: '1px solid #C9A227', background: '#fff', padding: '14px 16px',
          display: 'flex', alignItems: 'center', gap: 14 }}>
          <ShieldCheck size={28} color="#C9A227" strokeWidth={1.5} style={{ flexShrink: 0 }} />
          <div>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>
              Last step: identity verification
            </p>
            <p style={{ fontSize: 12, color: '#777', margin: 0, lineHeight: 1.5 }}>
              A quick ID check and on-camera liveness scan confirms it's really you and earns your gold,
              silver, or bronze tier. Verified helpers get booked first.
            </p>
          </div>
        </motion.div>
      </motion.div>

      <div style={{ height: 100 }} />{/* spacer for sticky CTA */}

      {/* sticky continue bar */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: EASE, delay: 0.1 }}
        style={{ position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: 'min(560px,100vw)', background: '#fff', borderTop: '1px solid #e5e5e5',
        padding: '12px 28px calc(12px + env(safe-area-inset-bottom, 0px))', zIndex: 60 }}>
        <motion.button onClick={handleContinue} disabled={!ready}
          whileHover={ready ? { scale: 1.02 } : {}} whileTap={ready ? { scale: 0.97 } : {}} style={{
          width: '100%', padding: '15px', border: 'none', cursor: ready ? 'pointer' : 'not-allowed',
          background: ready ? '#1a1a1a' : '#ccc', color: '#fff',
          fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          Continue to verification
          <ArrowRight size={16} strokeWidth={2} />
        </motion.button>
        {!ready && (
          <p style={{ fontSize: 11, color: '#aaa', textAlign: 'center', margin: '8px 0 0' }}>
            Add your name, story, a service specialty, and a rate to continue.
          </p>
        )}
      </motion.div>
    </Shell>
  )
}
