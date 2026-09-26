/**
 * TopNav — desktop website navigation (the web-layout counterpart to BottomNav).
 *
 * Rendered by Shell only on desktop widths and only when showNav is on. Role-aware
 * like BottomNav: cook tabs require holding the cook role AND being toggled to it.
 */
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { MARKETPLACE_ENABLED, BEAM_ENABLED } from '../config'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const MARKETPLACE_TABS = ['/bookings', '/pantry']  // hidden until the transaction layer ships
const BEAM_TABS = ['/beam', '/beams']              // hidden unless BEAM_ENABLED

const EATER_TABS = [
  { path: '/browse', label: 'Find Help' },
  { path: '/beam', label: 'Post Task' },
  { path: '/bookings', label: 'Bookings' },
  { path: '/pantry', label: 'Household' },
]
const COOK_TABS = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/beams', label: 'Requests' },
  { path: '/bookings', label: 'Bookings' },
  { path: '/skill', label: 'Verify' },
  { path: '/payouts', label: 'Payouts' },
]

export default function TopNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const { profile } = useAuth()

  const roles = profile?.roles || []
  const active = profile?.activeRole || profile?.active_role || 'eater'
  const isCook = active === 'cook' && roles.includes('cook')
  const baseTabs = isCook ? COOK_TABS : EATER_TABS
  const hidden = [
    ...(MARKETPLACE_ENABLED ? [] : MARKETPLACE_TABS),
    ...(BEAM_ENABLED ? [] : BEAM_TABS),
  ]
  const tabs = baseTabs.filter(t => !hidden.includes(t.path))
  const home = isCook ? '/dashboard' : '/browse'

  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
      background: 'rgba(254,253,251,0.92)', backdropFilter: 'saturate(180%) blur(8px)',
      borderBottom: '1px solid #ececec',
    }}>
      <div style={{
        maxWidth: 1080, margin: '0 auto', padding: '0 28px', height: 64,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {/* wordmark */}
        <motion.button
          onClick={() => navigate(home)}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginRight: 'auto',
            display: 'flex', alignItems: 'baseline', gap: 8,
          }}>
          <span style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a', letterSpacing: 0.5 }}>Mise</span>
          <span style={{ fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: '#767676' }}>
            {isCook ? 'Helper' : 'Client'}
          </span>
        </motion.button>

        {/* links */}
        {tabs.map(({ path, label }) => {
          const on = location.pathname === path
          return (
            <button key={path} onClick={() => navigate(path)} style={{
              position: 'relative',
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '8px 14px', fontSize: 14, letterSpacing: 0.3,
              color: on ? '#1a1a1a' : '#777', fontWeight: on ? 600 : 400,
            }}>
              {label}
              {on && (
                <motion.span
                  layoutId="topNavActiveUnderline"
                  transition={{ type: 'spring', stiffness: 500, damping: 34 }}
                  style={{
                    position: 'absolute', left: 14, right: 14, bottom: 4, height: 2,
                    background: '#1F6F5C', borderRadius: 1,
                  }}
                />
              )}
            </button>
          )
        })}

        {/* profile */}
        <motion.button
          onClick={() => navigate('/profile')}
          aria-label="Profile"
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          style={{
            marginLeft: 8, width: 36, height: 36, borderRadius: '50%', cursor: 'pointer',
            border: '1px solid #e5e5e5', background: '#fff', overflow: 'hidden',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: SERIF, fontSize: 16, color: '#1a1a1a',
          }}>
          {profile?.photoUrl
            ? <img src={profile.photoUrl} alt="" width={36} height={36} loading="lazy" style={{ width: 36, height: 36, objectFit: 'cover' }} />
            : (profile?.name || 'U').trim().charAt(0).toUpperCase()}
        </motion.button>
      </div>
    </nav>
  )
}
