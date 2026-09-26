import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, CircleAlert, MapPin, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import {
  applyToHiringRole, getHiringRole, getMyHiringApplication, startHiringAttempt,
} from '../utils/Api'
import { buttonPress, fadeUp } from '../styles/motion'
import HiringApplicationDetailScreen from './HiringApplicationDetailScreen'
import { PREVIEW } from '../config'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C', INK = '#1a1a1a'
const field = { width: '100%', border: '1px solid #dedbd4', background: '#fff', padding: '12px 13px', fontSize: 15, color: INK }
const overline = { fontSize: 10, letterSpacing: 2.4, textTransform: 'uppercase', color: '#8c8a84', margin: '0 0 7px' }

function Question({ question, value, onChange }) {
  const inputId = `application-question-${question.id}`
  const label = <label htmlFor={inputId} style={{ display: 'block', fontSize: 14, color: INK, marginBottom: 7 }}>{question.label}{question.required ? ' *' : ''}</label>
  if (question.type === 'yes_no') return <div>{label}<div style={{ display: 'flex', gap: 8 }}>
    {[['Yes', true], ['No', false]].map(([text, answer]) => <button type="button" key={text} aria-pressed={value === answer} onClick={() => onChange(answer)} style={{ border: `1px solid ${value === answer ? INK : '#dedbd4'}`, background: value === answer ? INK : '#fff', color: value === answer ? '#fff' : '#555', padding: '9px 18px', cursor: 'pointer' }}>{text}</button>)}
  </div></div>
  if (question.type === 'select') return <div>{label}<select id={inputId} value={value || ''} onChange={e => onChange(e.target.value)} style={field}>
    <option value="">Choose one</option>{question.options.map(option => <option key={option}>{option}</option>)}
  </select></div>
  if (question.type === 'multiselect') {
    const selected = Array.isArray(value) ? value : []
    return <div>{label}<div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>{question.options.map(option => {
      const on = selected.includes(option)
      return <button type="button" key={option} aria-pressed={on} onClick={() => onChange(on ? selected.filter(item => item !== option) : [...selected, option])} style={{ border: `1px solid ${on ? GREEN : '#dedbd4'}`, background: on ? '#E8F1EC' : '#fff', color: on ? GREEN : '#555', padding: '8px 11px', cursor: 'pointer' }}>{on && '✓ '}{option}</button>
    })}</div></div>
  }
  if (question.type === 'long_text') return <div>{label}<textarea id={inputId} rows={4} value={value || ''} onChange={e => onChange(e.target.value)} style={{ ...field, resize: 'vertical', lineHeight: 1.5 }} /></div>
  return <div>{label}<input id={inputId} type={question.type === 'phone' ? 'tel' : 'text'} value={value || ''} onChange={e => onChange(e.target.value)} style={field} /></div>
}


