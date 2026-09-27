import { useEffect, useRef, useState } from 'react'
import { downloadHiringCv } from '../utils/Api'
import { saveHiringCv } from '../utils/saveHiringCv'

export default function HiringCvDownload(props) {
  return <HiringCvControls key={props.applicationId} {...props} />
}

function HiringCvControls({ applicationId, getToken }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [reader, setReader] = useState(null)
  const readController = useRef(null)
  useEffect(() => () => readController.current?.abort(), [applicationId])
  function closeReader() {
    readController.current?.abort(); readController.current = null; setReader(null)
  }
  async function read() {
    if (readController.current) return
    const controller = new AbortController()
    readController.current = controller
    setReader({ loading: true })
    try {
      const [{ readCvPdf }, blob] = await Promise.all([
        import('../utils/readCvPdf'),
        downloadHiringCv({ token: await getToken(), applicationId }),
      ])
      const pages = await readCvPdf(blob, { signal: controller.signal })
      if (!controller.signal.aborted) setReader({ pages })
    } catch (error) {
      if (!controller.signal.aborted) setReader({ error: error.message || 'CV could not be read. Download the original PDF.' })
    }
  }
  async function download() {
    if (busy) return
    setBusy(true); setError(''); setStatus('')
    try {
      const result = await saveHiringCv(async () => downloadHiringCv({ token: await getToken(), applicationId }))
      setStatus(result === 'saved' ? 'CV saved.' : result === 'cancelled' ? 'Save cancelled. You can try again.' : 'Download requested. Check your browser downloads. If no file appears, try again in Chrome, Edge, Firefox or Safari.')
    } catch (e) { setError(e.message || 'CV download failed. Please try again.') }
    finally { setBusy(false) }
  }
  return <div><button type="button" disabled={busy} onClick={download} style={{ border: '1px solid #dedbd4', background: '#fff', padding: '8px 12px', color: '#1F6F5C', cursor: 'pointer' }}>{busy ? 'Downloading…' : 'Download CV'}</button><button type="button" onClick={read} disabled={Boolean(reader)} style={{ border: '1px solid #dedbd4', background: '#fff', padding: '8px 12px', marginLeft: 8, color: '#1F6F5C', cursor: 'pointer' }}>Read CV</button>{reader && <section aria-label="CV text" style={{ marginTop: 12, padding: 14, border: '1px solid #dedbd4', maxHeight: 420, overflowY: 'auto' }}><button type="button" onClick={closeReader}>Close CV</button><p style={{ fontSize: 12 }}>Extracted text may omit formatting or change reading order. Use the original PDF to confirm details.</p>{reader.loading && <p role="status">Reading CV...</p>}{reader.error && <p role="alert">{reader.error}</p>}{reader.pages?.map(page => <div key={page.number}><strong>Page {page.number}</strong><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.6 }}>{page.text || 'No selectable text on this page.'}</p></div>)}</section>}{status && <p role="status" style={{ color: '#526057', fontSize: 12 }}>{status}</p>}{error && <p role="alert" style={{ color: '#A44320', fontSize: 12 }}>{error}</p>}</div>
}
