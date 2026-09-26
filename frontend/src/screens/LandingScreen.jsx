/**
 * LandingScreen — public marketing page. Pitches Mise as trusted, verified
 * household help (cleaning, cooking, childcare, elder care, errands) booked
 * in minutes. Routes into /signup (client or helper), /browse, /business.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import InfoModal from '../components/InfoModal'
import { TermsContent, PrivacyContent, BiometricContent } from '../components/InfoPages'
import { ShieldCheck, UserCheck, Star, ArrowRight } from 'lucide-react'
import { fadeUp, staggerContainer, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C'

const pillars = [
  { Icon: ShieldCheck, title: 'ID + background checked', body: 'Every helper passes an identity verification check and a background check before they can take a booking.' },
  { Icon: UserCheck, title: 'Vetted specialties', body: 'Cleaning, cooking, childcare, elder care, laundry, errands — browse by the specific help you need, near you.' },
  { Icon: Star, title: 'Rated by real clients', body: 'Every booking ends in a review. See ratings, repeat-client counts, and verified badges before you book.' },
]

export default function LandingScreen() {
  const navigate = useNavigate()
  const [infoModal, setInfoModal] = useState(null)
  const t = { terms: 'Terms', privacy: 'Privacy', biometric: 'Biometric notice' }

  return (
    <div style={{ background: '#FEFDFB', minHeight: '100vh', overflowX: 'hidden' }}>

      {/* HERO */}
      <section style={{ position: 'relative', minHeight: '94vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: 'radial-gradient(1200px 600px at 50% -10%, #1B4B41 0%, #14332C 55%, #0e0e0e 100%)' }}>
        <nav style={{ position: 'absolute', top: 0, left: 0, right: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ShieldCheck size={16} color="white" strokeWidth={1.5} />
            </div>
            <span style={{ color: 'white', fontFamily: SERIF, fontSize: 18, fontWeight: 300, letterSpacing: 2 }}>MISE</span>
          </div>
          <motion.button whileTap={tapScale} onClick={() => navigate('/login')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5, color: 'rgba(255,255,255,0.8)', fontSize: 13, letterSpacing: 0.5 }}>
            Sign in
          </motion.button>
        </nav>

        <motion.div variants={staggerContainer(0.12, 0.05)} initial="hidden" animate="show"
          style={{ position: 'relative', zIndex: 10, textAlign: 'center', padding: '60px 24px 0', maxWidth: 720, margin: '0 auto' }}>
          <motion.p variants={fadeUp} style={{ fontSize: 12, letterSpacing: 3, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', margin: '0 0 18px' }}>Household help, verified</motion.p>
          <motion.h1 variants={fadeUp} style={{ fontFamily: SERIF, fontSize: 'clamp(36px, 8vw, 60px)', fontWeight: 300, color: 'white', lineHeight: 1.12, letterSpacing: 0.5, margin: '0 0 24px' }}>
            Help for your home, booked in minutes.
          </motion.h1>
          <motion.p variants={fadeUp} style={{ fontSize: 16, color: 'rgba(255,255,255,0.78)', lineHeight: 1.7, fontWeight: 300, letterSpacing: 0.3, margin: '0 auto 36px', maxWidth: 560 }}>
            Mise connects you with background-checked, ID-verified helpers for cleaning, cooking,
            childcare, elder care, and everyday household tasks — so you can hire trusted help
            without the guesswork.
          </motion.p>
          <motion.div variants={fadeUp} style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <motion.button onClick={() => navigate('/signup')} whileHover={{ scale: 1.02 }} whileTap={tapScale}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 34px', background: 'white', color: '#1a1a1a', fontSize: 14, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', border: 'none', cursor: 'pointer' }}>
              Find help <ArrowRight size={16} strokeWidth={2} />
            </motion.button>
            <motion.button onClick={() => navigate('/browse')} whileHover={{ scale: 1.02 }} whileTap={tapScale}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 34px', background: 'transparent', color: 'white', fontSize: 14, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', border: '1px solid rgba(255,255,255,0.3)', cursor: 'pointer' }}>
              Browse helpers
            </motion.button>
          </motion.div>
        </motion.div>
      </section>

      {/* TRUST PILLARS */}
      <section style={{ padding: '88px 24px', background: '#FEFDFB' }}>
        <div style={{ maxWidth: 860, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 44 }}>
            <ShieldCheck size={26} color={GREEN} strokeWidth={1.5} style={{ marginBottom: 12 }} />
            <h2 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 6vw, 40px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>Why families trust Mise</h2>
          </div>
          <motion.div variants={staggerContainer(0.1)} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.3 }}
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
            {pillars.map(p => (
              <motion.div key={p.title} variants={fadeUp} whileHover={hoverLift}
                style={{ border: '1px solid #e5e5e5', background: '#fff', padding: '26px 22px' }}>
                <p.Icon size={24} color="#1a1a1a" strokeWidth={1.5} style={{ marginBottom: 14 }} />
                <h3 style={{ fontFamily: SERIF, fontSize: 21, fontWeight: 500, color: '#1a1a1a', margin: '0 0 8px' }}>{p.title}</h3>
                <p style={{ fontSize: 14, color: '#777', lineHeight: 1.6, margin: 0 }}>{p.body}</p>
              </motion.div>
            ))}
          </motion.div>
          <p style={{ textAlign: 'center', fontSize: 13, color: '#999', lineHeight: 1.7, margin: '36px auto 0', maxWidth: 540 }}>
            Every helper's identity and background check are verified before they can be booked.
            See exactly how in our biometric notice below.
          </p>
        </div>
      </section>

      {/* CTA BAND */}
      <motion.section variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.4 }}
        style={{ padding: '80px 24px', background: '#1A1A1A', textAlign: 'center' }}>
        <div style={{ maxWidth: 600, margin: '0 auto' }}>
          <p style={{ fontSize: 11, letterSpacing: 3, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', margin: '0 0 16px' }}>Ready to get help?</p>
          <h2 style={{ fontFamily: SERIF, fontSize: 'clamp(26px, 5vw, 36px)', fontWeight: 400, color: 'white', margin: '0 0 16px' }}>Become a helper, or find one today</h2>
          <p style={{ fontSize: 15, color: 'rgba(255,255,255,0.55)', lineHeight: 1.7, fontWeight: 300, margin: '0 auto 30px', maxWidth: 480 }}>
            Helpers complete an identity verification check and a background check, then set their
            own rate and service area. Clients browse verified helpers and book in minutes.
          </p>
          <motion.button onClick={() => navigate('/signup')} whileHover={{ scale: 1.02 }} whileTap={tapScale}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 32px', background: 'white', color: '#1a1a1a', fontSize: 14, fontWeight: 600, letterSpacing: 0.5, border: 'none', cursor: 'pointer' }}>
            Get started <ArrowRight size={16} strokeWidth={1.75} />
          </motion.button>
        </div>
      </motion.section>

      {/* FOOTER */}
      <footer style={{ padding: '56px 24px', background: '#0F0F0F', borderTop: '1px solid #333' }}>
        <div style={{ maxWidth: 520, margin: '0 auto', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 28, marginBottom: 20, flexWrap: 'wrap' }}>
            {[['Terms', 'terms'], ['Privacy', 'privacy'], ['Biometric', 'biometric']].map(([label, key]) => (
              <motion.button key={key} whileTap={tapScale} onClick={() => setInfoModal(key)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', fontSize: 11, cursor: 'pointer', letterSpacing: 2, textTransform: 'uppercase' }}>{label}</motion.button>
            ))}
            <motion.button whileTap={tapScale} onClick={() => navigate('/login')} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', fontSize: 11, cursor: 'pointer', letterSpacing: 2, textTransform: 'uppercase' }}>Sign in</motion.button>
          </div>
          <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12, lineHeight: 1.6, margin: '0 0 10px' }}>
            Questions? <a href="mailto:hello@mise.app" style={{ color: 'rgba(255,255,255,0.5)' }}>hello@mise.app</a>
          </p>
          <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: 11, letterSpacing: 2, margin: 0 }}>{'©'} 2026 MISE</p>
        </div>
      </footer>

      <InfoModal open={!!infoModal} onClose={() => setInfoModal(null)} title={{ terms: t.terms, privacy: t.privacy, biometric: t.biometric }[infoModal]}>
        {infoModal === 'terms' && <TermsContent />}
        {infoModal === 'privacy' && <PrivacyContent />}
        {infoModal === 'biometric' && <BiometricContent />}
      </InfoModal>
    </div>
  )
}
