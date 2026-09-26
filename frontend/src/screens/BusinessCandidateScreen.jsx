/**
 * Candidate report (B2B) — a candidate's full profile for a business: recorded assessment result, the submitted skill VIDEO, an About/description, their résumé key-points (skills,
 * certifications, service specialties, experience), and — when reached from a role (?role=) — the
 * transparent match + the claim↔camera-truth reconciliation. No marketing tier scheme. Shortlist
 * writes to the shared workspace store. Gated to the business workspace (under BusinessRoute).
 */
import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, ShieldCheck, Check, CircleAlert, PlayCircle, Star, FileText } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import EmployerApplicationReview from '../components/EmployerApplicationReview'
import CandidateVideoPlayer from '../components/CandidateVideoPlayer'
import { reconcileClaims } from '../utils/match'
import { labelOf, nodeById } from '../data/culinaryTaxonomy'
import { credentialDetails } from '../utils/accreditation'
import { useAuth } from '../context/AuthContext'
import { useBusiness } from '../context/BusinessContext'
import { getCandidateReport, getCandidateVideo } from '../utils/Api'
import { reportPlayback } from '../utils/reportPlayback'
import { fadeUp, scaleIn, staggerContainer, buttonPress } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C', TERRA = '#C4561F', GOLD = '#9A781E'
const overline = { fontSize: 10, letterSpacing: 2, color: '#70706b', fontWeight: 500, textTransform: 'uppercase', margin: '0 0 8px' }
const CAT_LABEL = { certification: 'Certifications', technique: 'Technique & skill', cuisine: 'Cuisines',
  station: 'Experience & work arrangement', food_safety: 'Safety & protocol', server_skill: 'Service', barista_skill: 'Specialty service',
  dish_skill: 'Kitchen tasks', alcohol_cert: 'State certifications', pos: 'Scheduling', soft: 'Strengths' }
const CAT_ORDER = ['certification', 'technique', 'cuisine', 'station', 'food_safety', 'server_skill', 'barista_skill', 'dish_skill', 'alcohol_cert', 'pos', 'soft']

export default function BusinessCandidateScreen() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const roleId = params.get('role')
  // A route change must not retain another candidate's report or pending video.
  return <CandidateReport key={JSON.stringify([id, roleId])} id={id} roleId={roleId} />
}

