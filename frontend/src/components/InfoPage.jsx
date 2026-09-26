/**
 * InfoPage — full-page, shareable shell for the legal/help docs (stable URLs
 * /about /privacy /terms /biometric /help), reusing the same content components
 * as the in-flow InfoModal. Editorial: Cormorant title, monochrome, sharp corners.
 */
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import { useLang } from '../context/LangContext'
import { AboutContent, PrivacyContent, TermsContent, BiometricContent, HelpContent } from './InfoPages'
import { fadeUp, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', Georgia, serif"
const PAGES = {
  about: { Content: AboutContent, titleKey: 'about', fallback: 'About' },
  privacy: { Content: PrivacyContent, titleKey: 'privacy', fallback: 'Privacy' },
  terms: { Content: TermsContent, titleKey: 'terms', fallback: 'Terms' },
  biometric: { Content: BiometricContent, titleKey: 'biometric', fallback: 'Biometric Notice' },
  help: { Content: HelpContent, titleKey: 'help', fallback: 'Help' },
}

export default function InfoPage({ page }) {
  const navigate = useNavigate()
  const { t } = useLang()
  const cfg = PAGES[page]
  if (!cfg) return null
  const { Content } = cfg

  return (
    <div style={{ minHeight: '100vh', background: '#fff' }}>
      <div style={{ position: 'sticky', top: 0, background: '#fff', borderBottom: '1px solid #eee',
        padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10, zIndex: 10 }}>
        <motion.button onClick={() => navigate(-1)} aria-label="Back" whileHover={{ scale: 1.05 }} whileTap={tapScale}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36,
            border: '1px solid #e5e5e5', background: '#fff', cursor: 'pointer' }}>
          <ArrowLeft size={18} strokeWidth={1.5} color="#1a1a1a" />
        </motion.button>
        <span style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a' }}>{t[cfg.titleKey] || cfg.fallback}</span>
      </div>
      <motion.div variants={fadeUp} initial="hidden" animate="show"
        style={{ maxWidth: 680, margin: '0 auto', padding: '24px 20px 64px' }}>
        <Content />
      </motion.div>
    </div>
  )
}
