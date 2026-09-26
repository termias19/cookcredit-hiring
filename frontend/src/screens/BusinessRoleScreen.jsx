/**
 * Role workspace (B2B) — the unified Role object: the scorecard, the candidate pipeline, and the
 * shortlist on one screen. Applications remain in submission order while employment validation is
 * incomplete; the recorded work sample is evidence for a person to review, never an automatic rank.
 */
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Star, ShieldCheck, Link2, ChevronRight, Video } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import PlaybackViewControl from '../components/PlaybackViewControl'
import HiringCvDownload from '../components/HiringCvDownload'
import { useBusiness } from '../context/BusinessContext'
import { labelOf } from '../data/culinaryTaxonomy'
import { getBusinessRole, getHiringApplications, changeBusinessRoleStatus } from '../utils/Api'
import { fadeUp, scaleIn, staggerContainer, tapScale, buttonPress } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C', GOLD = '#9A781E', TERRA = '#C4561F'
const STAGES = ['invited', 'assessing', 'verified', 'shortlisted', 'contacted', 'hired', 'not_selected']
// Keep the persisted stage key; a workflow position does not certify the evidence.
const stageLabel = stage => stage === 'verified' ? 'Ready for review' : stage.replaceAll('_', ' ')
const bandColor = b => (b === 'Gated' ? TERRA : b === 'Strong fit' || b === 'Qualified' ? GREEN : GOLD)

