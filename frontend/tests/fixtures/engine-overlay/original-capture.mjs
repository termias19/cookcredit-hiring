// Record existing screen-space hand positions only; no inference or scoring.
export function createLandmarkCapture() {
  let origin = null, frames = [], last = -1, overflow = false;
  return {
    start(mediaTime) { origin = mediaTime; frames = []; last = -1; overflow = false; },
    add(mediaTime, knife, other) {
      const t = Math.round((mediaTime - origin) * 1000);
      if (origin === null || !Number.isFinite(t) || t < 0 || t <= last || (last >= 0 && t - last < 66)) return;
      if (t > 120000 || frames.length >= 1900) { overflow = true; return; }
      const points = hand => hand?.length === 21
        ? hand.map(p => [Math.round(p.x * 10000) / 10000, Math.round(p.y * 10000) / 10000]) : null;
      frames.push([t, points(knife), points(other)]); last = t;
    },
    finish() {
      return origin !== null && !overflow && frames.length
        ? { version: 1, timebase: 'recording-ms', mirrored: false, frames } : null;
    },
  };
}
