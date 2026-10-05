/** Shared responsive account frame; authentication stays in the existing screens. */
import { Link } from 'react-router-dom'
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
      <div className="cc-hiring-page" style={{ minHeight: '100svh', background: 'var(--cc-canvas)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px' }}>
        <motion.div
          variants={scaleIn}
          initial="hidden"
          animate="show"
          style={{ width: '100%', maxWidth: 440, background: 'var(--cc-surface)', border: '1px solid var(--cc-border)' }}
        >
          <Link className="cc-auth-home" to="/">Back to CookCredit Hiring</Link>
          {children}
          <PolicyLinks />
        </motion.div>
      </div>
    )
  }

  return (
    <div className="cc-hiring-page" style={{ background: 'var(--cc-canvas)', minHeight: '100svh', display: 'flex', justifyContent: 'center' }}>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="show"
        style={{ width: '100%', maxWidth: 430, minHeight: '100svh', background: 'var(--cc-surface)' }}
      >
        <Link className="cc-auth-home" to="/">Back to CookCredit Hiring</Link>
          {children}
        <PolicyLinks />
      </motion.div>
    </div>
  )
}
