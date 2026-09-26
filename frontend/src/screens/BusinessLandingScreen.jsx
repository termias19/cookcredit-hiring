/**
 * Public entry to the hiring workspace. Product and assessment links point to
 * the published CookCredit sites, independently of this workspace's environment.
 */
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ScanLine, BarChart3, UserCheck, ArrowRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { isBusinessProfile } from '../utils/homeFor'
import { COOKCREDIT_ASSESSMENT_URL } from '../config'
import CookCreditBrand from '../components/CookCreditBrand'
import { fadeUp, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "var(--cc-display)"
const overline = { fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase', margin: 0 }

function Step({ n, icon, title, body }) {
  return (
    <motion.div variants={fadeUp} style={{ flex: '1 1 200px', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <span style={{ fontFamily: SERIF, fontSize: 13, color: '#74756f', letterSpacing: 2 }}>{n}</span>
        <span style={{ width: 44, height: 44, border: '1px solid #e5e5e5', background: '#fff',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          {icon}
        </span>
      </div>
      <h3 style={{ fontFamily: SERIF, fontSize: 21, fontWeight: 500, color: '#1a1a1a', margin: '0 0 6px' }}>{title}</h3>
      <p style={{ fontSize: 14, color: '#777', lineHeight: 1.6, margin: 0 }}>{body}</p>
    </motion.div>
  )
}

export default function BusinessLandingScreen() {
  const navigate = useNavigate()
  const { user, profile } = useAuth()
  // Route the marketing CTAs through the REAL funnel instead of deep-linking gated workspace URLs
  // (which a production build bounces to /login or /business/onboarding): logged-out → sign in;
  // logged-in non-business → activate a workspace; already-business → the requested page.
  const goWorkspace = dest => navigate(!user ? '/signup' : isBusinessProfile(profile) ? dest : '/business/onboarding', { state: { from: dest } })
  const primary = {
    display: 'inline-flex', alignItems: 'center', gap: 8, padding: '14px 28px', border: 'none',
    background: '#1F6F5C', color: '#fff', fontSize: 14, fontWeight: 500, letterSpacing: 0.5, cursor: 'pointer',
  }
  return (
    <div className="cc-hiring-page" style={{ minHeight: '100svh', background: '#FEFDFB', color: '#1a1a1a' }}>
      {/* top bar */}
      <div style={{ maxWidth: 960, margin: '0 auto', padding: '18px 24px', borderBottom: '1px solid #eee',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <CookCreditBrand />
        <motion.button whileTap={tapScale} onClick={() => navigate(user ? '/profile' : '/login', { state: { from: '/business/roles' } })} style={{
          background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#1a1a1a',
          borderBottom: '2px solid #1a1a1a', paddingBottom: 3,
        }}>{user ? 'My account' : 'Sign in'}</motion.button>
      </div>

      {/* hero */}
      <motion.section initial="hidden" animate="show" variants={fadeUp} className="cc-hiring-hero">
        <div>
        <p style={overline}>CookCredit · Knife skill assessment</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(34px, 7vw, 52px)', fontWeight: 400, color: '#1a1a1a',
          lineHeight: 1.1, margin: '18px 0 18px' }}>
          See their knife skills before the first shift.
        </h1>
        <p style={{ fontSize: 16, color: '#777', lineHeight: 1.7, maxWidth: 520, margin: '0 auto' }}>
          Add CookCredit to your hiring process. Applicants record their knife work; your team reviews the video, measurements, and attempt history in one place.
        </p>
        <div style={{ marginTop: 30 }}>
          <motion.button {...buttonPress} onClick={() => goWorkspace('/business/roles')} style={primary}>
            {user ? 'Open your workspace' : 'Start hiring'} <ArrowRight size={16} strokeWidth={1.5} />
          </motion.button>
        </div>
        <nav aria-label="Explore CookCredit" style={{ marginTop: 20, display: 'flex', gap: '12px 24px', flexWrap: 'wrap' }}>
          <a href={COOKCREDIT_ASSESSMENT_URL} target="_blank" rel="noopener noreferrer" aria-label="Try the live assessment (opens in a new tab)" style={{
            fontSize: 13, color: '#1F6F5C', textUnderlineOffset: 5,
          }}>Try the live assessment</a>
          <button onClick={() => goWorkspace('/business/integrations')} style={{ padding: 0, border: 0, background: 'none', font: 'inherit', fontSize: 13, color: '#1F6F5C', textDecoration: 'underline', textUnderlineOffset: 5, cursor: 'pointer' }}>Connect your hiring system</button>
        </nav>
        <p style={{ fontSize: 12, color: '#777', lineHeight: 1.6, marginTop: 14 }}>
          Trying the assessment here does not submit a job application.
        </p>
        </div>
        <aside className="cc-report-preview" aria-label="Example assessment report">
          <div className="cc-report-preview-heading"><span style={overline}>THE EVIDENCE, AT A GLANCE</span><span className="cc-example-label">Example</span></div>
          <div className="cc-recording-preview" aria-label="Illustration of a knife work recording">
            <ScanLine size={48} strokeWidth={1} /><span>A work sample you can watch.</span>
            <span style={{ fontSize: 11, color: '#d1d9d0' }}>Knife work · submitted by your applicant</span>
          </div>
          <h2 style={{ fontFamily: SERIF, fontWeight: 400, fontSize: 28, margin: '22px 0 12px' }}>More than a résumé.</h2>
          {[['Rhythm', 'Timing between strokes'], ['Consistency', 'Steadiness of stroke depth'], ['Form', 'Direction of the movement']].map(([label, description]) => <div className="cc-preview-measure" key={label}><span>{label}</span><span>{description}</span></div>)}
          <p style={{ fontSize: 12, lineHeight: 1.7, color: '#70706b', margin: '18px 0 0' }}>Review the recording, compare the measurements with your criteria, and see what needs a closer look.</p>
        </aside>
      </motion.section>

      {/* how it works */}
      <section style={{ background: '#F8F7F4', borderTop: '1px solid #eee', borderBottom: '1px solid #eee' }}>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}
          variants={fadeUp} style={{ maxWidth: 860, margin: '0 auto', padding: '56px 24px' }}>
          <p style={{ ...overline, textAlign: 'center', marginBottom: 32 }}>How it works</p>
          <motion.div variants={staggerContainer()} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}
            style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
            <Step n="01" icon={<ScanLine size={20} color="#1a1a1a" strokeWidth={1.5} />} title="Connect your application"
              body="Use a branded link, add a widget to your website, or connect your hiring software through the API." />
            <Step n="02" icon={<BarChart3 size={20} color="#1a1a1a" strokeWidth={1.5} />} title="Applicants show their skills"
              body="Applicants complete the CookCredit knife assessment. Choose the questions you need and allow up to three attempts." />
            <Step n="03" icon={<UserCheck size={20} color="#1a1a1a" strokeWidth={1.5} />} title="Review the evidence"
              body="See the recording, measured results, and limitations. Your team decides who advances." />
          </motion.div>
        </motion.div>
      </section>

      {/* closing CTA */}
      <section style={{ background: '#1A1A1A', color: '#fff' }}>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.4 }}
          variants={fadeUp} style={{ maxWidth: 720, margin: '0 auto', padding: '64px 24px', textAlign: 'center' }}>
          <h2 style={{ fontFamily: SERIF, fontSize: 'clamp(26px, 5vw, 36px)', fontWeight: 400, margin: '0 0 24px' }}>
            Make room for real skills.
          </h2>
          <motion.button {...buttonPress} onClick={() => goWorkspace('/business/roles')} style={{
            ...primary, background: '#fff', color: '#1a1a1a',
          }}>
            Open your workspace <ArrowRight size={16} strokeWidth={1.5} />
          </motion.button>
        </motion.div>
      </section>
    </div>
  )
}
