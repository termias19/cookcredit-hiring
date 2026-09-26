import { Link } from 'react-router-dom'
function AccountNav() {
  return <nav aria-label="CookCredit" style={{ display: 'flex', gap: 24, padding: 20, background: '#FEFDFB' }}><Link to="/business">CookCredit</Link><Link to="/applications">My applications</Link><Link to="/profile">Profile</Link></nav>
}
import useIsDesktop from '../hooks/useIsDesktop'

/**
 * Shell — one component, two layouts.
 *   mobile  (< 900px): a 430px phone frame with a fixed BottomNav (the app layout).
 *   desktop (>= 900px): a top NavBar with the content centered in a web column on a
 *                       warm page background (the website layout).
 * Individual screens don't change — they just reflow into whichever shell is active.
 * `showNav={false}` (drill-in / onboarding screens) suppresses both navs.
 * `wide` (desktop only) drops the narrow 560px boxed-card layout for a full-bleed
 * page — for listing/grid screens (Browse, dashboards) that want to use the whole
 * viewport rather than read like a mobile screen stretched onto a desktop.
 */
export default function Shell({ children, header, showNav = true, wide = false }) {
  const isDesktop = useIsDesktop()

  if (isDesktop) {
    if (wide) {
      return (
        <div style={{ minHeight: '100svh', background: '#FEFDFB', paddingTop: showNav ? 64 : 0 }}>
          {showNav && <AccountNav />}
          {header}
          <div style={{ maxWidth: 1360, margin: '0 auto', padding: '0 32px 56px' }}>{children}</div>
        </div>
      )
    }
    return (
      <div style={{ minHeight: '100svh', background: '#F1EEE8', paddingTop: showNav ? 64 : 0 }}>
        {showNav && <AccountNav />}
        <div style={{ padding: showNav ? '28px 20px 56px' : '0' }}>
          <div style={{
            width: 'min(560px, 100%)', margin: '0 auto', background: '#FEFDFB',
            minHeight: showNav ? 'auto' : '100svh',
            border: '1px solid #e7e3db',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 12px 40px rgba(0,0,0,0.06)',
            overflow: 'hidden',
          }}>
            {header}
            <div>{children}</div>
          </div>
        </div>
      </div>
    )
  }

  // ── mobile: phone-frame app layout ──
  return (
    <div style={{
      width: 'min(430px,100vw)', minHeight: '100svh',
      background: '#FEFDFB',
      margin: '0 auto', position: 'relative', overflowX: 'clip',
    }}>
      {header && (
        <div style={{ position: 'sticky', top: 0, zIndex: 50 }}>
          {header}
        </div>
      )}
      <div style={{ paddingBottom: showNav ? 'calc(72px + env(safe-area-inset-bottom, 0px))' : 'env(safe-area-inset-bottom, 0px)' }}>
        {children}
      </div>
      {showNav && <AccountNav />}
    </div>
  )
}
