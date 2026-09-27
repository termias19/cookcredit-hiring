/** Keep a confirmed file write distinct from a browser download request. */
export async function saveHiringCv(loadBlob, browser = window, doc = document, urls = URL) {
  // Invoke the picker before awaiting authentication so the click retains activation.
  let handle
  if (typeof browser.showSaveFilePicker === 'function') {
    try {
      handle = await browser.showSaveFilePicker({
        suggestedName: 'candidate-cv.pdf',
        types: [{ description: 'PDF document', accept: { 'application/pdf': ['.pdf'] } }],
      })
    } catch (error) {
      if (error.name === 'AbortError') return 'cancelled'
      // Embedded browsers may prohibit the picker. Use their standard download path.
      if (!['SecurityError', 'NotAllowedError'].includes(error.name)) throw error
    }
  }
  const blob = await loadBlob()
  if (handle) {
    const writable = await handle.createWritable()
    try {
      await writable.write(blob)
      await writable.close()
    } catch (error) {
      try { await writable.abort() } catch { /* Keep the original write failure. */ }
      throw error
    }
    return 'saved'
  }
  const url = urls.createObjectURL(blob)
  const link = doc.createElement('a')
  link.href = url
  link.download = 'candidate-cv.pdf'
  try {
    doc.body.appendChild(link)
    link.click()
  } finally {
    link.remove()
    // Give browsers time to consume the blob before releasing its memory.
    browser.setTimeout(() => urls.revokeObjectURL(url), 60000)
  }
  return 'requested'
}
