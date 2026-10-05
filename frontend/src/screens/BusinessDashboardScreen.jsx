/**
 * Business — Candidates (the assessed-candidate sourcing pool).
 *
 * When employment validation is enabled, cooks can be ranked by the transparent composite — verified skill primary, then
 * smoothed rating, gated+decayed proximity, service-category/role fit, availability, bucketed
 * experience, cold-start exposure; each card shows plain-language reason codes (transparent +
 * LL144 artifact). Star adds to the shared workspace shortlist. Search spans
 * name/city/service categories/bio/skills/certs.
 * (A per-business CONFIGURABLE ranking + a semantic/cosine search are the next layer — in design.)
 */
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search, ShieldCheck, Star, Video } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import MobileCandidateFeed from '../components/MobileCandidateFeed'
import useIsDesktop from '../hooks/useIsDesktop'
import { useBusiness } from '../context/BusinessContext'
import { rankCandidates } from '../utils/ranking'
import { searchCandidates } from '../utils/search'
import { fadeUp, staggerContainer, tapScale } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = 'var(--cc-forest)', GOLD = '#9A781E'

function Header({ q, setQ, embedded }) {
  return (
    <div style={{ background: 'var(--cc-surface)', borderBottom: '1px solid var(--cc-border)', padding: '20px 28px' }}>
      <span style={{ fontSize: 10, letterSpacing: 2.3, color: 'var(--cc-muted)', textTransform: 'uppercase', fontWeight: 500 }}>Knife skill assessment</span>
      {!embedded && <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: 'var(--cc-ink)', margin: '5px 0 16px' }}>Candidates</h1>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, border: '1px solid var(--cc-border)', background: '#FFF', padding: '11px 13px', maxWidth: 500, borderRadius: 2 }}>
        <Search size={17} color="var(--cc-muted)" strokeWidth={1.7} />
        <input type="search" aria-label="Search candidates" value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search by name, skill, or city"
          style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, color: 'var(--cc-ink)', background: 'transparent', padding: 0, borderRadius: 0 }} />
      </div>
    </div>
  )
}

function CandidateCard({ rank, cook, onClick, onStar, starred, rankingEnabled }) {
  const firstName = (cook.name || 'Candidate').trim().split(/\s+/)[0]
  return (
    <div style={{ position: 'relative' }}>
      <motion.button className="cc-business-card" variants={fadeUp} whileHover={{ borderColor: '#b2bdb6' }} whileTap={tapScale} onClick={onClick} style={{
        display: 'flex', flexDirection: 'column', width: '100%', textAlign: 'left', cursor: 'pointer',
        background: 'var(--cc-surface)', border: '1px solid var(--cc-border)', padding: 0, overflow: 'hidden',
      }}>
        <div style={{ width: '100%', height: 132, flexShrink: 0, position: 'relative',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: cook.photo ? `#EDE7DF url(${cook.photo}) center/cover` : '#EDE7DF' }}>
          {!cook.photo && <span style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 400, color: '#8e8272' }}>{(cook.name || '?').trim().charAt(0).toUpperCase()}</span>}
          {rankingEnabled && <span style={{ position: 'absolute', top: 8, left: 8, fontFamily: SERIF, fontSize: 13, letterSpacing: 1,
            color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '3px 8px' }}>{String(rank).padStart(2, '0')}</span>}
        </div>
        <div style={{ flex: 1, padding: '16px 17px 17px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <h3 style={{ fontFamily: SERIF, fontSize: 18, fontWeight: 500, color: 'var(--cc-ink)', margin: 0 }}>{cook.name}</h3>
            <Video size={14} color={GREEN} strokeWidth={2} aria-label="Shared assessment on file" />
          </div>
          <p style={{ fontSize: 12, color: 'var(--cc-muted)', margin: '2px 0 11px' }}>{(cook.cuisines || []).join(' · ')}{cook.years != null ? ` · ${cook.years} yrs` : ''}</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: rankingEnabled ? 9 : 14 }}>
            <span className="cc-evidence-pill">Shared assessment</span>
            {cook.hasVideo && <span className="cc-evidence-pill"><Video size={12} strokeWidth={2} />Recording ready</span>}
          </div>
          {rankingEnabled && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15, duration: 0.3 }}
            style={{ fontSize: 12, color: 'var(--cc-muted)', margin: '0 0 11px', lineHeight: 1.5 }}>{(cook._rank?.reasons || []).join(' · ')}</motion.p>}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 'auto', paddingTop: 12, borderTop: '1px solid #E7E2D8' }}>
            <span style={{ fontSize: 12, color: GREEN, fontWeight: 500 }}>Review {firstName}&rsquo;s evidence</span>
            <span style={{ display: 'inline-flex', alignItems: 'baseline', whiteSpace: 'nowrap' }}>
              <motion.span initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.3 }}
                style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 500, color: 'var(--cc-ink)', lineHeight: 1 }}>{cook.verifiedScore ?? '—'}</motion.span>
              <span style={{ fontSize: 9, color: 'var(--cc-muted)', letterSpacing: .6, textTransform: 'uppercase', marginLeft: 3 }}>{cook.verifiedScore == null ? 'Review' : '/100'}</span>
            </span>
          </div>
        </div>
      </motion.button>
      <motion.button whileTap={tapScale} onClick={onStar} aria-label={starred ? 'Remove from shortlist' : 'Add to shortlist'}
        style={{ position: 'absolute', top: 10, right: 10, zIndex: 1, background: 'rgba(255,253,248,0.94)', border: '1px solid rgba(36,49,41,.1)',
          borderRadius: '50%', width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0 }}>
        <motion.span key={starred ? 'starred' : 'unstarred'} initial={{ scale: 0.6, rotate: -20 }} animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 15 }} style={{ display: 'inline-flex' }}>
          <Star size={16} strokeWidth={1.5} color={starred ? GOLD : '#ccc'} fill={starred ? GOLD : 'none'} />
        </motion.span>
      </motion.button>
    </div>
  )
}

