import { useEffect, useState } from 'react'
import { useLang } from '../context/LangContext'
import { watchForAppUpdate } from '../utils/serviceWorkerUpdate'

export default function AppUpdateNotice() {
  const { lang } = useLang()
  const [applyUpdate, setApplyUpdate] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => watchForAppUpdate({
    serviceWorker: navigator.serviceWorker,
    onReady: apply => { setApplyUpdate(() => apply); setBusy(false) },
    onUnavailable: () => { setBusy(false); setFailed(true) },
    reload: () => window.location.reload(),
  }), [])

  if (!applyUpdate) return null
  const es = lang === 'ES'
  return (
    <aside aria-label={es ? 'Actualización de CookCredit' : 'CookCredit update'} aria-live="polite"
      style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: 12,
        padding: '12px 20px', background: '#FEFDFB', color: '#1a1a1a', borderBottom: '1px solid #e5e5e5', fontSize: 13, lineHeight: 1.5 }}>
      <span>{failed
        ? (es ? 'No se pudo actualizar. Comprueba tu conexión e inténtalo de nuevo.' : 'The update could not finish. Check your connection and try again.')
        : (es ? 'Hay una nueva versión. Guarda tu trabajo antes de actualizar.' : 'A new version is available. Save your work before updating.')}</span>
      <button disabled={busy} onClick={() => { setBusy(true); setFailed(false); applyUpdate() }}
        style={{ padding: '8px 14px', border: 0, background: '#1F6F5C', color: '#fff', cursor: busy ? 'wait' : 'pointer' }}>
        {busy ? (es ? 'Actualizando…' : 'Updating…') : (es ? 'Actualizar' : 'Update')}
      </button>
      <button disabled={busy} onClick={() => setApplyUpdate(null)}
        style={{ padding: '8px 12px', border: '1px solid #e5e5e5', background: 'transparent', color: '#555', cursor: 'pointer' }}>
        {es ? 'Más tarde' : 'Later'}
      </button>
    </aside>
  )
}
