/**
 * Household — the client's preferences hub (route /pantry, showNav=true).
 *
 * The "what we should know before a helper steps into your home" screen:
 * household details, allergies/safety notes, access notes, default service
 * address (prefills bookings), household size, and saved helpers (favorites).
 * Calm and editorial, not a settings dump — every section earns its place in
 * the booking flow. A single "Save preferences" affordance confirms inline.
 *
 * Mock/local state for now; wires to GET/PATCH /api/me/pantry later.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Heart, MapPin, Plus, X, Minus, Check, ShieldCheck } from 'lucide-react'
import Shell from '../components/Shell'
import { fadeUp, staggerContainer, listItem, hoverLift, tapScale, EASE } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const TIER_COLOR = { gold: '#C9A227', silver: '#9AA3AD', bronze: '#B08D57' }

const DIET_OPTIONS = ['Pets in home', 'Children in home', 'Elderly / care needs', 'Security system', 'Smoker in home', 'Gated access']

const SAVED_COOKS = [
  { id: 'c1', name: 'Amara Okafor', tier: 'gold',   cuisines: ['House cleaning', 'Deep cleaning'] },
  { id: 'c3', name: 'Mei Lin',      tier: 'gold',   cuisines: ['Childcare / nannying', 'Errands'] },
  { id: 'c4', name: 'Sara Haile',   tier: 'bronze', cuisines: ['Elder & companion care', 'Cooking'] },
]

function Header() {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 24px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: '0 0 6px' }}>Your household</h1>
        <p style={{ fontSize: 13, color: '#777', margin: 0, lineHeight: 1.5, maxWidth: 520 }}>
          What we tell every helper before they step into your home.
        </p>
      </div>
    </div>
  )
}

function Section({ title, hint, children }) {
  return (
    <motion.div variants={fadeUp} style={{ padding: '22px 0 0' }}>
      <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 4px' }}>{title}</p>
      {hint && <p style={{ fontSize: 12, color: '#999', margin: '0 0 12px', lineHeight: 1.5 }}>{hint}</p>}
      {!hint && <div style={{ height: 8 }} />}
      {children}
    </motion.div>
  )
}

export default function PantryScreen() {
  const navigate = useNavigate()
  const [diet, setDiet] = useState(['Children in home', 'Pets in home'])
  const [allergies, setAllergies] = useState(['Cat dander', 'Peanut allergy (child)'])
  const [allergyDraft, setAllergyDraft] = useState('')
  const [accessNotes, setAccessNotes] = useState('')
  const [address, setAddress] = useState('1287 Ponce de Leon Ave NE, Atlanta, GA 30306')
  const [household, setHousehold] = useState(4)
  const [saved, setSaved] = useState(true)

  const dirty = () => setSaved(false)

  const toggleDiet = (d) => {
    dirty()
    setDiet(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d])
  }

  const addAllergy = () => {
    const v = allergyDraft.trim()
    if (!v) return
    if (!allergies.some(a => a.toLowerCase() === v.toLowerCase())) {
      setAllergies(prev => [...prev, v])
      dirty()
    }
    setAllergyDraft('')
  }

  const removeAllergy = (a) => {
    dirty()
    setAllergies(prev => prev.filter(x => x !== a))
  }

  const setHouse = (n) => {
    const v = Math.max(1, Math.min(20, n))
    if (v !== household) dirty()
    setHousehold(v)
  }

  return (
    <Shell wide header={<Header />}>
      <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show"
        style={{ padding: '8px 0 40px', display: 'flex', gap: 32, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      <div style={{ flex: '3 1 420px', minWidth: 0 }}>
      {/* Household details */}
      <Section title="Household details" hint="Tap what applies. Helpers plan their visit around these.">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {DIET_OPTIONS.map(d => {
            const on = diet.includes(d)
            return (
              <motion.button key={d} onClick={() => toggleDiet(d)} whileTap={tapScale}
                animate={{ borderColor: on ? '#1F6F5C' : '#e5e5e5', background: on ? '#E8F1EC' : '#fff', color: on ? '#1F6F5C' : '#555' }}
                transition={{ duration: 0.18, ease: EASE }} style={{
                padding: '7px 14px', fontSize: 12, letterSpacing: 0.3, cursor: 'pointer', borderRadius: 999,
                border: '1px solid',
                fontWeight: on ? 600 : 400,
              }}>{d}</motion.button>
            )
          })}
        </div>
      </Section>

      {/* Allergies & safety notes */}
      <Section title="Allergies & safety notes" hint="The non-negotiables — allergies, sensitivities, or care needs. We flag these for the helper in bold.">
        <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <AnimatePresence>
            {allergies.map(a => (
              <motion.span key={a} variants={listItem} initial="hidden" animate="show" exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.18 } }} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 8px 6px 12px',
                fontSize: 12, color: '#C4561F', background: '#FBEAE1',
                borderRadius: 999, fontWeight: 600,
              }}>
                {a}
                <button onClick={() => removeAllergy(a)} aria-label={`Remove ${a}`} style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  border: 'none', background: 'none', cursor: 'pointer', padding: 0, color: '#C4561F',
                }}>
                  <X size={13} strokeWidth={2} />
                </button>
              </motion.span>
            ))}
          </AnimatePresence>
          {allergies.length === 0 && (
            <span style={{ fontSize: 12, color: '#aaa' }}>Nothing on file.</span>
          )}
        </motion.div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: '1px solid #e5e5e5', background: '#fff', padding: '10px 12px' }}>
          <input
            value={allergyDraft}
            onChange={e => setAllergyDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addAllergy() } }}
            aria-label="Add a note"
            placeholder="Add an allergy or care note, then press enter"
            style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, color: '#1a1a1a', background: 'transparent' }}
          />
          <motion.button onClick={addAllergy} aria-label="Add note" whileTap={tapScale} style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30,
            border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer', flexShrink: 0,
          }}>
            <Plus size={16} strokeWidth={1.5} color="#1a1a1a" />
          </motion.button>
        </div>
      </Section>

      {/* Access & instructions */}
      <Section title="Access & instructions" hint="Gate codes, parking, alarm codes — anything that helps a helper get in and get started.">
        <textarea
          value={accessNotes}
          onChange={e => { setAccessNotes(e.target.value); dirty() }}
          rows={3}
          aria-label="Access notes"
          placeholder="e.g. Gate code 4471#, park in the driveway, dog is friendly…"
          style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #e5e5e5', background: '#fff',
            padding: '12px 14px', fontSize: 14, color: '#1a1a1a', outline: 'none', resize: 'vertical',
            fontFamily: 'inherit' }}
        />
      </Section>

      {/* Default service address */}
      <Section title="Default service address" hint="Prefilled when you book — change it per session anytime.">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, border: '1px solid #e5e5e5', background: '#fff', padding: '12px 14px' }}>
          <MapPin size={16} color="#999" strokeWidth={1.5} style={{ flexShrink: 0 }} />
          <input
            value={address}
            onChange={e => { setAddress(e.target.value); dirty() }}
            aria-label="Default service address"
            placeholder="Street, city, state, ZIP"
            style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, color: '#1a1a1a', background: 'transparent' }}
          />
        </div>
      </Section>

      {/* Household size */}
      <Section title="Household size" hint="How many people a helper should expect in the home.">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          border: '1px solid #e5e5e5', background: '#fff', padding: '14px 16px' }}>
          <div>
            <motion.div key={household} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: EASE }} style={{ fontFamily: SERIF, fontSize: 30, color: '#1a1a1a', lineHeight: 1 }}>{household}</motion.div>
            <div style={{ fontSize: 11, color: '#aaa', letterSpacing: 0.5, marginTop: 2 }}>
              {household === 1 ? 'person' : 'people'}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <motion.button onClick={() => setHouse(household - 1)} aria-label="Decrease" whileTap={household <= 1 ? {} : tapScale} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', width: 40, height: 40,
              border: '1px solid #e5e5e5', background: '#fff', cursor: household <= 1 ? 'default' : 'pointer',
              opacity: household <= 1 ? 0.4 : 1,
            }}>
              <Minus size={18} strokeWidth={1.5} color="#1a1a1a" />
            </motion.button>
            <motion.button onClick={() => setHouse(household + 1)} aria-label="Increase" whileTap={tapScale} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', width: 40, height: 40,
              border: '1px solid #1a1a1a', background: '#1F6F5C', cursor: 'pointer',
            }}>
              <Plus size={18} strokeWidth={1.5} color="#fff" />
            </motion.button>
          </div>
        </div>
      </Section>

      {/* Save affordance */}
      <motion.div variants={fadeUp} style={{ padding: '26px 0 0' }}>
        <motion.button onClick={() => setSaved(true)} disabled={saved} whileHover={saved ? {} : { scale: 1.01 }} whileTap={saved ? {} : { scale: 0.98 }} style={{
          width: '100%', padding: '15px', border: 'none', cursor: saved ? 'default' : 'pointer',
          fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          background: saved ? '#E8F1EC' : '#1a1a1a', color: saved ? '#1F6F5C' : '#fff',
        }}>
          <AnimatePresence mode="wait" initial={false}>
            {saved ? (
              <motion.span key="saved" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }} transition={{ duration: 0.18, ease: EASE }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <Check size={16} strokeWidth={2} /> Preferences saved
              </motion.span>
            ) : (
              <motion.span key="save" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                Save preferences
              </motion.span>
            )}
          </AnimatePresence>
        </motion.button>
        <p style={{ fontSize: 11, color: '#aaa', textAlign: 'center', margin: '12px 0 0', lineHeight: 1.5 }}>
          Shared only with helpers you book — never sold, never public.
        </p>
      </motion.div>
      </div>

      {/* Saved helpers — sidebar */}
      <div style={{ flex: '1 1 280px', minWidth: 0, position: 'sticky', top: 28 }}>
      <Section title="Saved helpers" hint="Your shortlist — rebook a favorite in two taps.">
        <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {SAVED_COOKS.map(c => {
            const tc = TIER_COLOR[c.tier] || '#777'
            return (
              <motion.button key={c.id} onClick={() => navigate(`/cook/${c.id}`)} variants={listItem} whileHover={hoverLift} whileTap={tapScale} style={{
                display: 'flex', alignItems: 'center', gap: 14, width: '100%', textAlign: 'left', cursor: 'pointer',
                background: '#fff', border: '1px solid #e5e5e5', padding: 12,
              }}>
                <div style={{ width: 56, height: 56, flexShrink: 0, background: c.photo ? `#eee url(${c.photo}) center/cover` : '#EDE7DF',
                  display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {!c.photo && <span style={{ fontFamily: SERIF, fontSize: 20, color: '#9a8c7a' }}>{c.name.trim().charAt(0).toUpperCase()}</span>}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                    <span style={{ fontFamily: SERIF, fontSize: 19, color: '#1a1a1a' }}>{c.name}</span>
                    <ShieldCheck size={14} color={tc} strokeWidth={2} />
                  </div>
                  <p style={{ fontSize: 11, letterSpacing: 1, color: tc, textTransform: 'uppercase', fontWeight: 600, margin: '0 0 3px' }}>
                    {c.tier} verified
                  </p>
                  <p style={{ fontSize: 12, color: '#777', margin: 0 }}>{c.cuisines.join(' · ')}</p>
                </div>
                <Heart size={20} color="#C4561F" fill="#C4561F" strokeWidth={1.5} style={{ flexShrink: 0 }} />
              </motion.button>
            )
          })}
        </motion.div>
        <motion.button onClick={() => navigate('/browse')} whileTap={tapScale} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: 0,
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 12, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600, color: '#1F6F5C',
        }}>
          <Plus size={14} strokeWidth={2} /> Find more helpers
        </motion.button>
      </Section>
      </div>
      </motion.div>
    </Shell>
  )
}
