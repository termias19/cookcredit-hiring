// Never attach a recording to a report for a different attempt.
export async function reportPlayback({ token, cookId, roleId, attemptId, request, signal }) {
  if (!token || !attemptId) throw new Error('Load the assessment report before playback.')
  const result = await request({ token, cookId, roleId, attemptId, ...(signal ? { signal } : {}) })
  if (result?.attemptId !== attemptId) throw new Error('Recording does not match this report.')
  return result.videoUrl || null
}

export function recordingLabel(recording) {
  return ({ready:'Recording ready', expired:'Recording expired', unavailable:'Recording unavailable'})[recording?.state] || 'Check recording'
}

export function playbackFailure(error) {
  const code = error?.code
  const terminal = ['recording_expired', 'recording_missing'].includes(code)
  const message = code === 'recording_expired'
    ? 'This recording has expired under the 30-day Hiring retention policy. The application and assessment history remain available.'
    : code === 'recording_missing'
      ? 'This recording is no longer available. The application and assessment history remain available.'
      : 'The recording could not be loaded. Please retry.'
  const reference = /^[a-f0-9]{32}$/.test(error?.requestId || '') ? error.requestId : ''
  return {terminal, message: reference ? `${message} Reference: ${reference}` : message}
}
