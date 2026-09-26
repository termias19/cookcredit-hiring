/**
 * BottomNav — role-aware bottom navigation.
 *
 * Client tabs: Find Help, Post a Task, Bookings, Household, Profile
 * Helper tabs: Dashboard, Requests, Bookings, Verify, Profile
 *
 * Hidden on auth screens (/login, /signup, etc.) and detail screens (/cook/:id, /booking/:id).
 */
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { Search, CalendarCheck, User, LayoutDashboard, Send, Inbox, Home, ShieldCheck } from 'lucide-react'
import { MARKETPLACE_ENABLED, BEAM_ENABLED } from '../config'
import { useNotifications } from '../context/NotificationContext'

// Tabs hidden until the booking/pantry transaction layer ships (see config.js).
const MARKETPLACE_TABS = ['/bookings', '/pantry']
// Beam tabs hidden unless BEAM_ENABLED (independent of the marketplace flag).
const BEAM_TABS = ['/beam', '/beams']

const EATER_TABS = [
  { path: '/browse',   label: 'Find Help', Icon: Search,        match: ['/browse'] },
  { path: '/beam',     label: 'Post Task', Icon: Send,          match: ['/beam'] },
  { path: '/bookings', label: 'Bookings',  Icon: CalendarCheck, match: ['/bookings'] },
  { path: '/pantry',   label: 'Household', Icon: Home,          match: ['/pantry'] },
  { path: '/profile',  label: 'Profile',   Icon: User,          match: ['/profile'] },
]

const COOK_TABS = [
  { path: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard, match: ['/dashboard'] },
  { path: '/beams',     label: 'Requests',  Icon: Inbox,           match: ['/beams'] },
  { path: '/bookings',  label: 'Bookings',  Icon: CalendarCheck,   match: ['/bookings'] },
  { path: '/skill',     label: 'Verify',    Icon: ShieldCheck,     match: ['/skill'] },
  { path: '/profile',   label: 'Profile',   Icon: User,            match: ['/profile'] },
]

/* Paths where the nav should be hidden */
const HIDDEN_PATTERNS = [
  '/', '/login', '/signup', '/forgot', '/verify', '/install',
]
function shouldHide(pathname) {
  if (HIDDEN_PATTERNS.includes(pathname)) return true
  if (pathname.startsWith('/cook/')) return true
  if (pathname.startsWith('/booking/')) return true
  return false
}

export default function BottomNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const { profile } = useAuth()
  const { unreadCount } = useNotifications()

  if (shouldHide(location.pathname)) return null

  const roles = profile?.roles || []
  const active = profile?.activeRole || profile?.active_role || 'eater'
  // Cook tabs only when the user holds the cook role AND is toggled to it.
  const baseTabs = active === 'cook' && roles.includes('cook') ? COOK_TABS : EATER_TABS
  const hidden = [
    ...(MARKETPLACE_ENABLED ? [] : MARKETPLACE_TABS),
    ...(BEAM_ENABLED ? [] : BEAM_TABS),
  ]
  const tabs = baseTabs.filter(t => !hidden.includes(t.path))

  return (
    <nav style={{
      position: 'fixed',
      bottom: 0,
      left: '50%',
      transform: 'translateX(-50%)',
      width: 'min(430px, 100vw)',
      background: '#fff',
      borderTop: '1px solid #f0f0f0',
      display: 'flex',
      justifyContent: 'space-around',
      alignItems: 'center',
      height: 64,
      paddingBottom: 'env(safe-area-inset-bottom, 0px)',
      zIndex: 100,
    }}>
      {tabs.map(({ path, label, Icon, match }) => {
        const active = match.some(m => location.pathname === m)
        const color = active ? '#1a1a1a' : '#777'

        return (
          <motion.button
            key={path}
            onClick={() => navigate(path)}
            whileTap={{ scale: 0.92 }}
            style={{
              position: 'relative',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 4,
              padding: '10px 0 8px',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              WebkitTapHighlightColor: 'transparent',
            }}
          >
            {active && (
              <motion.span
                layoutId="bottomNavActivePill"
                transition={{ type: 'spring', stiffness: 500, damping: 32 }}
                style={{
                  position: 'absolute', top: 2, width: 32, height: 32, borderRadius: '50%',
                  background: '#F0F2ED',
                }}
              />
            )}
            <motion.span
              animate={{ scale: active ? 1.08 : 1 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
              style={{ position: 'relative', display: 'inline-flex' }}
            >
              <Icon size={22} color={color} strokeWidth={1.5} />
              {BEAM_TABS.includes(path) && unreadCount > 0 && (
                <span style={{
                  position: 'absolute', top: -5, right: -9, minWidth: 16, height: 16,
                  padding: '0 4px', background: '#1F6F5C', color: '#fff', fontSize: 10,
                  fontWeight: 700, borderRadius: 8, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', lineHeight: 1,
                }}>{unreadCount > 9 ? '9+' : unreadCount}</span>
              )}
            </motion.span>
            <span style={{
              position: 'relative',
              fontSize: 10,
              fontWeight: active ? 600 : 400,
              color,
              letterSpacing: 0.3,
              whiteSpace: 'nowrap',
            }}>
              {label}
            </span>
          </motion.button>
        )
      })}
    </nav>
  )
}