export default function HiringApplicationScreen() {
  const { roleId } = useParams()
  const navigate = useNavigate()
  const routeLocation = useLocation()
  const [searchParams] = useSearchParams()
  const { user, logout } = useAuth()
  const [role, setRole] = useState(null)
  const [activeApplicationId, setActiveApplicationId] = useState(null)
  const [entryError, setEntryError] = useState('')
  const [answers, setAnswers] = useState({})
  const [fullName, setFullName] = useState(user?.displayName || '')
  const [cv, setCv] = useState(null)
  const [city, setCity] = useState('')
  const [coordinates, setCoordinates] = useState(null)
  const [consent, setConsent] = useState(false)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [locating, setLocating] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const result = await getHiringRole({ roleId, invitationToken: searchParams.get('invite') })
        if (!live) return
        setRole(result.role)
        if (user?.emailVerified) {
          const token = await user.getIdToken()
          const existing = await getMyHiringApplication({ token, roleId })
          if (live && existing.application) { setActiveApplicationId(existing.application.id); setStatus('ready'); return }
        }
        if (live) setStatus('ready')
      } catch (cause) {
        if (live) { setError(cause.status ? cause.message || 'This role is unavailable.' : 'Could not connect to CookCredit. Check your connection and retry.'); setStatus('error') }
      }
    })()
    return () => { live = false }
  }, [roleId, user, searchParams, navigate, reloadKey])

  const requiredComplete = useMemo(() => (role?.questions || []).every(question => {
    if (!question.required) return true
    const value = answers[question.id]
    return value !== undefined && value !== '' && (!Array.isArray(value) || value.length > 0)
  }), [role, answers])
  const locationRequired = Boolean(role?.location?.label)

  async function useApproximateLocation() {
    if (!navigator.geolocation) { setError('Location is unavailable in this browser. Enter your city instead.'); return }
    setLocating(true); setError('')
    navigator.geolocation.getCurrentPosition(
      position => { setCoordinates({ lat: position.coords.latitude, lng: position.coords.longitude }); setLocating(false) },
      () => { setError('Location could not be read. Enter your city instead.'); setLocating(false) },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    )
  }

  async function submit() {
    if (!user) { navigate('/login', { state: { from: routeLocation } }); return }
    if (!user.emailVerified) { navigate('/verify', { state: { from: routeLocation } }); return }
    if (!fullName.trim() || (role.cvRequired && !cv)) { setError('Enter your full name and attach the required CV.'); return }
    if (cv && cv.size > 2 * 1024 * 1024) { setError('Choose a PDF no larger than 2 MB.'); return }
    if ((locationRequired && !city.trim()) || !requiredComplete || !consent) { setError('Complete the required fields and consent notice.'); return }
    setBusy(true); setError('')
    let savedId
    try {
      const token = await user.getIdToken()
      const result = await applyToHiringRole({
        token, roleId, answers, fullName: fullName.trim(), cv,
        location: city.trim() || coordinates ? { city: city.trim(), ...(coordinates || {}) } : undefined,
        consentVersion: role.consentVersion,
        invitationToken: searchParams.get('invite') || undefined,
      })
      savedId = result.application.id
      const attempt = await startHiringAttempt({ token, applicationId: savedId })
      window.location.assign(attempt.launchUrl)
    } catch (cause) {
      if (savedId) {
        setEntryError('Your details are saved. The assessment could not open. Use Start assessment below to retry.')
        setActiveApplicationId(savedId)
      } else setError(cause.message || 'The application could not be submitted.')
    }
    finally { setBusy(false) }
  }

  if (activeApplicationId) return <HiringApplicationDetailScreen key={activeApplicationId} applicationId={activeApplicationId} entryError={entryError} />
  if (status === 'loading') return <main className="cc-hiring-page" style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', color: '#888' }}>Loading role…</main>
  if (status === 'error' || !role) return <main className="cc-hiring-page" style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', padding: 30, textAlign: 'center' }}><div><CircleAlert /><p role="alert">{error}</p><button type="button" onClick={() => { setError(''); setStatus('loading'); setReloadKey(key => key + 1) }} style={{ border: 0, background: GREEN, color: '#fff', padding: '12px 22px', cursor: 'pointer' }}>Retry</button><p style={{ fontSize: 13, color: '#70706b' }}>If the role is closed or your invitation has expired, ask the employer for a current link.</p></div></main>
  const brandColor = /^#[0-9A-F]{6}$/i.test(role.company?.brandColor || '') ? role.company.brandColor : GREEN

  return <main className="cc-hiring-page" style={{ minHeight: '100svh', background: '#F7F5F0', color: INK }}>
    <header style={{ background: '#FEFDFB', color: INK, padding: '24px clamp(18px, 5vw, 64px)', borderTop: `3px solid ${brandColor}`, borderBottom: '1px solid #E3E0D9' }}>
      <button onClick={() => navigate('/')} style={{ border: 0, background: 'none', color: '#70706b', display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', padding: 0, marginBottom: 24 }}><ArrowLeft size={14} /> CookCredit</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 7 }}>{role.company.logoUrl && <img src={role.company.logoUrl} alt="" referrerPolicy="no-referrer" style={{ width: 36, height: 36, objectFit: 'contain', background: '#fff' }} />}<p style={{ ...overline, color: '#70706b', margin: 0 }}>{role.company.name}</p></div>
      <h1 style={{ fontFamily: SERIF, fontWeight: 300, fontSize: 'clamp(30px, 6vw, 48px)', margin: '0 0 10px' }}>{role.title}</h1>
      <p style={{ margin: 0, color: '#70706b', fontSize: 14 }}>{role.location?.label || role.company.city || 'Location shown by employer'} · {role.employment?.type || 'Role'}</p>
    </header>
    {PREVIEW && <div className="cc-preview-note" role="status">Preview application · sample role. Nothing is submitted to an employer.</div>}

    <motion.div initial="hidden" animate="show" variants={fadeUp} style={{ maxWidth: 720, margin: '0 auto', padding: '24px 18px 60px' }}>
      {user && <p style={{ fontSize: 13, color: '#555', marginBottom: 18 }}>Signed in as {user.email}. <button type="button" onClick={async () => { await logout(); navigate('/login', { state: { from: routeLocation } }) }} style={{ border: 0, background: 'none', color: GREEN, textDecoration: 'underline', cursor: 'pointer' }}>Use a different account</button></p>}
      {role.environment === 'test' && <p role="status" style={{ padding: 14, background: '#FFF9E9', border: '1px solid #D8C58B', borderRadius: 2, color: '#5F532D', fontSize: 13 }}>Test assessment — this invitation is for checking the integration. It does not enter the employer’s live hiring pipeline.</p>}
      <section style={{ background: '#fff', border: '1px solid #dedbd4', padding: 20, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
          <div><p style={overline}>Position</p><p style={{ margin: 0, fontSize: 14 }}>{role.employment?.shifts?.join(' · ') || 'Schedule discussed by employer'}</p></div>
          <div><p style={overline}>Pay</p><p style={{ margin: 0, fontSize: 14 }}>${role.employment?.payMin ?? '—'}–${role.employment?.payMax ?? '—'} / hour{role.employment?.tips ? ' + tips' : ''}</p></div>
          <div><p style={overline}>Assessment tries</p><p style={{ margin: 0, fontSize: 14 }}>{role.attemptLimit} total</p></div>
        </div>
        {role.description && <p style={{ margin: '18px 0 0', color: '#555', lineHeight: 1.6, fontSize: 14 }}>{role.description}</p>}
      </section>

      {!user && <section style={{ background: '#fff', border: '1px solid #dedbd4', padding: 22, textAlign: 'center' }}>
        <ShieldCheck size={24} color={GREEN} />
        <h2 style={{ fontFamily: SERIF, fontWeight: 400, fontSize: 25, margin: '10px 0 8px' }}>Apply with CookCredit</h2>
        <p style={{ color: '#666', fontSize: 13, lineHeight: 1.55 }}>Sign in or create an account, verify your email, then return to this role. Add your details and CV, record your knife assessment, and review it before sharing it with {role.company.name}.</p>
        <button onClick={() => navigate('/login', { state: { from: routeLocation } })} style={{ background: brandColor, border: 0, color: '#fff', padding: '13px 28px', cursor: 'pointer' }}>Sign in to apply</button>
        <button onClick={() => navigate('/signup', { state: { from: routeLocation } })} style={{ display: 'block', margin: '12px auto 0', background: 'none', border: 0, color: INK, textDecoration: 'underline', cursor: 'pointer' }}>Create an account</button>
      </section>}

      {user && !user.emailVerified && <section style={{ padding: 22 }}><p>Verify your email before applying.</p><button onClick={() => navigate('/verify', { state: { from: routeLocation } })}>Verify email</button></section>}
      {user?.emailVerified && <section style={{ background: '#fff', border: '1px solid #dedbd4', padding: 20 }}>
        <p style={overline}>1. Your details · 2. Record assessment · 3. Submitted</p>
        <div style={{ display: 'grid', gap: 18 }}>
          <div><label htmlFor="application-name" style={{ display: 'block', fontSize: 14, marginBottom: 7 }}>Full name *</label>
            <input id="application-name" value={fullName} onChange={e => setFullName(e.target.value)} autoComplete="name" maxLength={200} required style={field} /></div>
          {role.cvRequired && <div><label htmlFor="application-cv" style={{ display: 'block', fontSize: 14, marginBottom: 7 }}>CV / résumé *</label>
            <input id="application-cv" type="file" accept="application/pdf,.pdf" onChange={e => setCv(e.target.files?.[0] || null)} required />
            <p style={{ fontSize: 12, color: '#70706b' }}>PDF, up to 2 MB. Shared only with this company for this application.</p></div>}
          {(role.questions || []).map(question => <Question key={question.id} question={question} value={answers[question.id]} onChange={value => setAnswers(current => ({ ...current, [question.id]: value }))} />)}
          <div>
            <label htmlFor="application-city" style={{ display: 'block', fontSize: 14, marginBottom: 7 }}>City or area{locationRequired ? ' *' : ' (optional)'}</label>
            <input id="application-city" value={city} onChange={event => setCity(event.target.value)} placeholder="e.g. Brooklyn, NY" style={field} />
            <button type="button" onClick={useApproximateLocation} disabled={locating} style={{ background: 'none', border: 0, color: GREEN, padding: '9px 0 0', cursor: 'pointer', display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}><MapPin size={13} /> {locating ? 'Reading location…' : coordinates ? 'Approximate location added' : 'Add approximate location'}</button>
            <p style={{ margin: '5px 0 0', color: '#70706b', fontSize: 12 }}>Optional: share your neighborhood to help the employer check travel distance. Your precise location is not saved.</p>
          </div>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 9, fontSize: 12, color: '#555', lineHeight: 1.55 }}>
            <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} style={{ marginTop: 3, accentColor: GREEN }} />
            <span>{role.consentText}</span>
          </label>
          {error && <p style={{ margin: 0, color: '#A44320', fontSize: 13 }}>{error}</p>}
          <motion.button {...buttonPress} type="button" disabled={busy || !fullName.trim() || (role.cvRequired && !cv) || (locationRequired && !city.trim()) || !requiredComplete || !consent} onClick={submit} style={{ border: 0, background: brandColor, color: '#fff', padding: 14, cursor: 'pointer', opacity: busy || !fullName.trim() || (role.cvRequired && !cv) || (locationRequired && !city.trim()) || !requiredComplete || !consent ? 0.45 : 1 }}>
            {busy ? 'Saving and opening assessment…' : 'Continue to assessment'}
          </motion.button>
        </div>
      </section>}


    </motion.div>
  </main>
}
