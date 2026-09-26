/**
 * Browse — clients discover verified helpers.
 *
 * Loads real, discoverable helpers (approved + skill_verified) from GET /api/cooks,
 * with client-side search + service-category filtering over the loaded set. Cards link to the
 * real /cook/:id profile. Honest empty state until helpers are verified + approved.
 */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search, MapPin, ShieldCheck } from 'lucide-react'
import Shell from '../components/Shell'
import { money } from '../utils/money'
import { tierColor } from '../utils/region'
import { getCooks } from '../utils/Api'
import { fadeUp, staggerContainer, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C'
const CUISINES = ['All', 'House Cleaning', 'Deep Cleaning', 'Cooking & Meal Prep', 'Laundry & Ironing', 'Childcare', 'Elder Care', 'Errands', 'Pet Care']

function Header({ q, setQ, cuisine, setCuisine, count }) {
  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show" style={{
      background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 20px',
    }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
          <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>Find a helper</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: '1px solid #e5e5e5', background: '#fff', padding: '11px 14px', width: 'min(360px, 100%)' }}>
            <Search size={16} color="#999" strokeWidth={1.5} />
            <input type="search" aria-label="Search helpers" value={q} onChange={e => setQ(e.target.value)} placeholder="Specialty, name, or city"
              style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, color: '#1a1a1a', background: 'transparent' }} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', WebkitOverflowScrolling: 'touch', paddingBottom: 2 }}>
            {CUISINES.map(c => (
              <motion.button key={c} onClick={() => setCuisine(c)} whileTap={tapScale} style={{
                flexShrink: 0, padding: '7px 15px', fontSize: 12, letterSpacing: 0.5, cursor: 'pointer',
                border: '1px solid', borderColor: cuisine === c ? '#1a1a1a' : '#e5e5e5',
                background: cuisine === c ? '#1a1a1a' : '#fff', color: cuisine === c ? '#fff' : '#555',
              }}>{c}</motion.button>
            ))}
          </div>
          {count != null && (
            <p style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: 0, whiteSpace: 'nowrap' }}>
              {count} verified helper{count === 1 ? '' : 's'}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  )
}

function CookCard({ cook, onClick }) {
  const tc = tierColor(cook.skillTier)
  const city = [cook.baseCity, cook.baseState].filter(Boolean).join(', ')
  return (
    <motion.button variants={fadeUp} whileHover={hoverLift} whileTap={tapScale} onClick={onClick} style={{
      display: 'flex', flexDirection: 'column', textAlign: 'left', cursor: 'pointer',
      background: '#fff', border: '1px solid #e5e5e5', padding: 0, overflow: 'hidden',
    }}>
      <div style={{ width: '100%', height: 168, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: cook.photoUrl ? `#eee url(${cook.photoUrl}) center/cover` : '#EDE7DF' }}>
        {!cook.photoUrl && <span style={{ fontFamily: SERIF, fontSize: 40, color: '#9a8c7a' }}>{(cook.name || '?').trim().charAt(0).toUpperCase()}</span>}
      </div>
      <div style={{ flex: 1, padding: '14px 16px 16px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <h3 style={{ fontFamily: SERIF, fontSize: 19, fontWeight: 500, color: '#1a1a1a', margin: 0 }}>{cook.name}</h3>
          <ShieldCheck size={15} color={tc} strokeWidth={2} />
        </div>
        <p style={{ fontSize: 11, letterSpacing: 1, color: tc, textTransform: 'uppercase', margin: '0 0 8px', fontWeight: 600 }}>
          {cook.skillTier ? `${cook.skillTier} verified` : 'verified'}{cook.skillScore != null ? ` · ${cook.skillScore}` : ''}
        </p>
        <p style={{ fontSize: 12, color: '#777', margin: '0 0 8px', minHeight: 16 }}>{(cook.cuisines || []).join(' · ')}</p>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto', paddingTop: 8 }}>
          {city ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#999' }}>
              <MapPin size={13} strokeWidth={1.5} /> {city}
            </div>
          ) : <span />}
          {cook.pricePerHour != null && (
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <span style={{ fontFamily: SERIF, fontSize: 20, color: '#1a1a1a' }}>{money(cook.pricePerHour)}</span>
              <span style={{ fontSize: 10, color: '#aaa', letterSpacing: 0.5 }}> / hr</span>
            </div>
          )}
        </div>
      </div>
    </motion.button>
  )
}

/** Skeleton placeholder shaped like a CookCard, shown while helpers load. */
function CookCardSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', background: '#fff', border: '1px solid #e5e5e5', overflow: 'hidden' }}>
      <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 1.4 }}
        style={{ width: '100%', height: 168, background: '#EDE7DF' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 16px 16px' }}>
        <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 1.4 }}
          style={{ width: '60%', height: 16, background: '#eee' }} />
        <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 1.4, delay: 0.1 }}
          style={{ width: '40%', height: 11, background: '#eee' }} />
        <motion.div animate={{ opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 1.4, delay: 0.2 }}
          style={{ width: '80%', height: 11, background: '#eee' }} />
      </div>
    </div>
  )
}

