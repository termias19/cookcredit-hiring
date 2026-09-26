/**
 * BusinessShell — two purpose-built layouts for the B2B workspace, same screens + data.
 *   Desktop (>=900px): a WEBSITE layout — fixed left sidebar nav + a wide content column.
 *   Mobile: the same light workspace with a horizontal navigation row.
 * Screens render their own `header`; on desktop it sits atop the content column, the sidebar owns
 * primary nav. `showNav` is accepted (for drop-in parity with Shell) but ignored.
 */
import { cloneElement, createElement, isValidElement } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { ChefHat, BriefcaseBusiness, Star, Users, CreditCard, Plus, Plug, Building2 } from 'lucide-react'
import useIsDesktop from '../hooks/useIsDesktop'
import { PREVIEW } from '../config'
import { useBusiness } from '../context/BusinessContext'
import { useLang } from '../context/LangContext'
import CookCreditBrand from './CookCreditBrand'
import HiringBottomNav from './HiringBottomNav'
import { useAuth } from '../context/AuthContext'

function OwnerAccessLink() {
  const { profile } = useAuth()
  const navigate = useNavigate()
  return profile?.isAccessOwner ? <button type="button" onClick={() => navigate('/owner/access')}
    style={{ border: '1px solid #d5dcd1', background: '#f3f6ef', color: '#1f6f5c', padding: '10px 14px', margin: '10px', fontSize: 13, cursor: 'pointer' }}>Manage hiring access</button> : null
}

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C'

const NAV = [
  { to: '/business/candidates', label: 'bn_candidates', base: '/business/candidate', icon: ChefHat },
  { to: '/business/roles', label: 'bn_roles', base: '/business/role', icon: BriefcaseBusiness },
  { to: '/business/shortlists', label: 'bn_shortlist', icon: Star },
  { to: '/business/team', label: 'bn_team', icon: Users },
  { to: '/business/integrations', label: 'bn_integrations', icon: Plug },
  { to: '/business/billing', label: 'bn_billing', icon: CreditCard },
]

function ProfileLink() {
  const { t } = useLang()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return <button type="button" aria-current={pathname === '/business/profile' ? 'page' : undefined}
    onClick={() => navigate('/business/profile')} style={{ display: 'flex', alignItems: 'center', gap: 10,
      width: '100%', marginTop: 18, padding: '14px 0 0', border: 0, borderTop: '1px solid #e3e0d9',
      background: 'none', color: GREEN, fontSize: 13, cursor: 'pointer', textAlign: 'left' }}>
    <span style={{ width: 34, height: 34, borderRadius: '50%', border: '1px solid #cbd8d0',
      display: 'grid', placeItems: 'center', flexShrink: 0, background: '#edf3ef' }}><Building2 size={18} strokeWidth={1.5} /></span>
    {t.bp_profile}
  </button>
}

