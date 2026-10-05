import { lazy, Suspense } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import BusinessShell from '../components/BusinessShell'
import { useLang } from '../context/LangContext'
const Applicants = lazy(() => import('./BusinessDashboardScreen'))
const Saved = lazy(() => import('./BusinessShortlistsScreen'))
export default function BusinessApplicantsScreen() {
  const [params] = useSearchParams(), { t } = useLang()
  const saved = params.get('view') === 'saved'
  return <BusinessShell header={<div style={{ padding: '24px 28px 16px' }}>
    <h1 style={{ fontFamily: 'var(--cc-display)', fontSize: 36, fontWeight: 500 }}>{t.bn_applicants}</h1>
    <nav aria-label="Applicant views" className="cc-workspace-sections">
      <Link to="/business/candidates" aria-current={!saved ? 'page' : undefined}>{t.bn_assessments}</Link>
      <Link to="/business/candidates?view=saved" aria-current={saved ? 'page' : undefined}>{t.bn_shortlist}</Link>
    </nav>
    <p style={{ marginTop: 12, fontSize: 13, color: 'var(--cc-muted)' }}>Shared assessments appear here. Open a role to see all its applications, including those still in progress.</p>
  </div>}><Suspense fallback={<p role="status" style={{ padding: 28 }}>Loading applicants…</p>}>{saved ? <Saved embedded /> : <Applicants embedded />}</Suspense></BusinessShell>
}
