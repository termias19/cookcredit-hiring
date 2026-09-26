import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { canInstallNatively, triggerInstall, isIOS, isStandalone } from '../utils/pwaInstall'
import { useLang } from '../context/LangContext'
import { useAuth } from '../context/AuthContext'
import { homeFor } from '../utils/homeFor'
import useIsDesktop from '../hooks/useIsDesktop'
import { Zap, Bell, Users, Check } from 'lucide-react'
import { fadeUp, scaleIn, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

export default function InstallPromptScreen() {
  const navigate = useNavigate()
  const { t } = useLang()
  const { profile } = useAuth()
  const isDesktop = useIsDesktop()
  const [installing, setInstalling] = useState(false)
  const [installed, setInstalled] = useState(false)
  // The add-to-home-screen nudge is a PHONE-APP concept — skip it entirely on desktop (the website),
  // already installed, or if the user dismissed it; those users go straight to their resolved home.
  const shouldSkip = isStandalone() || isDesktop || !!sessionStorage.getItem('installSkipped')

  // Continue to the post-auth home: the one-shot dest the login flow carried, else the role home.
  const go = () => {
    let dest = null
    try { const d = sessionStorage.getItem('postAuthDest'); if (d) { dest = d; sessionStorage.removeItem('postAuthDest') } } catch { /* ignore */ }
    navigate(dest || homeFor(profile), { replace: true })
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount; go()/shouldSkip are read intentionally
  useEffect(() => { if (shouldSkip) go() }, [])
  if (shouldSkip) return null

  async function handleInstall() {
    if (canInstallNatively()) {
      setInstalling(true)
      const accepted = await triggerInstall()
      if (accepted) { setInstalled(true); setTimeout(go, 2000) }
      else setInstalling(false)
    }
  }

  function handleDone() {
    go()
  }

  function handleSkip() {
    sessionStorage.setItem('installSkipped', 'true')
    go()
  }

  if (installed) return (
    <motion.div variants={staggerContainer(0.08, 0.05)} initial="hidden" animate="show"
      style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 24px', background: '#FEFDFB' }}>
      <motion.div variants={scaleIn} style={{ width: 56, height: 56, border: '1px solid rgba(45,106,79,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
        <motion.div initial={{ scale: 0, rotate: -45 }} animate={{ scale: 1, rotate: 0 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}>
          <Check size={24} color="#1F6F5C" strokeWidth={1.5} />
        </motion.div>
      </motion.div>
      <motion.div variants={fadeUp} style={{ fontFamily: SERIF, fontSize: 22, fontWeight: 400, color: '#1a1a1a', marginBottom: 6, textAlign: 'center' }}>{t.install_success_title || 'App installed'}</motion.div>
      <motion.div variants={fadeUp} style={{ fontSize: 13, color: '#999', textAlign: 'center', marginBottom: 20 }}>{t.install_success_sub || 'Find Mise on your home screen'}</motion.div>
      <motion.div variants={fadeUp} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <div style={{ width: 44, height: 44, background: '#1A1A1A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontFamily: SERIF, fontSize: 14, fontWeight: 500, color: 'white' }}>M</span>
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: '#1a1a1a' }}>Mise</div>
          <div style={{ fontSize: 11, color: '#999' }}>mise.app</div>
        </div>
      </motion.div>
    </motion.div>
  )

  const showNative = canInstallNatively()
  const showIOS = isIOS()

  return (
    <motion.div variants={staggerContainer(0.08, 0.05)} initial="hidden" animate="show"
      style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 24px', background: '#FEFDFB' }}>
      <motion.div variants={fadeUp} style={{ display: 'flex', gap: 6, marginBottom: 24 }}>
        <div style={{ width: 8, height: 3, background: '#1F6F5C' }} />
        <div style={{ width: 8, height: 3, background: '#1F6F5C' }} />
        <div style={{ width: 20, height: 3, background: '#3B5166' }} />
      </motion.div>

      <motion.div variants={scaleIn} style={{ width: 56, height: 56, background: '#1A1A1A', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
        <span style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 500, color: 'white' }}>M</span>
      </motion.div>

      <motion.div variants={fadeUp} style={{ fontFamily: SERIF, fontSize: 22, fontWeight: 400, color: '#1a1a1a', marginBottom: 6, textAlign: 'center' }}>{t.install_title || 'Add to home screen'}</motion.div>
      <motion.div variants={fadeUp} style={{ fontSize: 13, color: '#999', textAlign: 'center', marginBottom: 24, lineHeight: 1.5 }}>{t.install_subtitle || 'Get the full app experience'}</motion.div>

      <motion.div variants={staggerContainer(0.08)} style={{ width: '100%', maxWidth: 320, display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
        {[
          { Icon: Zap, text: t.install_benefit_1 || 'Instant access from home screen' },
          { Icon: Bell, text: t.install_benefit_2 || 'Push notifications for bookings' },
          { Icon: Users, text: t.install_benefit_3 || 'Full-screen experience' },
        ].map((b, i) => (
          <motion.div key={i} variants={fadeUp} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, color: '#1a1a1a' }}>
            <div style={{ width: 32, height: 32, border: '1px solid #e5e5e5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <b.Icon size={14} color="#555" strokeWidth={1.5} />
            </div>
            <span>{b.text}</span>
          </motion.div>
        ))}
      </motion.div>

      {showNative && (
        <motion.button variants={fadeUp} {...buttonPress} onClick={handleInstall} disabled={installing} style={{ width: '100%', maxWidth: 320, padding: 14, background: '#1F6F5C', color: 'white', border: 'none', fontSize: 15, fontWeight: 500, cursor: 'pointer', marginBottom: 10 }}>
          {installing ? (t.install_adding || 'Adding\u2026') : (t.install_button || 'Add to home screen')}
        </motion.button>
      )}

      {showIOS && (
        <motion.div variants={fadeUp} style={{ width: '100%', maxWidth: 320, border: '1px solid #e5e5e5', padding: 16, marginBottom: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: '#1a1a1a', marginBottom: 12 }}>{t.install_ios_title || 'Install on iOS'}</div>
          {[
            { num: '1', text: t.install_ios_step1 || 'Tap the <strong>Share</strong> button' },
            { num: '2', text: t.install_ios_step2 || 'Scroll and tap <strong>Add to Home Screen</strong>' },
            { num: '3', text: t.install_ios_step3 || 'Tap <strong>Add</strong>' },
          ].map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10, fontSize: 12, color: '#777', lineHeight: 1.5 }}>
              <div style={{ width: 22, height: 22, background: '#1F6F5C', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 600, flexShrink: 0 }}>{s.num}</div>
              <span dangerouslySetInnerHTML={{ __html: s.text }} />
            </div>
          ))}
          <motion.button {...buttonPress} onClick={handleDone} style={{ width: '100%', padding: 12, background: '#1F6F5C', color: 'white', border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer', marginTop: 4 }}>
            {t.install_ios_done || 'Done'}
          </motion.button>
        </motion.div>
      )}

      {!showNative && !showIOS && (
        <motion.div variants={fadeUp} style={{ fontSize: 12, color: '#999', textAlign: 'center', marginBottom: 10 }}>{t.install_desktop_hint || 'Use your browser menu to install'}</motion.div>
      )}

      <motion.button variants={fadeUp} whileTap={tapScale} onClick={handleSkip} style={{ background: 'transparent', border: 'none', color: '#999', fontSize: 13, cursor: 'pointer', padding: 10 }}>
        {t.install_skip || 'Skip for now'}
      </motion.button>
    </motion.div>
  )
}