export default function BrowseScreen() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [cuisine, setCuisine] = useState('All')
  const [all, setAll] = useState([])
  const [status, setStatus] = useState('loading')   // loading | ready | error

  useEffect(() => {
    let live = true
    getCooks({ perPage: 50 })
      .then(d => { if (!live) return; setAll(Array.isArray(d?.cooks) ? d.cooks : []); setStatus('ready') })
      .catch(() => { if (live) setStatus('error') })
    return () => { live = false }
  }, [])

  const cooks = useMemo(() => {
    const term = q.trim().toLowerCase()
    return all.filter(c => {
      const cu = (c.cuisines || []).map(x => x.toLowerCase())
      const matchC = cuisine === 'All' || cu.some(x => x.includes(cuisine.toLowerCase()))
      const city = [c.baseCity, c.baseState].filter(Boolean).join(', ').toLowerCase()
      const matchQ = !term || (c.name || '').toLowerCase().includes(term) || city.includes(term)
        || cu.some(x => x.includes(term))
      return matchC && matchQ
    })
  }, [q, cuisine, all])

  const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 20 }

  return (
    <Shell wide header={<Header q={q} setQ={setQ} cuisine={cuisine} setCuisine={setCuisine} count={status === 'ready' ? cooks.length : null} />}>
      <div style={{ padding: '24px 0 20px' }}>
        {status === 'loading' ? (
          <div style={grid}>
            <CookCardSkeleton /><CookCardSkeleton /><CookCardSkeleton /><CookCardSkeleton />
          </div>
        ) : status === 'error' ? (
          <motion.p variants={fadeUp} initial="hidden" animate="show" style={{ textAlign: 'center', color: '#767676', fontSize: 14, padding: '60px 0' }}>Couldn’t load helpers. Pull to refresh.</motion.p>
        ) : all.length === 0 ? (
          <motion.div variants={fadeUp} initial="hidden" animate="show" style={{ textAlign: 'center', padding: '72px 16px' }}>
            <ShieldCheck size={28} color={GREEN} strokeWidth={1.5} style={{ marginBottom: 12, opacity: 0.5 }} />
            <p style={{ fontFamily: SERIF, fontSize: 24, color: '#1a1a1a', margin: '0 0 6px' }}>No verified helpers yet</p>
            <p style={{ fontSize: 13, color: '#999', margin: '0 auto', lineHeight: 1.5, maxWidth: 420 }}>
              Helpers appear here once they pass ID verification and a background check and are approved. Check back soon.
            </p>
          </motion.div>
        ) : (
          <>
            <motion.div key={cuisine + q} variants={staggerContainer(0.05, 0.02)} initial="hidden" animate="show" style={grid}>
              {cooks.map(c => <CookCard key={c.id} cook={c} onClick={() => navigate(`/cook/${c.id}`)} />)}
            </motion.div>
            {cooks.length === 0 && (
              <p style={{ textAlign: 'center', color: '#999', fontSize: 14, padding: '60px 0' }}>
                No helpers match that. Try another category or search.
              </p>
            )}
          </>
        )}
      </div>
    </Shell>
  )
}
