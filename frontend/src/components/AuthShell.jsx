/**
 * AuthShell — responsive chrome for the auth screens (login, signup, forgot, verify).
 *
 * The product is a desktop WEBSITE and a mobile APP from one codebase. This wrapper is the only
 * thing that differs between them on the auth path; the screen content (dark brand band + form)
 * is identical. Via useIsDesktop (matchMedia '(min-width:900px)'):
 *   • desktop → a centered editorial card floating on warm paper (#F1EEE8), not a 430px phone
 *     strip on a black void — what a B2B buyer arriving from the full-bleed landing expects.
 *   • mobile  → the existing full-height phone frame (dark backdrop, white card).
 *
 * Editorial system preserved exactly: Cormorant Garamond + Inter, borderRadius 0 (only the logo
 * chip is a circle), Lucide strokeWidth 1.5, monochrome palette, no emoji.
 */
import { motion } from 'framer-motion'
import useIsDesktop from '../hooks/useIsDesktop'
import { scaleIn, fadeIn } from '../styles/motion'

function PolicyLinks() {
  return <nav aria-label="Account policies" style={{ display: 'flex', justifyContent: 'center', gap: 20, flexWrap: 'wrap', fontSize: 13, padding: '4px 24px 24px' }}>
    <a href="https://cookcredit.com/privacy.html" target="_blank" rel="noopener noreferrer" style={{ color: '#636960' }}>Privacy Policy</a>
    <a href="https://cookcredit.com/terms.html" target="_blank" rel="noopener noreferrer" style={{ color: '#636960' }}>Terms of Use</a>
  </nav>
}

export default function AuthShell({ children }) {
  const isDesktop = useIsDesktop()

  if (isDesktop) {
    return (
      <div className="cc-hiring-page" style={{ minHeight: '100svh', background: '#F1EEE8', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px' }}>
        <motion.div
          variants={scaleIn}
          initial="hidden"
          animate="show"
          style={{ width: '100%', maxWidth: 440, background: '#FEFDFB', border: '1px solid #e5e5e5' }}
        >
          {children}
          <PolicyLinks />
        </motion.div>
      </div>
    )
  }

  return (
    <div className="cc-hiring-page" style={{ background: '#F4F1EA', minHeight: '100svh', display: 'flex', justifyContent: 'center' }}>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="show"
        style={{ width: '100%', maxWidth: 430, minHeight: '100svh', background: '#FEFDFB' }}
      >
        {children}
        <PolicyLinks />
      </motion.div>
    </div>
  )
}
