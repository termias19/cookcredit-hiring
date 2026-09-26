export function validateOriginalLandmarks(data) {
  if (![1, 2].includes(data?.version) || data.timebase !== 'recording-ms' || data.mirrored !== false || !Array.isArray(data.frames) || !data.frames.length || data.frames.length > 1900) throw new Error('Invalid original landmark data')
  if (data.version === 2 && !/^[a-f0-9]{64}$/.test(data.renderer)) throw new Error('Invalid renderer identity')
  let last = -1
  for (const row of data.frames) {
    if (!Array.isArray(row) || row.length !== (data.version === 2 ? 4 : 3) || !Number.isInteger(row[0]) || row[0] <= last || row[0] > 120000) throw new Error('Invalid landmark time')
    if (data.version === 2) {
      const v = row[3], keys = ['width','height','bladeExtendK','knifePresent','knifeConf','knifeWorker','bladeTrail']
      if (!v || Object.keys(v).length !== keys.length || keys.some(k => !(k in v))) throw new Error('Invalid engine overlay')
      if (['width','height'].some(k => !Number.isInteger(v[k]) || v[k] < 1 || v[k] > 8192)) throw new Error('Invalid dimensions')
      if (!Number.isFinite(v.bladeExtendK) || v.bladeExtendK < .1 || v.bladeExtendK > 20 || !Number.isFinite(v.knifeConf) || v.knifeConf < 0 || v.knifeConf > 1 || typeof v.knifePresent !== 'boolean' || typeof v.knifeWorker !== 'boolean') throw new Error('Invalid knife state')
      if (!Array.isArray(v.bladeTrail) || v.bladeTrail.length > 48 || v.bladeTrail.some(p => !Array.isArray(p) || p.length !== 2 || p.some(n => !Number.isFinite(n) || Math.abs(n) > 163840))) throw new Error('Invalid trail')
    }
    last = row[0]
    for (const hand of row.slice(1,3)) if (hand !== null && (!Array.isArray(hand) || hand.length !== 21 || hand.some(p => !Array.isArray(p) || p.length !== 2 || p.some(n => !Number.isFinite(n) || n < -1 || n > 2)))) throw new Error('Invalid landmark positions')
  }
  return data.frames
}
export function landmarkFrameAt(frames, seconds) {
  const t = seconds * 1000
  let lo = 0, hi = frames.length - 1, found = -1
  while (lo <= hi) { const mid = (lo + hi) >>> 1; if (frames[mid][0] <= t) { found = mid; lo = mid + 1 } else hi = mid - 1 }
  return found >= 0 && t - frames[found][0] <= 200 ? frames[found] : null
}

