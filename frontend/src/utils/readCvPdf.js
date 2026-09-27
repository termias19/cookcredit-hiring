import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
GlobalWorkerOptions.workerSrc = workerUrl

export async function readCvPdf(blob, { signal } = {}) {
  if (blob.size > 2 * 1024 * 1024) throw new Error('This CV is too large to read here. Download the original PDF.')
  if (signal?.aborted) throw new DOMException('Closed', 'AbortError')
  const data = new Uint8Array(await blob.arrayBuffer())
  if (signal?.aborted) throw new DOMException('Closed', 'AbortError')
  const task = getDocument({ data, isEvalSupported: false, disableFontFace: true,
    useSystemFonts: false, useWorkerFetch: false, useWasm: false, stopAtErrors: true })
  let timer, abort
  const interrupted = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Reading took too long. Download the original PDF.')), 20000)
    abort = () => reject(new DOMException('Closed', 'AbortError'))
    signal?.addEventListener('abort', abort, { once: true })
  })
  try {
    return await Promise.race([interrupted, (async () => {
      const pdf = await task.promise
      if (pdf.numPages > 30) throw new Error('This CV has more than 30 pages. Download the original PDF.')
      const pages = []
      let characters = 0
      for (let number = 1; number <= pdf.numPages; number++) {
        const page = await pdf.getPage(number)
        try {
          const content = await page.getTextContent()
          const text = content.items.map(item => typeof item.str === 'string' ? item.str + (item.hasEOL ? '\n' : ' ') : '').join('').trim()
          characters += text.length
          if (characters > 100000) throw new Error('This CV contains too much text. Download the original PDF.')
          pages.push({ number, text })
        } finally { page.cleanup() }
      }
      if (!pages.some(page => page.text)) throw new Error('No selectable text was found. This may be a scanned CV. Download the original PDF to read it.')
      return pages
    })()])
  } catch (error) {
    if (error.name === 'PasswordException') throw new Error('This PDF is password protected. Download the original to open it.')
    if (['InvalidPDFException', 'UnknownErrorException'].includes(error.name)) throw new Error('This PDF could not be read here. Download the original PDF.')
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
    await task.destroy()
  }
}
