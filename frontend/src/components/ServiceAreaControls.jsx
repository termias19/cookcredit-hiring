import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import { updateCookServiceArea } from '../utils/Api'
import { PREVIEW } from '../config'

export default function ServiceAreaControls() {
  const { user } = useAuth()
  const { t } = useLang()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState(false)
  async function save(remove = false) {
    if (busy) return
    setMessage(''); setError(false)
    if (PREVIEW) { setError(true); setMessage(t.loc_preview); return }
    setBusy(true)
    try {
      let location = null
      if (!remove) {
        if (!navigator.geolocation) throw new Error('Location unavailable')
        const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject,
          { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }))
        location = { lat: position.coords.latitude, lng: position.coords.longitude }
      }
      await updateCookServiceArea({ token: await user.getIdToken(), location })
      setMessage(remove ? t.loc_service_removed : t.loc_service_saved)
    } catch (e) { setError(true); setMessage(e.code === 1 ? t.loc_permission : t.loc_unavailable) }
    finally { setBusy(false) }
  }
  const style = { padding: '11px 14px', border: '1px solid #1f6f5c', background: 'none', color: '#1f6f5c', cursor: 'pointer', fontSize: 13 }
  return <div style={{ borderTop: '1px solid #e3e0d9', marginTop: 20, paddingTop: 18 }}>
    <p style={{ fontSize: 13, color: '#636960', lineHeight: 1.7, marginBottom: 12 }}>{t.loc_service_hint}</p>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
      <button type="button" style={style} disabled={busy} onClick={() => save()}>{busy ? t.loc_busy : t.loc_service}</button>
      <button type="button" style={style} disabled={busy} onClick={() => save(true)}>{t.loc_service_remove}</button>
    </div>
    {message && <p role={error ? 'alert' : 'status'} style={{ color: error ? '#a52b2b' : '#1f6f5c', fontSize: 13, marginTop: 12 }}>{message}</p>}
  </div>
}
