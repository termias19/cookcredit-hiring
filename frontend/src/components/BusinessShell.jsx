/**
 * BusinessShell — two purpose-built layouts for the B2B workspace, same screens + data.
 *   Desktop (>=900px): a WEBSITE layout — fixed left sidebar nav + a wide content column.
 *   Mobile: the same light workspace with a horizontal navigation row.
 * Screens render their own `header`; on desktop it sits atop the content column, the sidebar owns
 * primary nav. `showNav` is accepted (for drop-in parity with Shell) but ignored.
 */
import { cloneElement, createElement, isValidElement } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { ChefHat, BriefcaseBusiness, Settings, Plus } from 'lucide-react'
import useIsDesktop from '../hooks/useIsDesktop'
import { PREVIEW } from '../config'
import { useBusiness } from '../context/BusinessContext'
import { useLang } from '../context/LangContext'
import CookCreditBrand from './CookCreditBrand'
import HiringBottomNav from './HiringBottomNav'


const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C'

const NAV = [
  { to: '/business/roles', label: 'bn_roles', base: '/business/role', icon: BriefcaseBusiness },
  { to: '/business/candidates', label: 'bn_applicants', base: '/business/candidate', icon: ChefHat },
  { to: '/business/profile', label: 'bn_settings', icon: Settings },
]

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

      <div style={{ flex: 1 }} />
      <div style={{ padding: '0 8px' }}>
        <div style={{ fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#70706b' }}>{t.bn_plan}</div>
        <div style={{ fontSize: 13, color: '#1a1a1a', textTransform: 'capitalize', marginTop: 2 }}>{biz?.org?.integrationAccess?.earlyAccess ? t.bn_included : biz?.org?.plan || '—'}</div>
      </div>
    </aside>
  )
}

export default function BusinessShell({ header, children, embedded = false }) {
  const biz = useBusiness()
  const isDesktop = useIsDesktop()
  const { t } = useLang()
  const screenHeader = isValidElement(header)
    ? cloneElement(header, { className: ['cc-business-header', header.props.className].filter(Boolean).join(' ') })
    : header
  const previewNote = PREVIEW && <div className="cc-preview-note" role="status">{t.bn_preview}</div>
  if (embedded) return <section>{header}{children}</section>
  // Keep the content subtree mounted across responsive breakpoints. Moving an
  // unsaved review into a different layout tree would discard the employer draft.
  return (
    <div className={`cc-business-workspace${isDesktop ? '' : ' cc-business-mobile'}`} style={isDesktop ? { minHeight: '100svh', background: '#F4F1EA' } : undefined}>
      {isDesktop ? <Sidebar /> : <div style={{ padding: '14px 20px 0', fontFamily: SERIF, fontSize: 25, fontWeight: 500 }}><CookCreditBrand /></div>}
      <main key="workspace-content" className={isDesktop ? 'cc-business-main' : undefined} style={isDesktop ? { marginLeft: 248, minWidth: 0, background: '#FEFDFB', minHeight: '100svh' } : undefined}>
        <div style={isDesktop ? { maxWidth: 1280, margin: '0 auto' } : undefined}>
          {isDesktop ? screenHeader : <header>{screenHeader}</header>}
          {previewNote}
          {biz?.actionError && <p role="alert" style={{ margin: '12px 28px', color: '#A44320' }}>{biz.actionError}</p>}
          <div>{children}</div>
        </div>
      </main>
      {!isDesktop && <HiringBottomNav />}
    </div>
  )
}
