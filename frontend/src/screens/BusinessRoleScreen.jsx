/**
 * Role workspace (B2B) — the unified Role object: the scorecard, the candidate pipeline, and the
 * shortlist on one screen. Applications remain in submission order while employment validation is
 * incomplete; the recorded work sample is evidence for a person to review, never an automatic rank.
 */
import { useState, useEffect, useRef } from 'react'
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
const roleAction = { border: '1px solid #1F6F5C', color: GREEN, background: 'transparent', padding: '10px 16px', marginRight: 12, borderRadius: 2, cursor: 'pointer', fontFamily: 'inherit' }
const STAGES = ['invited', 'assessing', 'verified', 'shortlisted', 'contacted', 'hired', 'not_selected']
// Keep the persisted stage key; a workflow position does not certify the evidence.
const stageLabel = stage => stage === 'verified' ? 'Ready for review' : stage.replaceAll('_', ' ')
const bandColor = b => (b === 'Gated' ? TERRA : b === 'Strong fit' || b === 'Qualified' ? GREEN : GOLD)

export default function BusinessRoleScreen() {
  const { id } = useParams()
  const navigate = useNavigate()
  const biz = useBusiness()
  const [invited, setInvited] = useState(false)
  const [copyError, setCopyError] = useState('')
  const [changingStatus, setChangingStatus] = useState(false)
  const [confirmTrash, setConfirmTrash] = useState(false)
  const [statusError, setStatusError] = useState('')
  const [data, setData] = useState({ role: null, pipeline: [], applications: [], status: 'loading' })
  const [filters, setFilters] = useState({ status: '', city: '', outcome: '' })
  const [nextCursor, setNextCursor] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)

  const requestVersion = useRef(0)
  const [reloadKey, setReloadKey] = useState(0)
  const [loadError, setLoadError] = useState('')

  // The pipeline is owned by THIS screen (not the global store): each card carries the server's
  // frozen match snapshot, so we render the audited numbers rather than recomputing client-side.
  // Depend on the STABLE getToken (memoized in the context), never the whole `biz` value object —
  // that object is recreated every provider render, which would re-fire the fetch.
  // Invalidate pending pagination whenever the role or selected filters change.
  const getToken = biz?.getToken
  useEffect(() => {
    const version = ++requestVersion.current
    let live = true
    setData(d => ({ ...d, role: d.role?.id === id ? d.role : null, pipeline: [], applications: [], status: 'loading' }))
    setNextCursor(null); setLoadingMore(false); setLoadError('')
    ;(async () => {
      try {
        const token = getToken ? await getToken() : null
        if (!token) throw new Error('Sign in again to load applications.')
        const [res, applicationResult] = await Promise.all([
          getBusinessRole({ token, id }),
          getHiringApplications({ token, roleId: id, status: filters.status, city: filters.city, outcome: filters.outcome }),
        ])
        if (!live || version !== requestVersion.current) return
        setData({
          role: res?.role || null,
          pipeline: Array.isArray(res?.pipeline) ? res.pipeline : [],
          applications: Array.isArray(applicationResult?.applications) ? applicationResult.applications : [],
          status: res?.role ? 'ready' : 'notfound',
        })
        setNextCursor(applicationResult?.page?.nextCursor || null)
      } catch {
        if (!live || version !== requestVersion.current) return
        setData(d => ({ ...d, status: 'error' }))
        setLoadError('Applications could not be loaded. Retry to see current results.')
      }
    })()
    return () => { live = false; requestVersion.current += 1 }
  }, [id, getToken, filters.status, filters.city, filters.outcome, reloadKey])

  async function loadMore() {
    if (!nextCursor || loadingMore || data.status !== 'ready') return
    const version = requestVersion.current
    setLoadingMore(true); setLoadError('')
    try {
      const token = await getToken()
      if (!token) throw new Error('Sign in again.')
      const result = await getHiringApplications({ token, roleId: id, status: filters.status, city: filters.city, outcome: filters.outcome, cursor: nextCursor })
      if (version !== requestVersion.current) return
      setData(current => {
        const existing = new Set(current.applications.map(application => application.id))
        return { ...current, applications: [...current.applications, ...(result.applications || []).filter(application => !existing.has(application.id))] }
      })
      setNextCursor(result?.page?.nextCursor || null)
    } catch {
      if (version === requestVersion.current) setLoadError('More applications could not be loaded. Use Load more applications to retry.')
    } finally { if (version === requestVersion.current) setLoadingMore(false) }
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
  if (data.status === 'error' && !role) return <BusinessShell header={header} showNav={false}><div style={{ padding: 28 }}><p role="alert">{loadError}</p><button onClick={() => setReloadKey(key => key + 1)}>Retry</button></div></BusinessShell>
  if (data.status === 'notfound') return <BusinessShell header={header} showNav={false}><p style={{ textAlign: 'center', color: '#74756f', padding: '60px 20px' }}>Role not found.</p></BusinessShell>

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
  async function changeStatus(target) {
    if (changingStatus) return
    setChangingStatus(true); setStatusError('')
    try {
      const token = await getToken()
      const result = await changeBusinessRoleStatus({ token, id, status: target })
      setData(current => ({ ...current, role: result.role }))
      setConfirmTrash(false)
      biz?.refresh?.()
    } catch (error) { setStatusError(error.message || 'Could not update this role. Please retry.') }
    finally { setChangingStatus(false) }
  }
  const withdrawn = cards.filter(card => card.stage === 'withdrawn')
  const visibleStages = STAGES.filter(stage => cards.some(card => card.stage === stage))

  return (
    <BusinessShell header={header} showNav={false}>
      {/* requirements scorecard */}
      <motion.div initial="hidden" animate="show" variants={fadeUp} style={{ padding: '22px 28px 8px' }}>
        <details><summary style={{ color: GREEN, cursor: 'pointer', fontSize: 13, marginBottom: 12 }}>Role requirements</summary>
        <motion.div variants={staggerContainer(0.04)} initial="hidden" animate="show" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {(role?.certsRequired || []).map(idr => (
            <motion.span key={idr} variants={scaleIn} style={chip(true)}>{labelOf(idr)} · required</motion.span>
          ))}
          {Object.entries(role?.assessmentCriteria || {}).filter(([key]) => key !== 'profileVersion').map(([key, value]) => <span key={key} style={chip(true)}>{key.replace(/^(minimum|maximum)/, '').replace('Cadence', 'Pace')} {key.startsWith('maximum') ? '≤' : '≥'} {value}{key.endsWith('Cadence') ? ' strokes/s' : ' / 100'}</span>)}
          {!role?.assessmentCriteria?.profileVersion && role?.skillFloor != null && <motion.span variants={scaleIn} style={chip(true)}>Verified ≥ {role.skillFloor}</motion.span>}
          {(role?.required || []).map(idr => <motion.span key={idr} variants={scaleIn} style={chip(true)}>{labelOf(idr)}</motion.span>)}
          {(role?.preferred || []).map(idr => <motion.span key={idr} variants={scaleIn} style={chip(false)}>{labelOf(idr)} · nice-to-have</motion.span>)}
        </motion.div>
        </details>
        <p role="status" style={{ fontSize: 13, color: GREEN, marginTop: 14 }}>
          {role.status === 'trashed' ? 'In trash. The application link is closed; applications and recordings are preserved.' : role.status === 'open' ? 'Open for applications' : 'Closed to new applications and assessment submissions. Existing applications remain available for review.'}
        </p>
        {!role.integrationManaged && <button type="button" disabled={changingStatus} onClick={() => changeStatus(role.status === 'trashed' || role.status === 'open' ? 'closed' : 'open')}
          style={{ border: '1px solid #1F6F5C', color: GREEN, background: 'transparent', padding: '10px 16px', cursor: changingStatus ? 'wait' : 'pointer', marginRight: 12 }}>
          {changingStatus ? 'Saving…' : role.status === 'trashed' ? 'Restore role (closed)' : role.status === 'open' ? 'Close role' : 'Reopen role'}
        </button>}
        {!role.integrationManaged && role.status !== 'trashed' && <>
          <button type="button" onClick={() => navigate(`/business/role/${id}/edit`)} style={roleAction}>Edit role</button>
          <button type="button" disabled={changingStatus} onClick={() => setConfirmTrash(true)} style={roleAction}>Move to trash</button>
          {confirmTrash && <div role="group" aria-label="Confirm move to trash"><p>This closes the application link. Existing applications and recordings stay available. You can restore the role from Trash.</p>
            <button style={roleAction} disabled={changingStatus} onClick={() => changeStatus('trashed')}>Confirm move to trash</button>
            <button style={roleAction} disabled={changingStatus} onClick={() => setConfirmTrash(false)}>Cancel</button>
          </div>}
        </>}
        {statusError && <p role="alert" style={{ color: TERRA }}>{statusError}</p>}
        <motion.button {...buttonPress} onClick={async () => {
            const link = `${window.location.origin}/apply/${role.id}`
            setInvited(false); setCopyError('')
            try { await navigator.clipboard.writeText(link); setInvited(true) }
            catch { setCopyError('Could not copy automatically. Select and copy the application link below.') }
          }} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, marginTop: 14,
          background: GREEN, color: '#fff', border: 'none', borderRadius: 2, padding: '11px 16px', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
          <Link2 size={15} strokeWidth={1.5} /> {invited ? 'Application link copied' : 'Copy application link'}
        </motion.button>
        {copyError && <div><p role="alert" style={{ fontSize: 12, color: TERRA }}>{copyError}</p><input aria-label="Application link" readOnly value={`${window.location.origin}/apply/${role.id}`} style={{ width: '100%', maxWidth: 620, padding: 10 }} onFocus={event => event.target.select()} /></div>}
        {invited && <p style={{ fontSize: 11, color: '#74756f', margin: '8px 0 0' }}>Applicants see this role, answer your configured questions, share approximate location, and then open the existing CookCredit assessment.</p>}
        <p style={{ fontSize: 12, color: '#777', lineHeight: 1.5, margin: '12px 0 0', maxWidth: 720 }}>Applications stay in submission order. CookCredit shows the recorded measurements, limitations, and attempt history; a person reviews the evidence and makes the hiring decision.</p>
      </motion.div>

      {/* pipeline — a Kanban board, one column per stage, so the workspace can scan the whole
          funnel at once instead of scrolling one long stacked list */}
      <div style={{ padding: '16px 28px 36px' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '4px 0 8px' }}>Pipeline · {cards.length}</p>
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
        {data.status === 'loading' && <p role="status">Loading applications…</p>}
        {loadError && <div><p role="alert" style={{ color: TERRA }}>{loadError}</p>{data.status === 'error' && <button onClick={() => setReloadKey(key => key + 1)}>Retry</button>}</div>}
        <div className="cc-pipeline" tabIndex={0} role="region" aria-label="Hiring pipeline">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 12, alignItems: 'start', width: '100%' }}>
          {visibleStages.map(stage => {
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
                            <motion.button whileTap={tapScale} onClick={() => biz.toggleShortlist(c.cookId)} aria-label="Shortlist" aria-pressed={starred}
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
        {data.status === 'ready' && !cards.length && <p style={{ color: '#74756f', fontSize: 13, padding: '20px 0' }}>{filters.status || filters.city || filters.outcome ? 'No applications match these filters.' : 'No candidates yet — invite cooks to assess for this role.'}</p>}
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
