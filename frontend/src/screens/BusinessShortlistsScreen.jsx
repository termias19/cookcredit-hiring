/**
 * Shortlists (B2B) — the cooks starred across roles, a reusable talent pool decoupled from any
 * one posting. One action: open a candidate. Backed by the org shortlist in BusinessContext
 * (the assessed-candidate roster joined by id), persisted server-side.
 */
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Star, ShieldCheck } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useBusiness } from '../context/BusinessContext'
import { fadeUp, staggerContainer, tapScale } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C', GOLD = '#9A781E'

function ShortlistCard({ cook, onClick }) {
  return (
    <motion.button className="cc-business-card" layout variants={fadeUp} initial="hidden" animate="show" whileHover={{ borderColor: '#b2bdb6' }} whileTap={tapScale}
      exit={{ opacity: 0, scale: 0.92, transition: { duration: 0.2 } }}
      onClick={onClick} style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left', cursor: 'pointer',
        background: '#FEFDFB', border: '1px solid #E3E0D9', padding: 0, overflow: 'hidden',
      }}>
      <div style={{ width: '100%', height: 132, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: cook.photo ? `#EDE7DF url(${cook.photo}) center/cover` : '#EDE7DF' }}>
        {!cook.photo && <span style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 400, color: '#8e8272' }}>{(cook.name || '?').trim().charAt(0).toUpperCase()}</span>}
      </div>
      <div style={{ flex: 1, padding: '14px 16px 16px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <Star size={14} color={GOLD} fill={GOLD} strokeWidth={1.5} />
          <h3 style={{ fontFamily: SERIF, fontSize: 18, fontWeight: 500, color: '#1a1a1a', margin: 0 }}>{cook.name}</h3>
          {cook.hasVideo && <ShieldCheck size={14} color={GREEN} strokeWidth={2} />}
        </div>
        <p style={{ fontSize: 12, color: '#777', margin: 0 }}>{(cook.cuisines || []).join(' · ')}{cook.city ? ` · ${cook.city}` : ''}</p>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto', paddingTop: 12, borderTop: '1px solid #E7E2D8' }}>
          <span className="cc-evidence-pill">{cook.hasVideo ? 'Evidence ready' : 'Assessment pending'}</span>
          <span style={{ fontFamily: SERIF, fontSize: 18, fontWeight: 500, color: '#1a1a1a' }}>{cook.verifiedScore ?? '—'}<small style={{ fontSize: 9, color: '#70706b', marginLeft: 3 }}>/100</small></span>
        </div>
      </div>
    </motion.button>
  )
}

export default function BusinessShortlistsScreen({ embedded = false } = {}) {
  const navigate = useNavigate()
  const biz = useBusiness()
  const cooks = (biz?.shortlist || []).map(id => biz?.candidateById?.(id) || biz?.shortlistCandidates?.find(candidate => candidate.id === id)).filter(Boolean)

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
      <button onClick={() => navigate('/business/roles')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
        <ArrowLeft size={14} color="#999" strokeWidth={1.5} />
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>Workspace</span>
      </button>
      <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>Shortlist</h1>
    </div>
  )

  return (
    <BusinessShell embedded={embedded} header={embedded ? null : header} showNav={false}>
      <div style={{ padding: '24px 28px 36px' }}>
        {cooks.length > 0 && (
          <motion.div variants={staggerContainer()} initial="hidden" animate="show"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 240px), 1fr))', gap: 16 }}>
            <AnimatePresence initial={false}>
              {cooks.map(c => (
                <ShortlistCard key={c.id} cook={c} onClick={() => navigate(`/business/candidate/${c.id}${c.roleId ? `?role=${c.roleId}` : ''}`)} />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
        {biz?.loading && !cooks.length && <p style={{ color: '#74756f', fontSize: 13, padding: '30px 0', textAlign: 'center' }}>Loading shortlist…</p>}
        {!biz?.loading && biz?.error && !cooks.length && (
          <div style={{ padding: '30px 0', textAlign: 'center' }}>
            <p style={{ color: '#777', fontSize: 13, margin: '0 0 12px' }}>Couldn&rsquo;t load the shortlist — check your connection.</p>
            <button onClick={() => biz?.refresh?.()} style={{
              background: '#1a1a1a', color: '#fff', border: 'none', padding: '10px 20px',
              fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', cursor: 'pointer',
            }}>Retry</button>
          </div>
        )}
        {!biz?.loading && !biz?.error && !cooks.length && <p style={{ color: '#74756f', fontSize: 13, padding: '30px 0', textAlign: 'center' }}>No one shortlisted yet. Star candidates from any role to build a reusable pool.</p>}
      </div>
    </BusinessShell>
  )
}
