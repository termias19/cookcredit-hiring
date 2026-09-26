/**
 * Business onboarding — stands up the org workspace in one short screen (company + location
 * prefilled, service focus as one-tap chips), then grants the 'business' role and drops the user
 * straight into Roles. Minimal clicks: smart defaults, single Continue.
 */
import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { activateBusiness } from '../utils/Api'
import { safeAuthDestination } from '../utils/homeFor'
import { fadeUp, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "var(--cc-display)"
const FOCUS = ['Restaurant', 'Catering', 'Private chef', 'Meal preparation', 'Hospitality staffing', 'Culinary school']

export default function BusinessOnboardingScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, refreshProfile } = useAuth()
  const [name, setName] = useState('')
  const [city, setCity] = useState('')
  const [focus, setFocus] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function enter() {
    if (busy || !name.trim() || !city.trim()) return
    setBusy(true); setErr('')
    try {
      const token = await user?.getIdToken?.()
      if (!token) { setErr('Please sign in to set up a workspace.'); setBusy(false); return }
      // activate() is the SINGLE source of the 'business' role grant (it creates the org + appends
      // the role server-side). We then refresh the profile so BusinessRoute sees the persisted role —
      // no client localStorage flag, no silently-dropped PATCH({roles}). Failure does NOT navigate.
      await activateBusiness({ token, org: { name: name.trim(), city: city.trim(), cuisineFocus: focus } })
      await refreshProfile()
      navigate(safeAuthDestination(location.state?.from) || '/business/roles', { replace: true })
    } catch {
      setErr('Could not set up the workspace. Check your connection and try again.')
      setBusy(false)
    }
  }

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '18px 20px' }}>
      <span style={{ fontSize: 11, letterSpacing: 3, color: '#1F6F5C', textTransform: 'uppercase' }}>CookCredit · Skill hiring</span>
      <h1 style={{ fontFamily: SERIF, fontSize: 34, fontWeight: 400, letterSpacing: '-0.02em', color: '#090A09', margin: '4px 0 0' }}>Set up your workspace</h1>
    </div>
  )

  return (
    <Shell header={header} showNav={false}>
      <motion.div initial="hidden" animate="show" variants={staggerContainer(0.08)} style={{ padding: '20px' }}>
        <motion.div variants={fadeUp}>
          <label style={lbl}>Company</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Your restaurant or company" style={input} />
        </motion.div>

        <motion.div variants={fadeUp}>
          <label style={{ ...lbl, marginTop: 16 }}>Primary location</label>
          <input value={city} onChange={e => setCity(e.target.value)} placeholder="City" style={input} />
        </motion.div>

        <motion.div variants={fadeUp}>
          <label style={{ ...lbl, marginTop: 16 }}>Your business <span style={{ textTransform: 'none', letterSpacing: 0, color: '#74756f' }}>optional</span></label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {FOCUS.map(f => {
              const on = focus.includes(f)
              return <motion.button key={f} whileHover={{ scale: 1.05 }} whileTap={tapScale} animate={{ scale: on ? 1.04 : 1 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                onClick={() => setFocus(p => on ? p.filter(x => x !== f) : [...p, f])}
                style={{ border: `1px solid ${on ? '#1a1a1a' : '#e5e5e5'}`, background: on ? '#1a1a1a' : '#fff', color: on ? '#fff' : '#555', padding: '6px 12px', fontSize: 12, cursor: 'pointer' }}>{f}</motion.button>
            })}
          </div>
        </motion.div>

        {err && <p style={{ fontSize: 13, color: '#c53030', marginTop: 14 }}>{err}</p>}

        <motion.div variants={fadeUp}>
          <motion.button {...buttonPress} onClick={enter} disabled={busy || !name.trim() || !city.trim()} style={{ width: '100%', marginTop: 24, padding: 14, border: 'none',
            background: busy ? '#e5e5e5' : '#1a1a1a', color: busy ? '#999' : '#fff',
            fontSize: 14, fontWeight: 500, letterSpacing: 0.5, cursor: busy ? 'default' : 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            {busy ? 'Setting up…' : <>Enter workspace <ArrowRight size={16} strokeWidth={1.5} /></>}
          </motion.button>
          <p style={{ fontSize: 11, color: '#74756f', textAlign: 'center', marginTop: 10 }}>You can invite teammates and post roles next — nothing here blocks you.</p>
        </motion.div>
      </motion.div>
    </Shell>
  )
}

const lbl = { display: 'block', fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', color: '#74756f', marginBottom: 2 }
const input = { width: '100%', padding: '11px 12px', border: '1px solid #e5e5e5', fontSize: 15, color: '#1a1a1a', marginTop: 6, fontFamily: 'inherit' }
