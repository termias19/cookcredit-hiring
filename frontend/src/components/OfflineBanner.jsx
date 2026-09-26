/**
 * OfflineBanner — a thin fixed banner while the browser reports no network.
 * Purely informational (requests still fail fast with their own error states);
 * critical on Addis connectivity where drops are routine. navigator.onLine
 * has false positives (captive portals) but never blocks anything here.
 */
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { WifiOff } from 'lucide-react'
import { useLang } from '../context/LangContext'
import { DURATION, EASE } from '../styles/motion'

export default function OfflineBanner() {
  const { t } = useLang()
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  return (
    <AnimatePresence>
      {!online && (
        <motion.div
          key="offline-banner"
          role="status"
          initial={{ y: '-100%', opacity: 0 }}
          animate={{ y: 0, opacity: 1, transition: { duration: DURATION.base, ease: EASE } }}
          exit={{ y: '-100%', opacity: 0, transition: { duration: DURATION.fast, ease: EASE } }}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9998,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            background: '#1a1a1a', color: '#fff', fontSize: 12.5, padding: '8px 14px',
            letterSpacing: 0.2, lineHeight: 1.4, textAlign: 'center',
          }}>
          <WifiOff size={14} strokeWidth={1.75} style={{ flex: 'none' }} />
          {t.offline_banner}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