export default function BusinessRoleScreen() {
  const { id } = useParams()
  const navigate = useNavigate()
  const biz = useBusiness()
  const [invited, setInvited] = useState(false)
  const [changingStatus, setChangingStatus] = useState(false)
  const [statusError, setStatusError] = useState('')
  const [data, setData] = useState({ role: null, pipeline: [], applications: [], status: 'loading' })
  const [filters, setFilters] = useState({ status: '', city: '', outcome: '' })
  const [nextCursor, setNextCursor] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)

  // The pipeline is owned by THIS screen (not the global store): each card carries the server's
  // frozen match snapshot, so we render the audited numbers rather than recomputing client-side.
  // Depend on the STABLE getToken (memoized in the context), never the whole `biz` value object —
  // that object is recreated every provider render, which would re-fire the fetch. All setData
  // calls sit past an await (no synchronous setState in the effect → no cascading renders).
  const getToken = biz?.getToken
  useEffect(() => {
    let live = true
    ;(async () => {
      const token = getToken ? await getToken() : null
      if (!token) { if (live) setData(d => ({ ...d, status: 'error' })); return }
      try {
        const [res, applicationResult] = await Promise.all([
          getBusinessRole({ token, id }),
          getHiringApplications({ token, roleId: id, status: filters.status, city: filters.city, outcome: filters.outcome }),
        ])
        if (!live) return
        setData({
          role: res?.role || null,
          pipeline: Array.isArray(res?.pipeline) ? res.pipeline : [],
          applications: Array.isArray(applicationResult?.applications) ? applicationResult.applications : [],
          status: res?.role ? 'ready' : 'notfound',
        })
        setNextCursor(applicationResult?.page?.nextCursor || null)
      } catch {
        if (live) setData(d => ({ ...d, status: 'error' }))
      }
    })()
    return () => { live = false }
  }, [id, getToken, filters.status, filters.city, filters.outcome])

  async function loadMore() {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const token = await getToken()
      const result = await getHiringApplications({ token, roleId: id, status: filters.status, city: filters.city, outcome: filters.outcome, cursor: nextCursor })
      setData(current => ({ ...current, applications: [...current.applications, ...(result.applications || [])] }))
      setNextCursor(result?.page?.nextCursor || null)
    } finally { setLoadingMore(false) }
  }

  // Use the fetched role; fall back to the list summary for the title while the detail loads.
  const role = data.role || biz?.roleById?.(id) || null

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
      <button onClick={() => navigate('/business/roles')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
        <ArrowLeft size={14} color="#999" strokeWidth={1.5} />
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>Roles</span>
      </button>
      <h1 style={{ fontFamily: SERIF, fontSize: 32, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>{role?.title || 'Role'}</h1>
    </div>
  )

  if (data.status === 'loading' && !role) return <BusinessShell header={header} showNav={false}><p style={{ textAlign: 'center', color: '#74756f', padding: '60px 20px' }}>Loading…</p></BusinessShell>
  if (data.status === 'notfound' || (!role && data.status !== 'loading')) return <BusinessShell header={header} showNav={false}><p style={{ textAlign: 'center', color: '#74756f', padding: '60px 20px' }}>Role not found.</p></BusinessShell>

  const pipelineByCook = new Map(data.pipeline.map(card => [card.cookId, card]))
  const cards = data.applications.length || filters.status || filters.city || filters.outcome
    ? data.applications.map(application => {
      const cookId = application.candidate?.id
      const pipeline = pipelineByCook.get(cookId) || {}
      const stage = application.status === 'withdrawn' ? 'withdrawn'
        : ['verified', 'shortlisted', 'contacted', 'hired', 'not_selected'].includes(pipeline.stage) ? pipeline.stage
        : application.status === 'ready' ? 'verified' : 'assessing'
      return {
        ...pipeline, cookId, stage, application,
        cook: { ...(biz?.candidateById?.(cookId) || {}), name: application.candidate?.name || 'Applicant', verifiedScore: application.bestAssessment?.score },
        hasVideo: Boolean(application.bestAssessment),
      }
    })
    : data.pipeline.map(card => ({ ...card, cook: biz?.candidateById?.(card.cookId) || null }))
  async function changeStatus() {
    if (changingStatus) return
    setChangingStatus(true); setStatusError('')
    try {
      const token = await getToken()
      const result = await changeBusinessRoleStatus({ token, id, status: role.status === 'open' ? 'closed' : 'open' })
      setData(current => ({ ...current, role: result.role }))
      biz?.refresh?.()
    } catch (error) { setStatusError(error.message || 'Could not update this role. Please retry.') }
    finally { setChangingStatus(false) }
  }
  const withdrawn = cards.filter(card => card.stage === 'withdrawn')

  return (
    <BusinessShell header={header} showNav={false}>
      {/* requirements scorecard */}
      <motion.div initial="hidden" animate="show" variants={fadeUp} style={{ padding: '22px 28px 8px' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '0 0 8px' }}>Requirements</p>
        <motion.div variants={staggerContainer(0.04)} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {(role?.certsRequired || []).map(idr => (
            <motion.span key={idr} variants={scaleIn} style={chip(true)}>{labelOf(idr)} · required</motion.span>
          ))}
          {Object.entries(role?.assessmentCriteria || {}).filter(([key]) => key !== 'profileVersion').map(([key, value]) => <span key={key} style={chip(true)}>{key.replace(/^(minimum|maximum)/, '').replace('Cadence', 'Pace')} {key.startsWith('maximum') ? '≤' : '≥'} {value}{key.endsWith('Cadence') ? ' strokes/s' : ' / 100'}</span>)}
          {!role?.assessmentCriteria?.profileVersion && role?.skillFloor != null && <motion.span variants={scaleIn} style={chip(true)}>Verified ≥ {role.skillFloor}</motion.span>}
          {(role?.required || []).map(idr => <motion.span key={idr} variants={scaleIn} style={chip(true)}>{labelOf(idr)}</motion.span>)}
          {(role?.preferred || []).map(idr => <motion.span key={idr} variants={scaleIn} style={chip(false)}>{labelOf(idr)} · nice-to-have</motion.span>)}
        </motion.div>
        <p role="status" style={{ fontSize: 13, color: GREEN, marginTop: 14 }}>
          {role.status === 'open' ? 'Open for applications' : 'Closed to new applications and assessment submissions. Existing applications remain available for review.'}
        </p>
        {!role.integrationManaged && <button type="button" disabled={changingStatus} onClick={changeStatus}
          style={{ border: '1px solid #1F6F5C', color: GREEN, background: 'transparent', padding: '10px 16px', cursor: changingStatus ? 'wait' : 'pointer', marginRight: 12 }}>
          {changingStatus ? 'Saving…' : role.status === 'open' ? 'Close role' : 'Reopen role'}
        </button>}
        {statusError && <p role="alert" style={{ color: TERRA }}>{statusError}</p>}
        <motion.button {...buttonPress} onClick={async () => {
            const link = `${window.location.origin}/apply/${role.id}`
            try { await navigator.clipboard.writeText(link) } catch { /* clipboard unavailable */ }
            setInvited(true)
          }} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, marginTop: 14,
          background: GREEN, color: '#fff', border: 'none', borderRadius: 2, padding: '11px 16px', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
          <Link2 size={15} strokeWidth={1.5} /> {invited ? 'Application link copied' : 'Copy application link'}
        </motion.button>
        {invited && <p style={{ fontSize: 11, color: '#74756f', margin: '8px 0 0' }}>Applicants see this role, answer your configured questions, share approximate location, and then open the existing CookCredit assessment.</p>}
        <p style={{ fontSize: 12, color: '#777', lineHeight: 1.5, margin: '12px 0 0', maxWidth: 720 }}>Applications stay in submission order. CookCredit shows the recorded measurements, limitations, and attempt history; a person reviews the evidence and makes the hiring decision.</p>
      </motion.div>

      {/* pipeline — a Kanban board, one column per stage, so the workspace can scan the whole
          funnel at once instead of scrolling one long stacked list */}
      <div style={{ padding: '16px 28px 36px' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '4px 0 8px' }}>Pipeline · {cards.length}</p>
        <ol aria-label="Hiring stages" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 20px', listStyle: 'none', padding: '0 0 14px', margin: 0, fontSize: 12, color: '#70706b' }}>
          {STAGES.map((stage, index) => <li key={stage} style={{ textTransform: 'capitalize' }}><span style={{ color: GREEN, marginRight: 6 }}>{index + 1}.</span>{stageLabel(stage)}</li>)}
        </ol>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
          <select aria-label="Filter application status" value={filters.status} onChange={event => setFilters(current => ({ ...current, status: event.target.value }))} style={filterField}>
            <option value="">All statuses</option><option value="assessment_required">Assessment required</option><option value="assessment_processing">Processing</option><option value="ready">Ready for review</option><option value="withdrawn">Withdrawn</option>
          </select>
          <select aria-label="Filter assessment outcome" value={filters.outcome} onChange={event => setFilters(current => ({ ...current, outcome: event.target.value }))} style={filterField}>
            <option value="">All assessment results</option><option value="demonstrated">Meets threshold</option><option value="not_demonstrated">Below threshold / technique not demonstrated</option><option value="review_required">Needs evidence review</option>
          </select>
          <PlaybackViewControl />
            <input aria-label="Filter by applicant city" value={filters.city} onChange={event => setFilters(current => ({ ...current, city: event.target.value }))} placeholder="Filter city" style={filterField} />
        </div>
        <div className="cc-pipeline" tabIndex={0} role="region" aria-label="Hiring pipeline">
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${STAGES.length}, minmax(190px, 1fr))`, gap: 12, alignItems: 'start', minWidth: 1180 }}>
          {STAGES.map(stage => {
            const inStage = cards.filter(c => c.stage === stage)
            return (
              <motion.div key={stage} layout initial="hidden" animate="show" variants={fadeUp}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.4, color: '#70706b', textTransform: 'uppercase', marginBottom: 9, padding: '0 4px 7px', borderBottom: '1px solid #E3E0D9' }}>{stageLabel(stage)} · {inStage.length}</div>
                <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show">
                  {!inStage.length && <div style={{ border: '1px dashed #ddd4c7', color: '#a09689', padding: '16px 10px', fontSize: 11, textAlign: 'center' }}>No candidates</div>}
                  <AnimatePresence initial={false}>
                    {inStage.map(c => {
                      const m = c.match || {}
                      const starred = biz.isShortlisted(c.cookId)
                      const canOpenApplication = Boolean(c.application && c.application.status !== 'withdrawn')
                      const canOpenEvidence = Boolean(c.application?.bestAssessment || c.application?.latestAssessment || c.hasVideo)
                      return (
                        <motion.div className="cc-business-card" key={c.cookId} layout variants={fadeUp} initial="hidden" animate="show" whileHover={{ borderColor: '#b2bdb6' }} exit={{ opacity: 0, x: -16, transition: { duration: 0.18 } }}
                          style={{ display: 'flex', flexDirection: 'column', gap: 8, border: '1px solid #E3E0D9', background: '#FEFDFB', padding: 13, marginBottom: 9 }}>
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                            <motion.button whileTap={tapScale} onClick={() => biz.toggleShortlist(c.cookId)} aria-label="Shortlist"
                              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, flexShrink: 0, marginTop: 2 }}>
                              <motion.span key={starred ? 'starred' : 'unstarred'} initial={{ scale: 0.6, rotate: -20 }} animate={{ scale: 1, rotate: 0 }}
                                transition={{ type: 'spring', stiffness: 400, damping: 15 }} style={{ display: 'inline-flex' }}>
                                <Star size={17} strokeWidth={1.5} color={starred ? GOLD : '#ccc'} fill={starred ? GOLD : 'none'} />
                              </motion.span>
                            </motion.button>
                            <motion.button whileTap={canOpenApplication || canOpenEvidence ? tapScale : undefined} onClick={() => (canOpenApplication || canOpenEvidence) && navigate(`/business/candidate/${c.cookId}?role=${role.id}`)} style={{ flex: 1, minWidth: 0, textAlign: 'left', background: 'none', border: 'none', cursor: canOpenApplication || canOpenEvidence ? 'pointer' : 'default', padding: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ fontFamily: SERIF, fontSize: 17, fontWeight: 500, color: '#1a1a1a' }}>{c.cook?.name || 'Candidate'}</span>
                                {canOpenEvidence && <ShieldCheck size={13} color={GREEN} strokeWidth={2} />}
                                {c.hasVideo && <Video size={12} color="#aaa" strokeWidth={1.5} aria-label="Has skill video" />}
                              </div>
                              <div style={{ fontSize: 11, color: c.application ? (c.application.status === 'ready' ? GREEN : GOLD) : bandColor(m.band), fontWeight: 600, marginTop: 2 }}>
                                {c.application ? `${c.application.status.replaceAll('_', ' ')} · ${c.application.attemptsCompleted}/${c.application.attemptLimit} tries completed` : m.band === 'Gated'
                                  ? `Not eligible — ${m.gates?.failures?.[0] || 'requirement not met'}`
                                  : `${m.band || 'Reviewing'}${m.reqTotal != null ? ` · ${m.reqMet}/${m.reqTotal} requirements` : ''}`}
                              </div>
                            </motion.button>
                            {canOpenEvidence && <ChevronRight size={15} color="#ccc" strokeWidth={1.5} style={{ flexShrink: 0, marginTop: 2 }} />}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, paddingLeft: 25 }}>
                            <motion.span initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.3 }}
                              style={{ fontFamily: SERIF, fontSize: 18, color: '#1a1a1a', lineHeight: 1 }}>{c.cook?.verifiedScore ?? '—'}</motion.span>
                            <span style={{ fontSize: 9, color: '#74756f', letterSpacing: 1, textTransform: 'uppercase' }}>{canOpenEvidence ? 'recorded result' : 'awaiting result'}</span>
                          </div>
                          {c.application?.hasCv && <HiringCvDownload applicationId={c.application.id} getToken={getToken} />}
                          {c.application?.location?.city && <p style={{ margin: '0 0 0 25px', color: '#777', fontSize: 11 }}>{c.application.location.city}{c.application.location.lat != null ? ' · approximate location shared' : ''}</p>}
                          {c.application?.questions?.length > 0 && <details style={{ marginLeft: 25, fontSize: 11, color: '#666' }}><summary style={{ cursor: 'pointer' }}>Application answers</summary><div style={{ paddingTop: 7, display: 'grid', gap: 6 }}>{c.application.questions.map(question => <div key={question.id}><strong>{question.label}</strong><br />{Array.isArray(c.application.answers?.[question.id]) ? c.application.answers[question.id].join(', ') : String(c.application.answers?.[question.id] ?? 'Not answered')}</div>)}</div></details>}
                        </motion.div>
                      )
                    })}
                  </AnimatePresence>
                </motion.div>
              </motion.div>
            )
          })}
        </div>
        </div>
        {withdrawn.length > 0 && <details style={{ borderTop: '1px solid #e7dfd3', marginTop: 12, paddingTop: 12 }}><summary style={{ cursor: 'pointer', color: '#786f65', fontSize: 12 }}>Archived · {withdrawn.length} withdrawn</summary><p style={{ color: '#968d83', fontSize: 11, margin: '8px 0 0' }}>Withdrawn applicants remain in the audit history and outside the active six-stage pipeline.</p></details>}
        {!cards.length && <p style={{ color: '#74756f', fontSize: 13, padding: '20px 0' }}>No candidates yet — invite cooks to assess for this role.</p>}
        {nextCursor && <button onClick={loadMore} disabled={loadingMore} style={{ border: '1px solid #1a1a1a', background: '#fff', color: '#1a1a1a', padding: '10px 16px', cursor: 'pointer' }}>{loadingMore ? 'Loading…' : 'Load more applications'}</button>}
      </div>
    </BusinessShell>
  )
}

const chip = (solid) => ({
  border: `1px solid ${solid ? '#1a1a1a' : '#e5e5e5'}`,
  background: solid ? '#1a1a1a' : '#fff', color: solid ? '#fff' : '#777',
  padding: '4px 10px', fontSize: 11, letterSpacing: 0.3,
})
const filterField = { border: '1px solid #E3E0D9', background: '#fff', color: '#1a1a1a', borderRadius: 2, padding: '9px 11px', fontSize: 12, minWidth: 170 }
