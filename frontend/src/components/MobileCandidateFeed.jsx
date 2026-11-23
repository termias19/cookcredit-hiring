import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Star, Info, X, Search, Hand, SlidersHorizontal } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useBusiness } from '../context/BusinessContext'
import { getCandidateReport, getCandidateVideo } from '../utils/Api'
import { reportPlayback, recordingLabel, playbackFailure } from '../utils/reportPlayback'
import CandidateVideoPlayer from './CandidateVideoPlayer'
import './MobileCandidateFeed.css'
import HiringBottomNav from './HiringBottomNav'
import EmployerApplicationReview from './EmployerApplicationReview'
import { PREVIEW } from '../config'
import PlaybackViewControl from './PlaybackViewControl'
import usePlaybackView from '../hooks/usePlaybackView'

function CandidateReel({ candidate }) {
  const root = useRef(null), sheet = useRef(null)
  const [landmarks, setLandmarks] = usePlaybackView()
  const { user } = useAuth(), biz = useBusiness(), navigate = useNavigate()
  const [visible, setVisible] = useState(false), [report, setReport] = useState(null)
  const [url, setUrl] = useState(null), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const [terminal, setTerminal] = useState(false)
  const [saving, setSaving] = useState(false), [starError, setStarError] = useState('')
  const [details, setDetails] = useState(false)
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      const next = entry.isIntersecting && entry.intersectionRatio >= 0.6
      setVisible(next)
      if (!next) setUrl(null) // Returning must obtain a fresh, consent-checked URL.
    }, { threshold: 0.6 })
    observer.observe(root.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let live = true
    if (!visible || !user) return undefined
    const controller = new AbortController()
    ;(async () => {
      try {
        const token = await user.getIdToken()
        if (!live) return
        const next = await getCandidateReport({ token, cookId: candidate.id, signal: controller.signal })
        if (!live) return
        if (live) setReport(next)
        if (['expired','unavailable'].includes(next.assessment?.recording?.state)) {
          if (live) { setUrl(null); setTerminal(true); setError(`${recordingLabel(next.assessment.recording)}. The application and assessment history remain available.`) }
          return
        }
        const signed = await reportPlayback({ token, cookId: candidate.id, attemptId: next.assessment?.attemptId, request: getCandidateVideo, signal: controller.signal })
        if (live) { setReport(next); setUrl(signed); setTerminal(false); setError(signed ? '' : 'No playable recording is available for this attempt.') }
      } catch (error) { if (live) { const failure = playbackFailure(error); setUrl(null); setTerminal(failure.terminal); setError(failure.message) } }
    })()
    return () => { live = false; controller.abort() }
  }, [visible, user, candidate.id, retry])
  useEffect(() => {
    if (details) sheet.current?.showModal()
    else sheet.current?.close()
  }, [details])
  async function star() {
    if (saving) return
    setSaving(true); setStarError('')
    try { if (await biz.toggleShortlist(candidate.id) === false) setStarError('Shortlist was not saved. Please retry.') }
    catch { setStarError('Shortlist was not saved. Please retry.') }
    finally { setSaving(false) }
  }
  const measurements = report?.assessment?.deviceEstimates
  const starred = biz.isShortlisted(candidate.id)
  return <article className="cc-candidate-reel" ref={root} aria-label={`${candidate.name || 'Candidate'} assessment`}>
    {url && visible ? <CandidateVideoPlayer key={`${candidate.id}:${url}`} url={url} cookId={candidate.id} attemptId={report?.assessment?.attemptId} reel active={!details}
      onRetry={() => setRetry(x => x + 1)} /> : <div className="cc-reel-loading" role="status">
      <p>{error || 'Loading shared recording…'}</p>{error && !terminal && <button onClick={() => setRetry(x => x + 1)}>Retry</button>}
    </div>}
    <div className="cc-reel-caption">
      <h2>{candidate.name || 'Candidate'}</h2><p>{report?.role?.title || 'Shared with your company'}{candidate.city ? ` · ${candidate.city}` : ''}</p>
      {landmarks && measurements && <dl>{['rhythm', 'consistency', 'form'].map(key => <div key={key}><dt>{key}</dt><dd>{measurements[key] ?? '—'}</dd></div>)}</dl>}
      {landmarks && <small>Saved measurements · human review</small>}
      {starError && <p role="alert">{starError}</p>}
    </div>
    <div className="cc-reel-actions" aria-label="Candidate actions">
      <button onClick={star} disabled={saving} aria-pressed={starred} aria-label={starred ? 'Remove from shortlist' : 'Add to shortlist'}><Star fill={starred ? 'currentColor' : 'none'} /><span>Save</span></button>
      <button onClick={() => setDetails(true)} aria-label="Open candidate details"><Info /><span>Details</span></button>
      <button onClick={() => setLandmarks(!landmarks)} aria-pressed={landmarks} aria-label={landmarks ? 'Hide landmarks' : 'Show landmarks'}><Hand /><span>Landmarks</span></button>
    </div>
    <dialog ref={sheet} className="cc-candidate-sheet" aria-labelledby={`candidate-title-${candidate.id}`} onClose={() => setDetails(false)} onCancel={() => setDetails(false)}>
      <header><h2 id={`candidate-title-${candidate.id}`}>{candidate.name || 'Candidate'}</h2><button onClick={() => setDetails(false)} aria-label="Close candidate details"><X /></button></header>
      <p>{report?.candidate?.bio || 'Review the recording alongside the candidate’s experience and references.'}</p>
      {measurements && <dl>{[['Rhythm',measurements.rhythm],['Consistency',measurements.consistency],['Form',measurements.form],['Detected strokes',measurements.strokes],['Pace (strokes/s)',measurements.cadence]].map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{value ?? 'Unavailable'}</dd></div>)}</dl>}
      {details && <EmployerApplicationReview cookId={candidate.id} roleId={report?.role?.id}/>}
      <p>These measurements are not independently verified. Shortlisting is your decision.</p>
      <p>{report?.attemptHistory?.length || 0} shared assessment attempt(s)</p>
      <button className="cc-sheet-review" onClick={() => navigate(`/business/candidate/${encodeURIComponent(candidate.id)}`)}>Open full evidence report</button>
    </dialog>
  </article>
}

export default function MobileCandidateFeed({ candidates, query, onQueryChange, embedded = false }) {
  const [filtersOpen, setFiltersOpen] = useState(false)
  return <section style={embedded ? { height: '80svh', minHeight: 440 } : undefined} className="cc-mobile-candidates" aria-label="Candidate recordings">
    <header className="cc-feed-header"><a href="https://cookcredit.com/" className="cc-feed-brand">CookCredit</a><button type="button" aria-label="Candidate filters" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(value => !value)}><SlidersHorizontal size={21}/></button></header>
    {filtersOpen && <div className="cc-feed-filters"><label><Search size={18}/><input type="search" aria-label="Search candidates" placeholder="Name, skill or city" value={query} onChange={e => onQueryChange(e.target.value)} /></label><p>Recording view · does not filter out applicants</p><PlaybackViewControl /></div>}
    <p className="cc-feed-order">{PREVIEW ? 'Sample applicants · swipe to review' : 'Application order · swipe to review'}</p>
    <div className="cc-reel-list">{candidates.map(c => <CandidateReel key={c.id} candidate={c}/>)}{!candidates.length && <p className="cc-feed-empty">No candidates match your search.</p>}</div>
    {!embedded && <HiringBottomNav />}
  </section>
}