function CandidateReport({ id, roleId }) {
  const navigate = useNavigate()
  const [video, setVideo] = useState({ open: false, url: null, loading: false })
  const [report, setReport] = useState(null)
  const [reportError, setReportError] = useState('')
  const { user } = useAuth()
  const biz = useBusiness()
  const rosterCandidate = biz?.candidateById?.(id) || null
  const role = biz?.roleById?.(roleId) || null
  const c = report?.candidate ? {
    ...rosterCandidate, ...report.candidate,
    verifiedScore: report.assessment?.score,
    assessed: report.assessment?.recordedAt,
    hasVideo: true,
  } : rosterCandidate
  const shortlisted = biz?.isShortlisted?.(id) || false

  useEffect(() => {
    let live = true
    if (!user || !id) return undefined
    ;(async () => {
      try {
        const token = await user.getIdToken()
        const next = await getCandidateReport({ token, cookId: id, roleId })
        if (live) { setReport(next); setReportError('') }
      } catch {
        if (live) setReportError('The evidence report could not be loaded.')
      }
    })()
    return () => { live = false }
  }, [user, id, roleId])

  async function playVideo() {
    setVideo({ open: true, url: null, loading: true })
    try {
      const token = await user?.getIdToken?.()
      const url = await reportPlayback({ token, cookId: id, roleId,
        attemptId: report?.assessment?.attemptId, request: getCandidateVideo })
      setVideo({ open: true, url, loading: false })
    } catch { setVideo({ open: true, url: null, loading: false }) }
  }

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
      <button onClick={() => navigate(-1)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
        <ArrowLeft size={14} color="#70706b" strokeWidth={1.5} />
        <span style={{ fontSize: 10, letterSpacing: 2.3, color: '#70706b', fontWeight: 500, textTransform: 'uppercase' }}>Back to applicants</span>
      </button>
    </div>
  )
  if (!c) return <BusinessShell header={header}><EmployerApplicationReview cookId={id} roleId={roleId}/><p style={{ textAlign: 'center', color: '#74756f', padding: '60px 20px' }}>{biz?.loading ? 'Loading…' : 'No assessment report is available yet.'}</p></BusinessShell>

  const estimated = report?.assessment?.deviceEstimates?.overall
  const s = estimated ?? c.verifiedScore
  const claims = report?.assessment?.deviceEstimates ? [] : reconcileClaims(c)
  const m = report?.match || null
  const creds = credentialDetails(c.resumePoints || [])
  // Certifications get the dedicated accreditation section below; everything else shows as grouped chips.
  const grouped = {}
  for (const pid of c.resumePoints || []) {
    const n = nodeById(pid)
    if (n && n.category !== 'certification' && n.category !== 'alcohol_cert') (grouped[n.category] = grouped[n.category] || []).push(pid)
  }

  return (
    <BusinessShell header={header}>
      <motion.div initial="hidden" animate="show" variants={staggerContainer(0.08)}
        style={{ display: 'flex', gap: 28, alignItems: 'flex-start', flexWrap: 'wrap', padding: '26px 28px 40px' }}>

      {/* trust summary — intentionally remains in document flow so it never covers evidence while scrolling. */}
      <motion.div variants={fadeUp} style={{ flex: '1 1 280px', maxWidth: '100%' }}>
        <div className="cc-business-card" style={{ background: '#FEFDFB', border: '1px solid #E3E0D9', padding: '26px 22px', textAlign: 'center' }}>
          <div aria-hidden="true" style={{ width: 118, height: 118, flexShrink: 0, margin: '0 auto 16px', borderRadius: 2, background: c.photo ? `#EDE7DF url(${c.photo}) center/cover` : '#EDE7DF', border: '1px solid #E0DDD3', display: 'grid', placeItems: 'center', fontFamily: SERIF, fontSize: 44, color: '#8e8272' }}>{!c.photo && (c.name || '?').trim().charAt(0).toUpperCase()}</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <h1 style={{ fontFamily: SERIF, fontSize: 30, fontWeight: 500, color: '#1a1a1a', margin: 0 }}>{c.name}</h1>
            {report?.assessment?.status === 'verified' && <ShieldCheck size={16} color={GREEN} strokeWidth={2} aria-label="Verified assessment" />}
          </div>
          <p style={{ fontSize: 10, letterSpacing: 1.2, color: GREEN, textTransform: 'uppercase', margin: '5px 0 18px', fontWeight: 700 }}>Shared knife assessment</p>

          <div style={{ display: 'inline-flex', alignItems: 'baseline', gap: 4, padding: '8px 0' }}>
            <motion.span initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              style={{ fontFamily: SERIF, fontSize: 44, fontWeight: 400, color: '#1a1a1a', lineHeight: 1 }}>{s == null ? '—' : s}</motion.span>
            <span style={{ fontSize: 10, color: '#70706b', letterSpacing: .6, textTransform: 'uppercase' }}>{s == null ? 'Measurement unavailable' : `/ 100 ${estimated != null ? 'browser estimate' : 'verified result'}`}</span>
          </div>

          <p style={{ fontSize: 13, color: '#777', margin: '18px 0 0' }}>{(c.cuisines || []).join(' · ')}</p>
          <p style={{ fontSize: 13, color: '#74756f', margin: '4px 0 20px' }}>{[c.city, c.years != null ? `${c.years} yrs experience` : null].filter(Boolean).join(' · ')}</p>

          <motion.button {...buttonPress} onClick={() => biz?.toggleShortlist?.(id)} style={{ width: '100%', padding: 13, border: shortlisted ? `1px solid ${GREEN}` : 'none',
            background: shortlisted ? '#FEFDFB' : GREEN, color: shortlisted ? GREEN : '#fff', fontSize: 14, fontWeight: 500, letterSpacing: 0.2, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <motion.span key={shortlisted ? 'on' : 'off'} initial={{ scale: 0.6 }} animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 400, damping: 15 }} style={{ display: 'inline-flex' }}>
              <Star size={16} strokeWidth={2} fill={shortlisted ? GREEN : 'none'} />
            </motion.span>{shortlisted ? 'Shortlisted' : 'Add to shortlist'}
          </motion.button>
        </div>
      </motion.div>

      {/* résumé / skill breakdown content */}
      <div style={{ flex: '3 1 460px', minWidth: 0 }}>
      <EmployerApplicationReview cookId={id} roleId={roleId}/>
      {reportError && <div className="cc-business-notice" style={{ border: '1px solid #C4561F', background: '#FBF1EC', padding: '10px 12px', marginBottom: 14, fontSize: 13 }}>{reportError}</div>}
      {report?.assessment?.limitations && (
        <motion.div className="cc-business-notice" variants={fadeUp} style={{ border: `1px solid ${report.assessment.limitations.employmentValidated ? GREEN : GOLD}`, background: report.assessment.limitations.employmentValidated ? '#E8F1EC' : '#FBF7EC', padding: '12px 14px', marginBottom: 18 }}>
          <p style={{ fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', color: '#777', margin: '0 0 5px' }}>Use of this result</p>
          <p style={{ fontSize: 13, color: '#333', lineHeight: 1.55, margin: 0 }}>{report.assessment.limitations.message}</p>
        </motion.div>
      )}
      {report?.assessment?.outcome && <motion.div className="cc-business-notice" variants={fadeUp} style={{ border: '1px solid #cfc4b5', background: '#fffaf2', padding: '14px 16px', marginBottom: 18 }}>
        <p style={{ ...overline, color: GREEN }}>Knife skill outcome</p>
        <div style={{ fontFamily: SERIF, fontSize: 24, color: '#2b2925', textTransform: 'capitalize' }}>{report.assessment.outcome.outcome.replaceAll('_', ' ')}</div>
        <p style={{ fontSize: 13, color: '#5f574e', lineHeight: 1.55, margin: '6px 0 10px' }}>{report.assessment.outcome.explanation}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{Object.entries(report.assessment.outcome.profile?.criteria || {}).map(([key, value]) => <span key={key} style={{ border: '1px solid #ddd4c7', background: '#fff', padding: '4px 8px', fontSize: 10, color: '#746b61' }}>{key.replaceAll(/([A-Z])/g, ' $1')}: {String(value)}</span>)}</div>
        <p style={{ fontSize: 11, color: '#8a7f73', margin: '10px 0 0' }}>Next step: {report.assessment.outcome.workflowGate?.status?.replaceAll('_', ' ')}.</p>
      </motion.div>}
      {/* skill assessment video */}
      {c.hasVideo && (
        <motion.div variants={fadeUp} style={{ padding: '0 0 0' }}>
          <p style={overline}>Skill assessment video</p>
          {!video.open ? (
            <button onClick={playVideo} style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', border: 'none', cursor: 'pointer', padding: 0,
              background: `linear-gradient(rgba(0,0,0,0.3), rgba(0,0,0,0.45)), #000 url(${c.photo}) center/cover` }}>
              <span style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <PlayCircle size={50} color="#fff" strokeWidth={1.25} />
                <span style={{ color: '#fff', fontSize: 12, letterSpacing: 0.5 }}>Watch {c.name.split(' ')[0]}’s shared assessment</span>
              </span>
            </button>
          ) : video.url ? (
            <CandidateVideoPlayer key={video.url} url={video.url} cookId={id} roleId={roleId} attemptId={report?.assessment?.attemptId} onRetry={playVideo} />
          ) : (
            <div style={{ border: '1px solid #e5e5e5', padding: '14px 16px', fontSize: 13, color: '#777', lineHeight: 1.5 }}>
              {video.loading ? 'Loading…' : 'The recording could not be loaded. Close and reopen the report to retry.'}
            </div>
          )}
          <p style={{ fontSize: 11, color: '#74756f', margin: '6px 0 0' }}>The submitted clip from this candidate’s assessment — held under the same retention as biometric data.</p>
        </motion.div>
      )}

      {/* about / description */}
      {c.bio && (
        <motion.div variants={fadeUp} style={{ padding: '18px 0 0' }}>
          <p style={overline}>About</p>
          <p style={{ fontSize: 14, color: '#444', lineHeight: 1.6, margin: 0 }}>{c.bio}</p>
        </motion.div>
      )}

      {/* match vs this role */}
      {m && (
        <motion.div variants={fadeUp} style={{ padding: '18px 0 4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
            <p style={{ ...overline, margin: 0 }}>Match · {role.title}</p>
            <span style={{ fontSize: 13, fontWeight: 600, color: m.band === 'Gated' ? TERRA : m.total >= 0.6 ? GREEN : GOLD }}>{m.band === 'Gated' ? 'Not eligible' : m.band}</span>
          </div>
          {!m.gates.passed && (
            <div style={{ display: 'flex', gap: 8, border: `1px solid ${TERRA}`, background: '#FBF1EC', padding: '10px 12px', marginBottom: 10 }}>
              <CircleAlert size={15} color={TERRA} strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 13, color: '#1a1a1a' }}>Does not meet: {m.gates.failures.join(', ')}</span>
            </div>
          )}
          {m.requirements.map(r => (
            <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', fontSize: 13 }}>
              <span style={{ width: 16, height: 16, flexShrink: 0, border: `1px solid ${r.status === 'met' ? GREEN : '#ccc'}`, background: r.status === 'met' ? GREEN : '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                {r.status === 'met' && <Check size={11} color="#fff" strokeWidth={3} />}
              </span>
              <span style={{ color: r.status === 'met' ? '#1a1a1a' : '#999', flex: 1 }}>{labelOf(r.id)}{r.kind === 'preferred' ? ' (nice-to-have)' : ''}</span>
              {r.source && <span style={{ fontSize: 11, color: '#74756f' }}>{r.source}</span>}
            </div>
          ))}
        </motion.div>
      )}

      {/* claim vs camera truth */}
      {claims.length > 0 && (
        <motion.div variants={fadeUp} style={{ padding: '14px 0 0' }}>
          <div style={{ display: 'flex', gap: 8, border: `1px solid ${claims[0].status === 'contradicted' ? TERRA : claims[0].status === 'verified' ? GREEN : GOLD}`,
            background: claims[0].status === 'contradicted' ? '#FBF1EC' : claims[0].status === 'verified' ? '#E8F1EC' : '#FBF7EC', padding: '10px 12px' }}>
            {claims[0].status === 'verified' ? <ShieldCheck size={15} color={GREEN} strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }} /> : <CircleAlert size={15} color={claims[0].status === 'contradicted' ? TERRA : GOLD} strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }} />}
            <span style={{ fontSize: 13, color: '#1a1a1a' }}>Résumé claims a skill — {claims[0].status === 'verified' ? 'confirmed by' : claims[0].status === 'partial' ? 'partly backed by' : 'NOT supported by'} the {claims[0].detail}.</span>
          </div>
        </motion.div>
      )}

      {/* résumé — the de-identified extraction of the candidate's attached résumé. We surface job-related
          facts only (skills, experience, service specialties, safety knowledge), NEVER the raw document
          with name/school/address/employment dates — those are the protected-attribute proxies the fair
          screen is built to keep out of the hiring view (RANKING_FAIRNESS.md). */}
      <motion.div variants={fadeUp} style={{ padding: '20px 0 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 4px' }}>
          <FileText size={14} color="#999" strokeWidth={1.5} />
          <p style={{ ...overline, margin: 0 }}>Résumé</p>
        </div>
        <p style={{ fontSize: 12, color: '#74756f', margin: '0 0 14px', lineHeight: 1.6 }}>
          {c.years != null ? `${c.years} yrs experience · ` : ''}extracted from {c.name.split(' ')[0]}’s attached résumé, de-identified to job-related facts.
        </p>
        <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show">
          {CAT_ORDER.filter(cat => grouped[cat]?.length).map(cat => (
            <div key={cat} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, letterSpacing: 1.5, color: '#74756f', textTransform: 'uppercase', marginBottom: 6 }}>{CAT_LABEL[cat] || cat}</div>
              <motion.div variants={staggerContainer(0.03)} style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {grouped[cat].map(pid => (
                  <motion.span key={pid} variants={scaleIn}
                    style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '5px 10px', fontSize: 12, color: '#1a1a1a' }}>{labelOf(pid)}</motion.span>
                ))}
              </motion.div>
            </div>
          ))}
        </motion.div>
      </motion.div>

      {/* certifications — scored by the issuer's accrediting body, not by brand */}
      {creds.length > 0 && (
        <motion.div variants={fadeUp} style={{ padding: '20px 0 0' }}>
          <p style={overline}>Certifications &amp; accreditation</p>
          {creds.map(cr => (
            <div key={cr.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderBottom: '1px solid #f0f0f0' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: '#1a1a1a', fontWeight: 500 }}>{cr.label}</div>
                <div style={{ fontSize: 11, color: '#74756f', marginTop: 1 }}>{cr.standard} · {cr.accreditor}</div>
              </div>
              <span style={{ fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', padding: '3px 8px', whiteSpace: 'nowrap',
                border: `1px solid ${cr.trust >= 0.95 ? GREEN : cr.trust >= 0.75 ? '#1a1a1a' : '#ccc'}`,
                color: cr.trust >= 0.95 ? GREEN : cr.trust >= 0.75 ? '#1a1a1a' : '#999' }}>{cr.tier}</span>
              <span style={{ fontSize: 11, color: cr.status === 'verified' ? GREEN : '#bbb', whiteSpace: 'nowrap' }}>
                {cr.status === 'verified' ? 'Verified' : cr.status === 'pending' ? 'Pending' : 'Claimed'}
              </span>
            </div>
          ))}
          <p style={{ fontSize: 11, color: '#74756f', margin: '8px 0 0', lineHeight: 1.6 }}>
            Ranked by the issuer’s accrediting body (ANAB/CFP, ASTM, DOL, CHEA) — never by brand; same-standard exams score equally. A claimed credential is capped until verified.
          </p>
        </motion.div>
      )}

      {/* verified skill breakdown (camera detail) */}
      <motion.div variants={fadeUp} style={{ padding: '20px 0 8px' }}>
        <p style={overline}>Assessment evidence</p>
        {report?.assessment ? <>
          {(report.assessment.deviceEstimates ? [
            ['Rhythm (browser estimate)', report.assessment.deviceEstimates.rhythm ?? 'Unavailable'],
            ['Consistency (browser estimate)', report.assessment.deviceEstimates.consistency ?? 'Unavailable'],
            ['Form (browser estimate)', report.assessment.deviceEstimates.form ?? 'Unavailable'],
            ['Detected strokes', report.assessment.deviceEstimates.strokes ?? 'Unavailable'],
            ['Cadence (strokes / second)', report.assessment.deviceEstimates.cadence ?? 'Unavailable'],
            ['Assessment source', 'Live assessment — not independently verified'],
          ] : [
            ['Detected technique', report.assessment.measurements?.detectedTechnique || 'Not confidently detected'],
            ['Requested technique matched', report.assessment.measurements?.requestedTechniqueMatched == null ? 'Unavailable' : report.assessment.measurements.requestedTechniqueMatched ? 'Yes' : 'No'],
            ['Finished product gradeable', report.assessment.measurements?.productGradeable ? 'Yes' : 'No'],
            ['Product-quality score', report.assessment.measurements?.productScore ?? 'Unavailable'],
          ]).map(([label, value]) => <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '8px 0', borderBottom: '1px solid #eee', fontSize: 13 }}>
            <span style={{ color: '#777' }}>{label}</span><span style={{ color: '#1a1a1a', textAlign: 'right' }}>{value}</span>
          </div>)}
          <div style={{ marginTop: 12, padding: '10px 12px', background: '#F6F3ED', fontSize: 12, lineHeight: 1.55, color: '#555' }}>
            <b>How the number is produced:</b> {report.assessment.calculation?.scoreSource}. {report.assessment.calculation?.comparison}
            {report.assessment.calculation?.resultReason ? ` Result note: ${report.assessment.calculation.resultReason}` : ''}
          </div>
          <p style={{ fontSize: 11, color: '#74756f', lineHeight: 1.6, margin: '8px 0 0' }}>
            Profile {report.assessment.profileId || 'unavailable'} · recording version pinned: {report.assessment.provenance?.recordingGenerationPinned ? 'yes' : 'no'} · client-computed score used for hiring: no.
          </p>
        </> : <p style={{ fontSize: 14, color: '#777', lineHeight: 1.6 }}>Loading the measured evidence and its calculation…</p>}
        <p style={{ fontSize: 11, color: '#74756f', lineHeight: 1.6, margin: '6px 0 0' }}>
          Recorded assessment{c.assessed ? ` (${c.assessed})` : ''}. A point-in-time work-sample, not an endorsement or guarantee of employment. <span style={{ color: GREEN, cursor: 'pointer' }} onClick={() => navigate('/business/audit')}>How evidence is measured</span>.
        </p>
        {report?.attemptHistory?.length > 0 && <div style={{ marginTop: 16 }}>
          <p style={overline}>Shared attempt history</p>
          {report.attemptHistory.map((attempt, index) => <div key={attempt.attemptId} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #eee', fontSize: 12 }}>
            <span>Attempt {report.attemptHistory.length - index} · {attempt.recordedAt ? new Date(attempt.recordedAt).toLocaleDateString() : 'date unavailable'}</span>
            <span>{attempt.score == null ? attempt.status : `${attempt.score}/100`}</span>
          </div>)}
        </div>}
      </motion.div>
      </div>
      </motion.div>
    </BusinessShell>
  )
}
