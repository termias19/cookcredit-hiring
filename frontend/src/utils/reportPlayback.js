// Never attach a recording to a report for a different attempt.
export async function reportPlayback({ token, cookId, roleId, attemptId, request }) {
  if (!token || !attemptId) throw new Error('Load the assessment report before playback.')
  const result = await request({ token, cookId, roleId, attemptId })
  if (result?.attemptId !== attemptId) throw new Error('Recording does not match this report.')
  return result.videoUrl || null
}
