/**
 * Helper profile editor (/cook/profile/edit) — the Qwick/Indeed-style "edit your professional
 * profile" screen. A helper can update their marketplace profile ANY TIME (pending or approved):
 * photo, name, story/bio, service specialties, highlighted skills, experience, hourly rate, service area, and
 * certifications. Loads the authoritative values from GET /api/cooks/me and saves via
 * PATCH /api/cooks/me (helper fields) + the auth profile (name/photo).
 *
 * The VERIFIED identity credential is shown READ-ONLY — it is earned via ID + liveness verification
 * (SkillScreen), never typed here — with a link to view/retake it. Responsive via Shell (desktop card + app frame).
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Camera, Plus, X, ShieldCheck, ScanLine, Check, Eye } from 'lucide-react'
import Shell from '../components/Shell'
import ServiceAreaControls from '../components/ServiceAreaControls'
import { useAuth } from '../context/AuthContext'
import { getCookMe, updateCookProfile, uploadPortfolioImage } from '../utils/Api'
import { money, cookPayout, currency, PLATFORM_FEE_PERCENT } from '../utils/money.js'
import { REGION } from '../utils/region'
import { fadeUp, fadeIn, scaleIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C', GOLD = '#C9A227', TERRA = '#C4561F'
const BIO_MAX = 600
const TIER_COLOR = { gold: GOLD, silver: '#9AA3AD', bronze: '#B08D57' }

const CUISINE_OPTIONS = [
  'House cleaning', 'Cooking & meal prep', 'Laundry & ironing', 'Childcare / nannying',
  'Elder & companion care', 'Errands & general household tasks', 'Deep cleaning', 'Organizing', 'Pet care',
]
const DIETARY_OPTIONS = [
  'CPR Certified', 'First Aid Certified', 'Background Check Cleared', 'Newborn Care Certified',
  'Food Handler Certified', "Driver's License", 'Bilingual', 'Pet First Aid Certified',
]

const inputStyle = {
  width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', background: '#fff',
  padding: '12px 14px', fontSize: 14, color: '#1a1a1a', outline: 'none', fontFamily: 'inherit',
}

function FieldLabel({ children, htmlFor }) {
  return (
    <label htmlFor={htmlFor} style={{ display: 'block', fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 8px' }}>
      {children}
    </label>
  )
}

function Chip({ on, onClick, children }) {
  return (
    <motion.button type="button" onClick={onClick}
      whileHover={{ scale: on ? 1 : 1.04 }} whileTap={tapScale}
      animate={{ scale: on ? [1, 1.1, 1] : 1 }} transition={{ duration: 0.25 }}
      style={{
        padding: '7px 13px', fontSize: 12, letterSpacing: 0.3, cursor: 'pointer',
        border: '1px solid', borderColor: on ? '#1a1a1a' : '#e5e5e5',
        background: on ? '#1a1a1a' : '#fff', color: on ? '#fff' : '#555' }}>
      {children}
    </motion.button>
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
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase' }}>Edit profile</span>
      </div>
    </div>
  )
}

export default function CookProfileEditScreen() {
  const navigate = useNavigate()
  const { user, updateProfile, refreshProfile } = useAuth()
  const fileRef = useRef(null)

  const [status, setStatus] = useState('loading')   // loading | ready | noprofile | error
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState('')
  const [photoBusy, setPhotoBusy] = useState(false)

  // editable fields
  const [name, setName] = useState('')
  const [photo, setPhoto] = useState(null)
  const [bio, setBio] = useState('')
  const [cuisines, setCuisines] = useState([])
  const [specialties, setSpecialties] = useState([])
  const [specInput, setSpecInput] = useState('')
  const [years, setYears] = useState('')
  const [rate, setRate] = useState('')
  const [radius, setRadius] = useState('')
  const [city, setCity] = useState('')
  const [stateRegion, setStateRegion] = useState('')
  const [dietary, setDietary] = useState([])

  // read-only credential
  const [cred, setCred] = useState({ score: null, tier: null, verified: false, when: null, appStatus: null })

  useEffect(() => {
    let live = true
    if (!user) return
    ;(async () => {
      try {
        const d = await getCookMe({ auth: { currentUser: user } })
        if (!live) return
        setName(d?.name || '')
        setPhoto(d?.photoUrl || null)
        setBio(d?.bio || '')
        setCuisines(Array.isArray(d?.cuisines) ? d.cuisines : [])
        setSpecialties(Array.isArray(d?.specialties) ? d.specialties : [])
        setYears(d?.yearsExperience != null ? String(d.yearsExperience) : '')
        setRate(d?.pricePerHour != null ? String(d.pricePerHour) : '')
        setRadius(d?.travelRadiusMiles != null ? String(d.travelRadiusMiles) : '')
        setCity(d?.baseCity || '')
        setStateRegion(d?.baseState || '')
        setDietary(Array.isArray(d?.dietaryCapabilities) ? d.dietaryCapabilities : [])
        setCred({
          score: d?.skillScore ?? null, tier: d?.skillTier || null, verified: !!d?.skillVerified,
          when: d?.skillTestAt ? new Date(d.skillTestAt).toLocaleDateString(REGION.dateLocale, { month: 'short', year: 'numeric' }) : null,
          appStatus: d?.applicationStatus || null,
        })
        setStatus('ready')
      } catch (e) {
        if (!live) return
        // 404 = signed-in user has no cook profile yet → send them through onboarding instead.
        setStatus(String(e?.message || '').includes('404') || String(e?.message || '').includes('no cook profile') ? 'noprofile' : 'error')
      }
    })()
    return () => { live = false }
  }, [user])

  async function handlePhoto(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoBusy(true)
    try {
      const res = await uploadPortfolioImage({ auth: { currentUser: user }, file })
      if (res?.url) {
        setPhoto(res.url)
        try { await updateProfile({ photoUrl: res.url }) } catch { /* avatar set on next load */ }
      }
    } catch { /* leave the current photo */ } finally {
      setPhotoBusy(false); e.target.value = ''
    }
  }

  const toggleCuisine = c => setCuisines(prev => (prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]))
  const toggleDietary = c => setDietary(prev => (prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]))
  const removeSpecialty = s => setSpecialties(prev => prev.filter(x => x !== s))
  const addSpecialty = () => {
    const v = specInput.trim()
    if (v && !specialties.some(s => s.toLowerCase() === v.toLowerCase())) setSpecialties(prev => [...prev, v])
    setSpecInput('')
  }

  const canSave = useMemo(
    () => name.trim() && bio.trim() && cuisines.length >= 1 && Number(rate) > 0,
    [name, bio, cuisines, rate])

  async function handleSave() {
    if (!canSave || saving) return
    setSaving(true); setErr(''); setSaved(false)
    try {
      if (name.trim()) { try { await updateProfile({ name: name.trim() }) } catch { /* non-fatal */ } }
      await updateCookProfile({
        auth: { currentUser: user },
        bio: bio.trim(),
        cuisines,
        specialties,
        pricePerHour: Number(rate) || null,
        travelRadiusMiles: radius === '' ? null : Number(radius),
        baseCity: city.trim() || null,
        baseState: stateRegion.trim() || null,
        yearsExperience: years === '' ? null : Number(years),
        dietaryCapabilities: dietary,
      })
      try { await refreshProfile?.() } catch { /* the save persisted; profile re-syncs on next load */ }
      setSaved(true)
    } catch {
      setErr('Could not save your changes. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const onBack = () => navigate(-1)

  if (status === 'loading') {
    return <Shell wide header={<Header onBack={onBack} />} showNav={false}>
      <p style={{ textAlign: 'center', color: '#999', padding: '60px 20px' }}>Loading your profile…</p></Shell>
  }
  if (status === 'noprofile') {
    return <Shell wide header={<Header onBack={onBack} />} showNav={false}>
      <div style={{ textAlign: 'center', padding: '52px 24px', maxWidth: 480, margin: '0 auto' }}>
        <p style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a', margin: '0 0 8px' }}>No helper profile yet</p>
        <p style={{ fontSize: 13, color: '#999', margin: '0 0 18px', lineHeight: 1.5 }}>Set up your helper profile and complete identity verification to get listed.</p>
        <button onClick={() => navigate('/onboarding/bio')} style={{ padding: '13px 22px', background: '#1F6F5C', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase' }}>Become a helper</button>
      </div></Shell>
  }
  if (status === 'error') {
    return <Shell wide header={<Header onBack={onBack} />} showNav={false}>
      <p style={{ textAlign: 'center', color: '#999', padding: '60px 20px' }}>Couldn’t load your profile. Please try again.</p></Shell>
  }

  const tc = TIER_COLOR[cred.tier] || GREEN
  const canViewPublic = cred.verified && cred.appStatus === 'approved'

  return (
    <Shell wide header={<Header onBack={onBack} />} showNav={false}>
      <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ padding: '28px 0 4px' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Your helper profile</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(26px, 3.4vw, 32px)', fontWeight: 400, color: '#1a1a1a', margin: '0 0 6px', lineHeight: 1.1 }}>Edit profile</h1>
        <p style={{ fontSize: 13, color: '#666', margin: 0, lineHeight: 1.6, maxWidth: 560 }}>This is what clients and businesses see. Keep it current — changes save instantly.</p>
      </motion.div>

      <motion.div variants={staggerContainer(0.05, 0.04)} initial="hidden" animate="show"
        style={{ padding: '22px 0 40px', display: 'flex', gap: 28, alignItems: 'flex-start', flexWrap: 'wrap' }}>

        {/* LEFT — sticky live-summary preview: how this reads on the public profile */}
        <motion.div variants={fadeUp} style={{
          flex: '1 1 260px', maxWidth: 300, position: 'sticky', top: 28,
          border: '1px solid #e5e5e5', background: '#fff', padding: '28px 24px', textAlign: 'center' }}>
          <div style={{
            width: 96, height: 96, margin: '0 auto 16px', borderRadius: '50%', overflow: 'hidden',
            border: '1px solid #e5e5e5', background: photo ? `#eee url(${photo}) center/cover` : '#FAF8F4',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {!photo && <Camera size={26} color="#bbb" strokeWidth={1.5} />}
          </div>
          <h2 style={{ fontFamily: SERIF, fontSize: 22, fontWeight: 400, color: '#1a1a1a', margin: '0 0 4px' }}>{name || 'Your name'}</h2>
          {cred.verified && cred.tier && (
            <p style={{ fontSize: 11, letterSpacing: 1, color: tc, textTransform: 'uppercase', fontWeight: 600, margin: '0 0 4px',
              display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <ShieldCheck size={13} strokeWidth={2} /> {cred.tier} verified
            </p>
          )}
          <div style={{ borderTop: '1px solid #f0f0f0', marginTop: 14, paddingTop: 16 }}>
            <div style={{ fontFamily: SERIF, fontSize: 26, color: '#1a1a1a', lineHeight: 1 }}>
              {Number(rate) > 0 ? money(Number(rate)) : '—'}
            </div>
            <div style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, marginTop: 2 }}>per hour</div>
          </div>
          <p style={{ fontSize: 11, color: '#999', margin: '16px 0 0', lineHeight: 1.5 }}>
            A preview of how you appear on your public profile.
          </p>
        </motion.div>

        {/* RIGHT — the form */}
        <div style={{ flex: '2 1 420px', maxWidth: 720, minWidth: 0 }}>

      {/* photo + name */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.04 }} style={{ padding: 0 }}>
        <FieldLabel>Profile photo</FieldLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <motion.button type="button" aria-label="Change photo" onClick={() => fileRef.current?.click()} disabled={photoBusy}
            whileHover={{ scale: 1.04 }} whileTap={tapScale} style={{
            width: 76, height: 76, flexShrink: 0, border: '1px solid #e5e5e5', borderRadius: '50%', overflow: 'hidden',
            background: photo ? `#eee url(${photo}) center/cover` : '#FAF8F4',
            cursor: photoBusy ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {!photo && <Camera size={24} color="#bbb" strokeWidth={1.5} />}
          </motion.button>
          <input ref={fileRef} type="file" accept="image/*" onChange={handlePhoto} style={{ display: 'none' }} />
          <div>
            <p style={{ fontSize: 13, color: '#555', margin: '0 0 2px', fontWeight: 600 }}>{photoBusy ? 'Uploading…' : 'A warm, well-lit face photo'}</p>
            <p style={{ fontSize: 12, color: '#999', margin: 0, lineHeight: 1.5 }}>Helpers with a real photo get booked far more often.</p>
          </div>
        </div>
      </motion.div>

      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.07 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel htmlFor="ce-name">Display name</FieldLabel>
        <input id="ce-name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Amara Okafor" style={inputStyle} />
      </motion.div>

      {/* verified credential — READ ONLY */}
      <motion.div variants={scaleIn} initial="hidden" animate="show" transition={{ delay: 0.1 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel>Verified identity</FieldLabel>
        <div style={{ border: `1px solid ${cred.score != null && cred.verified ? tc : '#e5e5e5'}`, background: '#fff', padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <ShieldCheck size={26} color={cred.score != null && cred.verified ? tc : '#bbb'} strokeWidth={1.5} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              {cred.score != null ? (
                <p style={{ fontSize: 13, color: '#1a1a1a', margin: 0 }}>
                  <span style={{ fontFamily: SERIF, fontSize: 22 }}>{cred.score}</span>
                  <span style={{ color: '#999' }}>{' / 100 · '}{cred.tier ? `${cred.tier} · ` : ''}{cred.verified ? 'Verified' : 'Scored'}{cred.when ? ` · ${cred.when}` : ''}</span>
                </p>
              ) : (
                <p style={{ fontSize: 13, color: '#777', margin: 0, lineHeight: 1.5 }}>Earned via ID verification — complete verification to get your verified score.</p>
              )}
              <p style={{ fontSize: 11, color: '#aaa', margin: '3px 0 0' }}>Earned via ID verification — not editable here.</p>
            </div>
          </div>
          <motion.button onClick={() => navigate('/skill')} {...buttonPress} style={{
            width: '100%', marginTop: 12, padding: '11px 14px', cursor: 'pointer',
            background: cred.score != null ? '#fff' : '#1a1a1a', border: cred.score != null ? '1px solid #1a1a1a' : 'none',
            color: cred.score != null ? '#1a1a1a' : '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            fontSize: 13, fontWeight: 500, letterSpacing: 0.5 }}>
            <ScanLine size={15} strokeWidth={1.5} /> {cred.score != null ? 'View / retake verification' : 'Complete identity verification'}
          </motion.button>
        </div>
      </motion.div>

      {/* bio */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.13 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel htmlFor="ce-bio">Your story</FieldLabel>
        <textarea id="ce-bio" value={bio} onChange={e => setBio(e.target.value.slice(0, BIO_MAX))} rows={4}
          placeholder="Where you learned your trade, what kind of help you love providing, and what it feels like to have you in someone's home."
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.55 }} />
        <p style={{ fontSize: 11, color: bio.length > BIO_MAX - 40 ? TERRA : '#aaa', margin: '6px 0 0', textAlign: 'right' }}>{bio.length} / {BIO_MAX}</p>
      </motion.div>

      {/* service specialties */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.16 }} style={{ padding: '10px 0 0' }}>
        <FieldLabel>Service specialties</FieldLabel>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Array.from(new Set([...CUISINE_OPTIONS, ...cuisines])).map(c => (
            <Chip key={c} on={cuisines.includes(c)} onClick={() => toggleCuisine(c)}>{c}</Chip>
          ))}
        </div>
      </motion.div>

      {/* highlighted skills */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.19 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel htmlFor="ce-spec">Highlighted skills</FieldLabel>
        <div style={{ display: 'flex', gap: 8 }}>
          <input id="ce-spec" value={specInput} onChange={e => setSpecInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSpecialty() } }}
            placeholder="e.g. Deep oven cleaning" style={{ ...inputStyle, flex: 1 }} />
          <motion.button onClick={addSpecialty} aria-label="Add skill" whileHover={{ scale: 1.05 }} whileTap={tapScale} style={{
            flexShrink: 0, width: 46, border: '1px solid #1a1a1a', background: '#1F6F5C', color: '#fff',
            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Plus size={18} strokeWidth={2} />
          </motion.button>
        </div>
        {specialties.length > 0 && (
          <motion.div variants={fadeIn} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            <AnimatePresence>
              {specialties.map(s => (
                <motion.span key={s} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 8px 6px 12px',
                  fontSize: 12, color: '#1a1a1a', border: '1px solid #e5e5e5', background: '#fff', letterSpacing: 0.3 }}>
                  {s}
                  <button onClick={() => removeSpecialty(s)} aria-label={`Remove ${s}`} style={{ display: 'flex', alignItems: 'center', padding: 2, border: 'none', background: 'none', cursor: 'pointer', color: '#aaa' }}>
                    <X size={13} strokeWidth={2} />
                  </button>
                </motion.span>
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </motion.div>

      {/* experience */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.22 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel htmlFor="ce-years">Years of experience</FieldLabel>
        <div style={{ display: 'flex', alignItems: 'center', border: '1px solid #e5e5e5', background: '#fff', maxWidth: 160 }}>
          <input id="ce-years" value={years} onChange={e => setYears(e.target.value.replace(/[^\d]/g, '').slice(0, 2))}
            inputMode="numeric" placeholder="5" style={{ ...inputStyle, border: 'none' }} />
          <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, padding: '0 14px 0 0', whiteSpace: 'nowrap' }}>years</span>
        </div>
      </motion.div>

      {/* rate + radius */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.25 }} style={{ padding: '22px 0 0', display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <FieldLabel htmlFor="ce-rate">Hourly rate</FieldLabel>
          <div style={{ display: 'flex', alignItems: 'center', border: '1px solid #e5e5e5', background: '#fff' }}>
            <span style={{ fontFamily: SERIF, fontSize: 20, color: '#999', padding: '0 4px 0 14px' }}>{currency().symbol.trim()}</span>
            <input id="ce-rate" value={rate} onChange={e => setRate(e.target.value.replace(/[^\d]/g, '').slice(0, 4))}
              inputMode="numeric" placeholder="45" style={{ ...inputStyle, border: 'none', padding: '12px 14px 12px 4px' }} />
            <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, padding: '0 14px 0 0', whiteSpace: 'nowrap' }}>/ hr</span>
          </div>
          {Number(rate) > 0 && (
            <p style={{ fontSize: 11, color: '#777', margin: '6px 0 0', lineHeight: 1.5 }}>You&rsquo;ll net ~{money(cookPayout(Number(rate)))}/hr after the {PLATFORM_FEE_PERCENT}% platform fee.</p>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <FieldLabel htmlFor="ce-radius">Travel radius</FieldLabel>
          <div style={{ display: 'flex', alignItems: 'center', border: '1px solid #e5e5e5', background: '#fff' }}>
            <input id="ce-radius" value={radius} onChange={e => setRadius(e.target.value.replace(/[^\d]/g, '').slice(0, 3))}
              inputMode="numeric" placeholder="10" style={{ ...inputStyle, border: 'none', padding: '12px 4px 12px 14px' }} />
            <span style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, padding: '0 14px 0 0', whiteSpace: 'nowrap' }}>mi</span>
          </div>
        </div>
      </motion.div>

      {/* service area */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.28 }} style={{ padding: '22px 0 0', display: 'flex', gap: 12 }}>
        <div style={{ flex: 2 }}>
          <FieldLabel htmlFor="ce-city">City</FieldLabel>
          <input id="ce-city" value={city} onChange={e => setCity(e.target.value)} placeholder="Atlanta" style={inputStyle} />
        </div>
        <div style={{ flex: 1 }}>
          <FieldLabel htmlFor="ce-state">State</FieldLabel>
          <input id="ce-state" value={stateRegion} onChange={e => setStateRegion(e.target.value.slice(0, 24))} placeholder="GA" style={inputStyle} />
        </div>
      </motion.div>

      <ServiceAreaControls />

      {/* certifications */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.31 }} style={{ padding: '22px 0 0' }}>
        <FieldLabel>Certifications</FieldLabel>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Array.from(new Set([...DIETARY_OPTIONS, ...dietary])).map(c => (
            <Chip key={c} on={dietary.includes(c)} onClick={() => toggleDietary(c)}>{c}</Chip>
          ))}
        </div>
      </motion.div>

      {/* view public profile (approved + verified only) */}
      {canViewPublic && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.34 }} style={{ padding: '22px 0 0' }}>
          <motion.button onClick={() => navigate(`/cook/${user.uid}`)} whileHover={{ scale: 1.02 }} whileTap={tapScale} style={{
            width: '100%', padding: '12px 14px', background: '#fff', border: '1px solid #e5e5e5', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 13, color: '#1a1a1a' }}>
            <Eye size={15} strokeWidth={1.5} color={GREEN} /> View my public profile
          </motion.button>
        </motion.div>
      )}

      {/* save */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" transition={{ delay: 0.37 }} style={{ padding: '26px 0 40px' }}>
        <motion.button onClick={handleSave} disabled={!canSave || saving} {...buttonPress} style={{
          width: '100%', padding: '15px', border: 'none', cursor: (canSave && !saving) ? 'pointer' : 'not-allowed',
          background: (canSave && !saving) ? '#1a1a1a' : '#ccc', color: '#fff',
          fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <Check size={16} strokeWidth={2} /> {saving ? 'Saving…' : 'Save changes'}
        </motion.button>
        <AnimatePresence>
          {saved && (
            <motion.p key="saved-ok" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
              style={{ fontSize: 13, color: GREEN, textAlign: 'center', margin: '12px 0 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <Check size={14} strokeWidth={2} /> Profile saved.
            </motion.p>
          )}
        </AnimatePresence>
        {err && <p style={{ fontSize: 12, color: TERRA, textAlign: 'center', margin: '12px 0 0' }}>{err}</p>}
        {!canSave && !saved && <p style={{ fontSize: 11, color: '#aaa', textAlign: 'center', margin: '10px 0 0' }}>Add your name, story, a service specialty, and an hourly rate to save.</p>}
      </motion.div>

        </div>
      </motion.div>
    </Shell>
  )
}
