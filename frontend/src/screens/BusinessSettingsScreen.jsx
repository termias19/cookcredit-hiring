import { lazy, Suspense } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import BusinessShell from '../components/BusinessShell'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
const Company = lazy(() => import('./BusinessProfileScreen'))
const Team = lazy(() => import('./BusinessTeamScreen'))
const Integrations = lazy(() => import('./BusinessIntegrationsScreen'))
const Billing = lazy(() => import('./BusinessBillingScreen'))
const Activity = lazy(() => import('./BusinessActivityScreen'))
const sections = { company: Company, team: Team, integrations: Integrations, billing: Billing, activity: Activity }
export default function BusinessSettingsScreen() {
  const [params] = useSearchParams()
  const { profile } = useAuth(), { t } = useLang()
  const section = Object.hasOwn(sections, params.get('section')) ? params.get('section') : 'company'
  const Content = sections[section]
  return <BusinessShell header={<div style={{ padding: '24px 28px 16px' }}>
    <h1 style={{ fontFamily: 'var(--cc-display)', fontSize: 36, fontWeight: 500 }}>{t.bn_settings}</h1>
    <nav aria-label="Workspace settings" className="cc-workspace-sections">
      {[['company', t.bp_profile], ['team', t.bn_team], ['integrations', t.bn_integrations], ['billing', t.bn_billing], ['activity', 'Activity log']].map(([key, label]) => <Link key={key} to={`/business/profile?section=${key}`} aria-current={section === key ? 'page' : undefined}>{label}</Link>)}
    </nav>
    {profile?.isAccessOwner && <Link to="/owner/access" style={{ display: 'inline-block', marginTop: 14, color: 'var(--cc-forest)', fontSize: 13 }}>Manage hiring access</Link>}
  </div>}><Suspense fallback={<p role="status" style={{ padding: 28 }}>Loading settings…</p>}><Content embedded /></Suspense></BusinessShell>
}