export default function BusinessDashboardScreen({ embedded = false } = {}) {
  const navigate = useNavigate()
  const biz = useBusiness()
  const [q, setQ] = useState('')
  const isDesktop = useIsDesktop()

  const rankingEnabled = biz?.screeningPolicy?.automaticRankingEnabled === true
  const rows = useMemo(() => {
    const roster = biz?.candidates || []
    const { results, relevanceById } = searchCandidates(q, roster)
    if (!rankingEnabled) return results
    const query = { loc: biz?.org?.loc || null, radiusM: 60000, relevance: relevanceById }
    return rankCandidates(results, query, { surface: 'b2b', rankConfig: biz?.rankConfig })
  }, [q, biz, rankingEnabled])

  const loading = biz?.loading
  const rosterEmpty = !loading && (biz?.candidates || []).length === 0

  if (!isDesktop && !loading && !rosterEmpty) {
    return <MobileCandidateFeed embedded={embedded} candidates={rows} query={q} onQueryChange={setQ} />
  }

  return (
    <BusinessShell embedded={embedded} header={<Header q={q} setQ={setQ} embedded={embedded} />}>
      <div style={{ padding: '22px 28px 36px' }}>
        {loading ? (
          <p style={{ textAlign: 'center', color: '#74756f', fontSize: 14, padding: '40px 0' }}>Loading candidates…</p>
        ) : biz?.error && rosterEmpty ? (
          <div style={{ textAlign: 'center', padding: '48px 16px' }}>
            <p style={{ fontFamily: SERIF, fontSize: 22, color: 'var(--cc-ink)', margin: '0 0 6px' }}>Couldn&rsquo;t load the workspace</p>
            <p style={{ fontSize: 13, color: '#777', margin: '0 0 16px' }}>Check your connection and retry.</p>
            <button onClick={() => biz?.refresh?.()} style={{
              background: 'var(--cc-ink)', color: '#fff', border: 'none', padding: '11px 24px',
              fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', cursor: 'pointer',
            }}>Retry</button>
          </div>
        ) : rosterEmpty ? (
          <div style={{ textAlign: 'center', padding: '48px 16px' }}>
            <ShieldCheck size={28} color="#cbb" strokeWidth={1.5} style={{ marginBottom: 12 }} />
            <p style={{ fontFamily: SERIF, fontSize: 22, color: 'var(--cc-ink)', margin: '0 0 6px' }}>No consenting applicants yet</p>
            <p style={{ fontSize: 13, color: '#74756f', margin: 0, lineHeight: 1.5 }}>
              Candidates appear here after they share a completed assessment with your company for a role.
            </p>
          </div>
        ) : (
          <>
            {!rankingEnabled && <div className="cc-business-notice" style={{ border: '1px solid #D7C99D', background: '#FCF8EC', padding: '12px 14px', marginBottom: 18, fontSize: 12, color: '#65561E', lineHeight: 1.55 }}>
              Shown in application order. Review the recording and measured results alongside experience and references. Automatic ranking is off while the assessment is being validated for hiring.
            </div>}
            <p style={{ fontSize: 10, letterSpacing: 1.8, color: 'var(--cc-muted)', textTransform: 'uppercase', fontWeight: 500, margin: '0 0 13px' }}>
              {rows.length} candidate{rows.length === 1 ? '' : 's'} · {rankingEnabled ? 'transparent job-related ranking' : 'application list'}
            </p>
            <motion.div variants={staggerContainer()} initial="hidden" animate="show"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 260px), 1fr))', gap: 18 }}>
              {rows.map((c, i) => (
                <CandidateCard key={c.id} rank={i + 1} cook={c} rankingEnabled={rankingEnabled}
                  onClick={() => navigate(`/business/candidate/${c.id}`)}
                  onStar={() => biz?.toggleShortlist?.(c.id)} starred={biz?.isShortlisted?.(c.id)} />
              ))}
            </motion.div>
            {rows.length === 0 && (
              <p style={{ textAlign: 'center', color: '#74756f', fontSize: 14, padding: '40px 0' }}>No candidates match “{q}”.</p>
            )}
          </>
        )}
      </div>
    </BusinessShell>
  )
}
