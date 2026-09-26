import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { DURATION, EASE, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

// Backdrop fade + panel slide-up-and-settle — replaces the old CSS
// `slideUp` keyframe with a framer-motion AnimatePresence pair so the modal
// can animate out on close too, not just pop away.
const backdropVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, transition: { duration: DURATION.fast, ease: EASE } },
}

const panelVariants = {
  hidden: { opacity: 0, y: 48 },
  show: { opacity: 1, y: 0, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, y: 32, transition: { duration: DURATION.fast, ease: EASE } },
}

export default function InfoModal({ open, onClose, title, children }) {
  const panelRef = useRef(null)

  // Dialog semantics: focus moves into the sheet on open (and Escape closes) so
  // keyboard/SR users aren't left behind on the page underneath.
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement
    panelRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (prev && prev.focus) prev.focus()
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="info-modal-backdrop"
          onClick={onClose}
          variants={backdropVariants}
          initial="hidden"
          animate="show"
          exit="exit"
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
          }}>
          <motion.div ref={panelRef} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
            tabIndex={-1} onClick={e => e.stopPropagation()}
            variants={panelVariants}
            style={{
              background: '#FEFDFB', width: '100%', maxWidth: 430, maxHeight: '85vh',
              display: 'flex', flexDirection: 'column',
              outline: 'none',
            }}>
            <div style={{ width: 36, height: 3, background: '#e5e5e5', margin: '10px auto 0' }} />
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 20px 12px', borderBottom: '1px solid #e5e5e5',
            }}>
              <span style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 400, color: '#1a1a1a' }}>{title}</span>
              <motion.button onClick={onClose} aria-label="Close" whileHover={{ scale: 1.06 }} whileTap={tapScale} style={{
                width: 28, height: 28, border: '1px solid #e5e5e5', background: 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', padding: 0,
              }}>
                <X size={14} color="#767676" strokeWidth={1.5} />
              </motion.button>
            </div>
            <div style={{
              padding: '16px 20px 32px', overflowY: 'auto',
              fontSize: 13, lineHeight: 1.7, color: '#555',
            }}>
              {children}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
