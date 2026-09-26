import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapPin, LocateFixed, ArrowRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import { resolveSearchLocation, getNearbyCooks } from '../utils/Api'
import { PREVIEW } from '../config'
import { money } from '../utils/money'

const field = { width: '100%', padding: '11px 12px', border: '1px solid #e3e0d9', fontSize: 14, background: '#fff', color: '#252923' }
const button = { padding: '11px 16px', border: '1px solid #1f6f5c', color: '#1f6f5c', background: 'transparent', fontSize: 14, cursor: 'pointer' }

export default function LocationFinder() {
  const { user, profile } = useAuth()
  const { t, lang } = useLang()
  const [zip, setZip] = useState(profile?.eaterProfile?.addressZip || '')
  const [area, setArea] = useState(null)
  const [radius, setRadius] = useState(25)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const requestId = useRef(0)

  function clearSearch() { requestId.current += 1; setArea(null); setResult(null); setError('') }
  async function locate(device = false) {
    if (busy) return
    if (!device && !/^\d{5}$/.test(zip)) { setError(t.loc_invalid); return }
    clearSearch()
    if (PREVIEW) { setError(t.loc_preview); return }
    const id = requestId.current
    setBusy(true)
    try {
      let location = { postalCode: zip, language: lang }
      if (device) {
        if (!navigator.geolocation) throw new Error('device_unavailable')
        const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject,
          { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }))
        location = { lat: position.coords.latitude, lng: position.coords.longitude,
          accuracyMeters: position.coords.accuracy, language: lang }
      }
      const data = await resolveSearchLocation({ token: await user.getIdToken(), location })
      if (id === requestId.current) setArea(data.location)
    } catch (e) {
      if (id === requestId.current) setError(e.code === 1 ? t.loc_permission : e.code === 3 ? t.loc_timeout
        : e.code === 2 || e.message === 'device_unavailable' ? t.loc_unavailable
          : e.code === 'area_not_found' ? t.loc_zero : t.loc_error)
    } finally { setBusy(false) }
  }
  async function search(page = 1) {
    if (!area || busy) return
    const id = requestId.current
    setBusy(true); setError('')
    try {
      const data = await getNearbyCooks({ token: await user.getIdToken(), locationToken: area.locationToken, radiusMiles: radius, page })
      if (id === requestId.current) setResult(previous => ({ ...data, cooks: page === 1 ? data.cooks : [...previous.cooks, ...data.cooks] }))
    } catch (e) { if (id === requestId.current) setError(e.code === 'invalid_location' ? t.loc_expired : t.loc_error) }
    finally { setBusy(false) }
  }
  return <section aria-labelledby="nearby-heading" style={{ border: '1px solid var(--cc-border)', padding: 24, gridColumn: '1 / -1' }}>
    <h2 id="nearby-heading" className="cc-profile-heading"><MapPin size={19} strokeWidth={1.5} style={{ marginRight: 8 }} />{t.loc_title}</h2>
    <p style={{ fontSize: 13, color: 'var(--cc-muted)', marginBottom: 20 }}>{t.loc_hint}</p>
    <div style={{ display: 'flex', alignItems: 'end', gap: 10, flexWrap: 'wrap' }}>
      <label style={{ display: 'grid', gap: 7, fontSize: 13, width: 170 }}>{t.loc_zip}
        <input style={field} value={zip} inputMode="numeric" autoComplete="postal-code" maxLength={5} placeholder="30303"
          onChange={e => { setZip(e.target.value.replace(/[^0-9]/g, '')); clearSearch() }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); locate() } }} />
      </label>
      <button type="button" style={button} disabled={busy} onClick={() => locate()}>{t.loc_lookup}</button>
      <button type="button" style={{ ...button, display: 'inline-flex', alignItems: 'center', gap: 7 }} disabled={busy} onClick={() => locate(true)}><LocateFixed size={16} />{t.loc_current}</button>
    </div>
    <p style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--cc-muted)', marginTop: 14, maxWidth: 660 }}>{t.loc_notice}</p>
    {busy && <p role="status" style={{ marginTop: 14 }}>{t.loc_busy}</p>}
    {error && <p role="alert" style={{ color: '#a52b2b', fontSize: 13, marginTop: 14 }}>{error}</p>}
    {area && <div style={{ marginTop: 20, borderTop: '1px solid var(--cc-border)', paddingTop: 18 }}>
      <p style={{ fontSize: 16 }}>{area.label} {area.postalCode}</p>
      <p style={{ fontSize: 12, color: 'var(--cc-muted)', marginTop: 4 }}>{area.source === 'zip' ? t.loc_approx : `${t.loc_device} · ${t.loc_accuracy}: ±${Math.ceil(area.accuracyMeters)} ${t.loc_meters}`}</p>
      <span translate="no" style={{ display: 'block', color: '#5e5e5e', fontFamily: 'Arial, sans-serif', fontSize: 12, fontWeight: 400, whiteSpace: 'nowrap', margin: '10px 0 18px' }}>Google Maps</span>
      <div style={{ display: 'flex', gap: 12, alignItems: 'end', flexWrap: 'wrap' }}>
        <label style={{ display: 'grid', gap: 7, fontSize: 13 }}>{t.loc_radius}<select style={field} value={radius} disabled={busy} onChange={e => { setRadius(Number(e.target.value)); setResult(null) }}>
          {[5, 10, 25, 50, 100].map(value => <option key={value} value={value}>{value} {t.loc_miles}</option>)}
        </select></label>
        <button type="button" disabled={busy} style={{ ...button, background: '#1f6f5c', color: '#fff' }} onClick={() => search()}>{t.loc_find}</button>
      </div>
    </div>}
    {result && <div style={{ marginTop: 24 }}>
      <h3 style={{ fontFamily: 'var(--cc-display)', fontSize: 25, fontWeight: 400 }}>{result.cooks.length ? t.loc_results : t.loc_none}</h3>
      <p style={{ fontSize: 12, color: 'var(--cc-muted)', lineHeight: 1.7, margin: '8px 0 16px' }}>{result.cooks.length ? t.loc_results_hint : t.loc_empty_hint}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(230px, 100%), 1fr))', gap: 14 }}>
        {result.cooks.map(cook => <Link key={cook.id} to={`/cook/${encodeURIComponent(cook.id)}`} style={{ border: '1px solid var(--cc-border)', padding: 18, color: 'var(--cc-ink)', textDecoration: 'none' }}>
          <h4 style={{ fontFamily: 'var(--cc-display)', fontSize: 24, fontWeight: 400 }}>{cook.name}</h4>
          <p style={{ fontSize: 13, color: 'var(--cc-muted)' }}>{[cook.baseCity, cook.baseState].filter(Boolean).join(', ')}</p>
          <p style={{ fontSize: 13, marginTop: 12 }}>{t.loc_distance}: {cook.distanceMiles < 1 ? '<1' : cook.distanceMiles} {t.loc_miles}</p>
          <p style={{ fontSize: 12, color: '#1f6f5c', marginTop: 5 }}>{t.loc_verified}{cook.skillScore != null ? ` · ${cook.skillScore}/100` : ''}</p>
          {cook.pricePerHour != null && <p style={{ marginTop: 12 }}>{money(cook.pricePerHour)} {t.loc_hour} <ArrowRight size={14} /></p>}
        </Link>)}
      </div>
      {result.hasMore && <button type="button" style={{ ...button, marginTop: 18 }} disabled={busy} onClick={() => search(result.page + 1)}>{t.loc_load_more}</button>}
    </div>}
  </section>
}
