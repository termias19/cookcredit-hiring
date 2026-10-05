/** Public explanation of the recorded work-sample and its current limitations. */
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import Shell from '../components/Shell'
import { fadeIn, staggerContainer } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = 'var(--cc-forest)'

function Row({ k, v }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '7px 0', borderBottom: '1px solid #f0ece3' }}>
      <span style={{ color: '#777' }}>{k}</span><span style={{ color: 'var(--cc-ink)' }}>{v}</span>
    </div>
  )
}

export default function BusinessAuditScreen() {
  const navigate = useNavigate()
  const header = (
    <div style={{ background: 'var(--cc-surface)', borderBottom: '1px solid #eee', padding: '14px 20px' }}>
      <button onClick={() => navigate(-1)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
        <ArrowLeft size={14} color="#999" strokeWidth={1.5} />
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>Back</span>
      </button>
      <h1 style={{ fontFamily: SERIF, fontSize: 26, fontWeight: 400, color: 'var(--cc-ink)', margin: 0 }}>How assessment evidence works</h1>
    </div>
  )

  return (
    <Shell header={header} showNav={false}>
      <motion.div variants={staggerContainer(0.1)} initial="hidden" animate="show" style={{ padding: '18px 20px 32px', fontSize: 14, color: '#444', lineHeight: 1.6 }}>
        <motion.div variants={fadeIn} style={{ display: 'flex', gap: 10, border: `1px solid ${GREEN}`, background: '#E8F1EC', padding: '12px 14px', marginBottom: 16 }}>
          <ShieldCheck size={18} color={GREEN} strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }} />
          <p style={{ margin: 0, fontSize: 13, color: 'var(--cc-ink)' }}>CookCredit does not automatically rank, accept, or reject hiring applicants. Applications remain in submission order. A person reviews the recorded work-sample and the rest of the application.</p>
        </motion.div>

        <motion.div variants={fadeIn}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '0 0 8px' }}>What the report contains</p>
          <p>The published assessment estimates rhythm (timing steadiness), consistency (stroke-depth steadiness) and form (vertical motion) in the browser. Available axes use weights of 45%, 30% and 25%. The report labels these as provisional and includes the submitted recording. Matching server video verification is pending. A zero in the saved version may also mean missing signal; it cannot be treated as an automatic failure.</p>
          <div style={{ border: '1px solid var(--cc-border)', padding: '10px 14px' }}>
            <Row k="Recording source" v="Pinned storage generation" />
            <Row k="Browser score" v="Provisional; human review required" />
            <Row k="Attempts" v="Shared according to applicant consent" />
            <Row k="Hiring decision" v="Human reviewer" />
          </div>
        </motion.div>

        <motion.div variants={fadeIn}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '20px 0 8px' }}>Current limitation</p>
          <div style={{ border: '1px solid var(--cc-border)', padding: '10px 14px' }}>
            <Row k="Employment validation" v="Pending" />
            <Row k="Independent adverse-impact audit" v="Pending" />
            <Row k="Automatic screening" v="Disabled" />
          </div>
          <p style={{ fontSize: 12, color: '#777', marginTop: 8 }}>The assessment has not yet been independently validated for automatic employment screening. Employers should review the recording, the measurement limits, and other job evidence. They should not reject a person from this score alone.</p>
        </motion.div>

        <motion.div variants={fadeIn}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: '20px 0 8px' }}>Your rights</p>
          <p>You may withdraw an application to stop new employer playback links. You may also request a human review or a non-camera alternative by contacting <span style={{ color: GREEN }}>connectwithus@cookcredit.com</span>.</p>
          <p style={{ fontSize: 11, color: '#74756f', marginTop: 16 }}>This page describes the product’s current behavior and known validation gap. It is not a substitute for an employer’s legal or accessibility review.</p>
        </motion.div>
      </motion.div>
    </Shell>
  )
}
