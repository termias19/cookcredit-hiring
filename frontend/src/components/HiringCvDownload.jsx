import { useState } from 'react'
import { downloadHiringCv } from '../utils/Api'

export default function HiringCvDownload({ applicationId, getToken }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function download() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const blob = await downloadHiringCv({ token: await getToken(), applicationId })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = 'candidate-cv.pdf'
      document.body.appendChild(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError(e.message || 'CV download failed. Please try again.') }
    finally { setBusy(false) }
  }
  return <div><button type="button" disabled={busy} onClick={download} style={{ border: '1px solid #dedbd4', background: '#fff', padding: '8px 12px', color: '#1F6F5C', cursor: 'pointer' }}>{busy ? 'Downloading…' : 'Download CV'}</button>{error && <p role="alert" style={{ color: '#A44320', fontSize: 12 }}>{error}</p>}</div>
}
