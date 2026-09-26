import { useState } from 'react'
import { Check, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import LanguageSelect from './LanguageSelect'
import { PREVIEW } from '../config'

const panel = { border: '1px solid var(--cc-border)', padding: 24, background: 'var(--cc-surface)' }
const input = { width: '100%', padding: '12px 14px', border: '1px solid var(--cc-border)', background: '#fff', fontSize: 14, color: 'var(--cc-ink)' }
const label = { display: 'grid', gap: 8, fontSize: 13, color: 'var(--cc-muted)' }
const button = { padding: '12px 20px', background: '#1F6F5C', color: '#fff', border: 0, cursor: 'pointer', fontSize: 14 }

/** Personal settings shared by applicants and company members. No role grant. */
export default function AccountDetails({ profile, children }) {
  const { user, updateProfile, resetPassword, logout } = useAuth()
  const { t } = useLang()
  const navigate = useNavigate()
  const [name, setName] = useState(profile.name || '')
  const [phone, setPhone] = useState(profile.phone || '')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  async function run(kind, action, message) {
    if (busy) return
    setBusy(kind); setError(''); setNotice('')
    try { await action(); setNotice(message) }
    catch (e) { setError(e.message || t.bp_save_error) }
    finally { setBusy('') }
  }
  return <>
    {notice && <p role="status" style={{ marginBottom: 20, color: '#1F6F5C' }}>{notice}</p>}
    {error && <p role="alert" style={{ marginBottom: 20, color: '#a52b2b' }}>{error}</p>}
    <div className="cc-plan-grid" style={{ alignItems: 'start' }}>
      <form style={panel} onSubmit={e => { e.preventDefault(); if (name.trim()) run('personal', () => updateProfile({ name: name.trim(), phone: phone.trim() }), PREVIEW ? t.bp_preview_saved : t.bp_saved) }}>
        <h2 className="cc-profile-heading">{t.bp_personal}</h2>
        <div style={{ display: 'grid', gap: 18 }}>
          <label style={label}>{t.bp_name}<input style={input} autoComplete="name" required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label>
          <label style={label}>{t.bp_phone} · {t.bp_optional}<input style={input} type="tel" autoComplete="tel" maxLength={40} value={phone} onChange={e => setPhone(e.target.value)} /></label>
          <label style={label}>{t.bp_email}<input style={{ ...input, background: '#f6f6f2' }} readOnly type="email" value={profile.email || user?.email || ''} /></label>
          {user?.emailVerified && <span style={{ color: '#1F6F5C', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}><Check size={14} /> {t.bp_verified}</span>}
          <button style={button} disabled={!!busy || !name.trim()}>{busy === 'personal' ? t.bp_saving : t.bp_save_personal}</button>
        </div>
      </form>
      {children}
      <section style={panel}>
        <h2 className="cc-profile-heading">{t.bp_language}</h2>
        <p style={{ marginBottom: 18, fontSize: 13, color: 'var(--cc-muted)', lineHeight: 1.7 }}>{t.bp_language_hint}</p>
        <LanguageSelect variant="toggle" />
      </section>
      <section style={panel}>
        <h2 className="cc-profile-heading">{t.bp_security}</h2>
        <p style={{ marginBottom: 18, fontSize: 13, color: 'var(--cc-muted)', lineHeight: 1.7 }}>{t.bp_reset_hint}</p>
        <button type="button" disabled={!!busy} style={{ ...button, background: 'transparent', color: '#1F6F5C', border: '1px solid #1F6F5C' }} onClick={() => run('reset', () => resetPassword(profile.email || user.email), t.bp_reset_sent)}>{busy === 'reset' ? t.bp_requesting : t.bp_reset}</button>
      </section>
    </div>
    <button disabled={!!busy} type="button" onClick={() => run('logout', async () => { await logout(); navigate('/login', { replace: true }) }, '')} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 28, background: 'none', border: 0, color: 'var(--cc-muted)', cursor: 'pointer', padding: '12px 0' }}><LogOut size={16} /> {t.bp_signout}</button>
  </>
}
