import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useAuth } from '../context/AuthContext'
import { useBusiness } from '../context/BusinessContext'
import { updateBusinessOrg } from '../utils/Api'
import { useLang } from '../context/LangContext'
import AccountDetails from '../components/AccountDetails'
import LocationFinder from '../components/LocationFinder'

const panel = { border: '1px solid var(--cc-border)', padding: 24, background: 'var(--cc-surface)' }
const input = { width: '100%', padding: '12px 14px', border: '1px solid var(--cc-border)', background: '#fff', fontSize: 14, color: 'var(--cc-ink)' }
const label = { display: 'grid', gap: 8, fontSize: 13, color: 'var(--cc-muted)' }
const button = { padding: '12px 20px', background: '#1F6F5C', color: '#fff', border: 0, cursor: 'pointer', fontSize: 14 }

function Details({ profile, org }) {
  const { t } = useLang()
  const { getToken, refresh } = useBusiness()
  const [company, setCompany] = useState(org.name || '')
  const [city, setCity] = useState(org.city || '')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const admin = org.seatRole === 'admin'
  async function run(kind, action, message) {
    if (busy) return
    setBusy(kind); setError(''); setNotice('')
    try { await action(); setNotice(message) }
    catch (e) { setError(e.message || t.bp_save_error) }
    finally { setBusy('') }
  }
  return <div style={{ padding: '0 28px 40px', maxWidth: 1000 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, borderTop: '1px solid var(--cc-border)', padding: '24px 0' }}>
      <div aria-hidden="true" style={{ width: 56, height: 56, display: 'grid', placeItems: 'center', background: '#EDF3EF', color: '#1F6F5C', fontFamily: 'var(--cc-display)', fontSize: 28 }}>{(profile.name || 'C').slice(0, 1)}</div>
      <div><h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 27, fontWeight: 400 }}>{profile.name}</h2><p style={{ fontSize: 13, marginTop: 4, color: 'var(--cc-muted)' }}>{org.name} · {(org.seatRole || 'member').replaceAll('_', ' ')}</p></div>
    </div>
    {notice && <p role="status" style={{ marginBottom: 20, color: '#1F6F5C' }}>{notice}</p>}
    {error && <p role="alert" style={{ marginBottom: 20, color: '#a52b2b' }}>{error}</p>}
    <AccountDetails profile={profile}>
      <form style={panel} onSubmit={e => { e.preventDefault(); run('company', async () => { await updateBusinessOrg({ token: await getToken(), updates: { name: company.trim(), city: city.trim() } }); refresh() }, t.bp_company_saved) }}>
        <h2 className="cc-profile-heading">{t.bp_company}</h2>
        <div style={{ display: 'grid', gap: 18 }}>
          <label style={label}>{t.bp_company_name}<input style={input} autoComplete="organization" required maxLength={200} disabled={!admin} value={company} onChange={e => setCompany(e.target.value)} /></label>
          <label style={label}>{t.bp_city}<input style={input} autoComplete="address-level2" required maxLength={120} disabled={!admin} value={city} onChange={e => setCity(e.target.value)} /></label>
          <p style={{ fontSize: 13, color: 'var(--cc-muted)', lineHeight: 1.7 }}>{t.bp_company_hint} <Link style={{ color: '#1F6F5C' }} to="/business/profile?section=integrations">{t.bn_integrations}</Link>.</p>
          {admin ? <button style={button} disabled={!!busy}>{busy === 'company' ? t.bp_saving : t.bp_save_company}</button> : <p style={{ fontSize: 13 }}>{t.bp_admin_only}</p>}
        </div>
      </form>
      <section style={panel}>
        <h2 className="cc-profile-heading">{t.bp_subscription}</h2>
        <p style={{ fontSize: 15, textTransform: 'capitalize' }}>{org.integrationAccess?.earlyAccess ? t.bn_included : org.plan || '—'} · {t.bn_plan}</p>
        <p style={{ margin: '12px 0 20px', fontSize: 13, color: 'var(--cc-muted)', lineHeight: 1.7 }}>{org.integrationAccess?.earlyAccess ? t.bp_included_hint : t.bp_billing_hint}</p>
        <Link className="cc-profile-link" to="/business/profile?section=billing">{t.bn_billing}<ArrowRight size={16} /></Link>
      </section>
      <LocationFinder />
    </AccountDetails>
  </div>
}

export default function BusinessProfileScreen({ embedded = false } = {}) {
  const { t } = useLang()
  const { profile } = useAuth()
  const { org, loading, error, refresh } = useBusiness()
  return <BusinessShell embedded={embedded} header={embedded ? null : <div style={{ padding: '28px 28px 24px' }}><p style={{ fontSize: 11, letterSpacing: 2, color: '#1F6F5C', textTransform: 'uppercase' }}>{t.bp_account}</p><h1 style={{ fontFamily: 'var(--cc-display)', fontWeight: 400, fontSize: 38, marginTop: 6 }}>{t.bp_profile}</h1><p style={{ marginTop: 8, color: 'var(--cc-muted)', fontSize: 14 }}>{t.bp_intro}</p></div>}>
    {loading ? <p role="status" style={{ padding: 28 }}>{t.bp_loading}</p> : error || !org || !profile ? <div style={{ padding: 28 }}><p role="alert">{t.bp_load_error}</p><button onClick={refresh}>{t.bp_retry}</button></div> : <Details key={org.id} profile={profile} org={org} />}
  </BusinessShell>
}
