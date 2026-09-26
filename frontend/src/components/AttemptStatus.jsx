import { motion } from 'framer-motion'
import { Play, ExternalLink } from 'lucide-react'
import { buttonPress } from '../styles/motion'
const SERIF = 'var(--cc-display)'
const GREEN = '#1F6F5C', GOLD = '#8B721A', INK = '#1a1a1a'
const overline = { fontSize: 10, letterSpacing: 2.4, textTransform: 'uppercase', color: '#70706b', margin: '0 0 7px' }

export default function AttemptStatus({ application, onStart, starting }) {
  const evidence = application.bestAssessment || application.latestAssessment
  const withdrawn = application.status === 'withdrawn'
  const closed = application.role?.status && application.role.status !== 'open'
  const ready = application.status === 'ready'
  const processing = application.status === 'assessment_processing'
  return <section style={{ border: '1px solid #dedbd4', background: '#fff', padding: 18 }}>
    <p style={overline}>Knife skill assessment</p>
    <h2 style={{ fontFamily: SERIF, fontWeight: 400, fontSize: 23, margin: '0 0 8px' }}>
      {withdrawn ? 'Application withdrawn' : ready ? 'Assessment received' : processing ? 'Video analysis in progress' : 'Show your knife work'}
    </h2>
    <p style={{ color: '#666', fontSize: 13, lineHeight: 1.55, margin: '0 0 14px' }}>
      {withdrawn ? 'Future employer access to your recording has been revoked.' : ready ? 'Your employer can now review your submitted recording and measurements. No further action is required; another attempt is optional.' : processing ? 'Your submission is being processed. You do not need to submit it again.' : 'Record your knife work, review it, then submit it to the employer. Your completed attempt history stays visible.'}
    </p>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
      {Array.from({ length: application.attemptLimit }, (_, index) => {
        const attempt = application.attempts?.find(item => item.slot === index + 1)
        return <span key={index} style={{ border: '1px solid #e7e4dd', padding: '6px 9px', fontSize: 11, color: attempt ? INK : '#aaa' }}>
          Try {index + 1} · {attempt?.status || 'available'}
        </span>
      })}
    </div>
    {evidence && <div style={{ background: '#F1F6F3', borderLeft: `3px solid ${GREEN}`, padding: '11px 12px', marginBottom: 14 }}>
      <strong style={{ fontFamily: SERIF, fontSize: 22 }}>{evidence.score ?? 'Review required'}</strong>
      <span style={{ fontSize: 11, color: '#777' }}>{evidence.score != null ? ' / 100 recorded result' : ''}</span>
      <p style={{ margin: '5px 0 0', color: '#555', fontSize: 12, lineHeight: 1.5 }}>{evidence.calculation?.resultReason || 'The evidence report is available to you and the employer.'}</p>
    </div>}
    {evidence?.deviceEstimates && <dl style={{ display: 'flex', flexWrap: 'wrap', gap: 22, margin: '16px 0', fontSize: 13 }}>
      {['rhythm', 'consistency', 'form'].map(axis => <div key={axis}><dt style={{ textTransform: 'capitalize' }}>{axis} · browser estimate</dt><dd style={{ marginTop: 5 }}>{evidence.deviceEstimates[axis] ?? 'Unavailable'}</dd></div>)}
    </dl>}
    {application.attemptsRemaining > 0 && !processing && !withdrawn && !closed && <motion.button {...buttonPress} type="button" onClick={onStart} disabled={starting} style={{ width: '100%', border: 0, background: INK, color: '#fff', padding: 14, cursor: starting ? 'default' : 'pointer', opacity: starting ? 0.55 : 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8 }}>
      <Play size={15} /> {starting ? 'Opening…' : application.attemptsCompleted ? 'Use another attempt' : 'Start assessment'}
    </motion.button>}
    {closed && !withdrawn && <p style={{ fontSize: 13, color: '#777' }}>This role is closed. New attempts are unavailable.</p>}
    {processing && <p style={{ margin: 0, fontSize: 13, color: GOLD }}>You can return here later. Your result will appear when the video analysis is complete.</p>}
    {!application.attemptsRemaining && !ready && !processing && !withdrawn && <p style={{ margin: 0, fontSize: 13, color: '#777' }}>All available attempts have been used. The employer sees the attempt history and any gradeable result.</p>}
    {ready && application.returnUrl && <a href={application.returnUrl} style={{ display: 'inline-flex', gap: 7, alignItems: 'center', marginTop: 12, background: GREEN, color: '#fff', textDecoration: 'none', padding: '11px 15px', fontSize: 13 }}>Return to application <ExternalLink size={14} /></a>}
  </section>
}

