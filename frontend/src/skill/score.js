// score.js -- on-device skill estimate for the live badge AND the result screen.
//
// IMPORTANT: this is an instant, on-device estimate for feedback. The canonical
// record is the server-side scorer (services/skill_scoring.py) on the uploaded
// trajectory. We only estimate what we can honestly measure from the wrist signal:
//   - Smoothness  = stroke-interval steadiness (rhythm)
//   - Consistency = stroke-depth steadiness (amplitude)
//   - Finesse     = chop-likeness (vertical, clean motion)
// Axes without enough data are dropped from the overall rather than guessed.
// Ported from the CookCredit engine's web/score.js.

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function median(a) {
  const s = [...a].sort((x, y) => x - y);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// Robust steadiness 0..100 from intervals/amplitudes. median + MAD (not mean/std)
// so a pause-to-reposition or one short hop doesn't tank an otherwise steady run.
function cvScore(values, k) {
  if (values.length < 3) return null;
  const m = median(values);
  if (m <= 0) return null;
  const mad = 1.4826 * median(values.map(v => Math.abs(v - m)));
  const rcv = mad / m;                       // robust coefficient of variation
  return clamp(100 * Math.exp(-k * rcv), 0, 100);
}

/**
 * Full breakdown from the running stroke series. Returns null axes when there
 * isn't enough data (so the UI can drop them rather than show a guessed number).
 *
 * @returns {{overall:number|null, smoothness:number|null, consistency:number|null,
 *            finesse:number|null, strokes:number}}
 */
export function scoreBreakdown(strokeTimes = [], strokeAmps = [], pctChop = 0) {
  let smoothness = null;
  if (strokeTimes.length >= 3) {
    const iv = [];
    for (let i = 1; i < strokeTimes.length; i++) iv.push(strokeTimes[i] - strokeTimes[i - 1]);
    smoothness = cvScore(iv, 1.0);                 // tempo steadiness
  }
  const consistency = cvScore(strokeAmps, 1.1);    // depth evenness
  const finesse = pctChop > 0 ? clamp(pctChop, 0, 100) : null;  // clean vertical chop

  const axes = [
    { v: smoothness,  w: 0.45 },
    { v: consistency, w: 0.30 },
    { v: finesse,     w: 0.25 },
  ].filter(a => a.v != null);

  let overall = null;
  if (axes.length && strokeTimes.length >= 3) {
    const wsum = axes.reduce((s, a) => s + a.w, 0);
    overall = Math.round(axes.reduce((s, a) => s + a.v * a.w, 0) / wsum);
  }
  return {
    overall,
    smoothness:  smoothness  == null ? null : Math.round(smoothness),
    consistency: consistency == null ? null : Math.round(consistency),
    finesse:     finesse     == null ? null : Math.round(finesse),
    strokes: strokeTimes.length,
  };
}

// Live badge wants just the single number.
export function liveSkillPct(strokeTimes = [], strokeAmps = [], pctChop = 0) {
  return scoreBreakdown(strokeTimes, strokeAmps, pctChop).overall;
}
