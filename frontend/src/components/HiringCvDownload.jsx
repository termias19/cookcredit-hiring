import { useState } from 'react'
import { downloadHiringCv } from '../utils/Api'
import { saveHiringCv } from '../utils/saveHiringCv'

export default function HiringCvDownload({ applicationId, getToken }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  async function download() {
    if (busy) return
    setBusy(true); setError(''); setStatus('')
    try {
      const result = await saveHiringCv(async () => downloadHiringCv({ token: await getToken(), applicationId }))
      setStatus(result === 'saved' ? 'CV saved.' : result === 'cancelled' ? 'Save cancelled. You can try again.' : 'Download requested. Check your browser downloads. If no file appears, try again in Chrome, Edge, Firefox or Safari.')
    } catch (e) { setError(e.message || 'CV download failed. Please try again.') }
    finally { setBusy(false) }
  }
  return <div><button type="button" disabled={busy} onClick={download} style={{ border: '1px solid #dedbd4', background: '#fff', padding: '8px 12px', color: '#1F6F5C', cursor: 'pointer' }}>{busy ? 'Downloading…' : 'Download CV'}</button>{status && <p role="status" style={{ color: '#526057', fontSize: 12 }}>{status}</p>}{error && <p role="alert" style={{ color: '#A44320', fontSize: 12 }}>{error}</p>}</div>
}