function Sidebar() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const biz = useBusiness()
  const { t } = useLang()
  return (
    <aside style={{ width: 248, flexShrink: 0, background: '#FEFDFB', borderRight: '1px solid #e5e5e5',
      height: '100svh', position: 'fixed', top: 0, left: 0, zIndex: 100,
      display: 'flex', flexDirection: 'column', padding: '24px 16px', overflowY: 'auto' }}>
      <div style={{ padding: '0 8px' }}>
        <CookCreditBrand />
        <div style={{ fontSize: 10, letterSpacing: 2, color: '#70706b', textTransform: 'uppercase', marginTop: 2 }}>{t.bn_assessment}</div>
        {biz?.org?.name && <div style={{ fontSize: 12, color: '#777', marginTop: 16 }}>{biz.org.name}</div>}
      </div>

      <button onClick={() => navigate('/business/role/new')} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        margin: '18px 8px 16px', padding: '10px 12px', background: '#1F6F5C', color: '#fff', border: 'none', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
        <Plus size={15} strokeWidth={1.5} /> {t.bn_post}
      </button>

      <nav aria-label={t.bn_workspace} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(({ to, label, base, icon }) => {
          const active = pathname === to || (base && pathname.startsWith(base))
          return (
            <button key={to} aria-current={active ? 'page' : undefined} onClick={() => navigate(to)} style={{ display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 10px', background: active ? '#e8eee5' : 'none', border: 'none', cursor: 'pointer',
              textAlign: 'left', color: active ? GREEN : '#777', fontSize: 14 }}>
              {createElement(icon, { size: 17, strokeWidth: 1.5, color: active ? GREEN : '#999' })} {t[label]}
            </button>
          )
        })}
      </nav>

      <OwnerAccessLink />
      <div style={{ flex: 1 }} />
      <div style={{ padding: '0 8px' }}>
        <div style={{ fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#70706b' }}>{t.bn_plan}</div>
        <div style={{ fontSize: 13, color: '#1a1a1a', textTransform: 'capitalize', marginTop: 2 }}>{biz?.org?.integrationAccess?.earlyAccess ? t.bn_included : biz?.org?.plan || '—'}</div>
        <ProfileLink />
      </div>
    </aside>
  )
}

// Mobile equivalent of the sidebar — a sticky horizontal tab row under the screen header, so the
// workspace has consistent nav on phones (where the app Shell has no bottom nav) without each
// screen re-rendering its own links.
function MobileNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { t } = useLang()
  return (
    <div style={{ display: 'flex', gap: 2, overflowX: 'auto', padding: '0 10px', background: '#FEFDFB', borderBottom: '1px solid #eee' }}>
      {NAV.filter(item => ['/business/team', '/business/integrations', '/business/billing'].includes(item.to)).map(({ to, label, base, icon }) => {
        const active = pathname === to || (base && pathname.startsWith(base))
        return (
          <button key={to} aria-current={active ? 'page' : undefined} onClick={() => navigate(to)} style={{ flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '8px 11px', background: 'none', border: 'none', borderBottom: active ? '2px solid #1a1a1a' : '2px solid transparent',
            cursor: 'pointer', color: active ? '#1a1a1a' : '#999', fontSize: 13 }}>
            {createElement(icon, { size: 15, strokeWidth: 1.5, color: active ? GREEN : '#bbb' })} {t[label]}
          </button>
        )
      })}
    </div>
  )
}

export default function BusinessShell({ header, children }) {
  const isDesktop = useIsDesktop()
  const { t } = useLang()
  const screenHeader = isValidElement(header)
    ? cloneElement(header, { className: ['cc-business-header', header.props.className].filter(Boolean).join(' ') })
    : header
  const previewNote = PREVIEW && <div className="cc-preview-note" role="status">{t.bn_preview}</div>
  // Keep the content subtree mounted across responsive breakpoints. Moving an
  // unsaved review into a different layout tree would discard the employer draft.
  return (
    <div className={`cc-business-workspace${isDesktop ? '' : ' cc-business-mobile'}`} style={isDesktop ? { minHeight: '100svh', background: '#F4F1EA' } : undefined}>
      {isDesktop ? <Sidebar /> : <div style={{ padding: '14px 20px 0', fontFamily: SERIF, fontSize: 25, fontWeight: 500 }}><CookCreditBrand /></div>}
      <main key="workspace-content" className={isDesktop ? 'cc-business-main' : undefined} style={isDesktop ? { marginLeft: 248, minWidth: 0, background: '#FEFDFB', minHeight: '100svh' } : undefined}>
        <div style={isDesktop ? { maxWidth: 1280, margin: '0 auto' } : undefined}>
          {isDesktop ? screenHeader : <header>{screenHeader}<MobileNav /><OwnerAccessLink /></header>}
          {previewNote}
          <div>{children}</div>
        </div>
      </main>
      {!isDesktop && <HiringBottomNav />}
    </div>
  )
}
