// wrist.js -- direct JS port of the Python/C++ wrist analysis classes.
// Same math, same defaults. No external deps.

// ----------------------------------------------------------------------
// WristStrokeDetector
// 5-frame peak window with binomial smoothing on the center, strict
// local-max test on raw neighbors, rolling-baseline (default 30 frames)
// minimum for the amplitude check, debounce gap.
// ----------------------------------------------------------------------
export class WristStrokeDetector {
  constructor(opts = {}) {
    this.peakHalfWindow        = opts.peakHalfWindow        ?? 2;
    this.minAmplitudePx        = opts.minAmplitudePx        ?? 18.0;
    // Time-based debounce (fps-independent). The processed frame rate in the
    // browser is only ~10 fps, so the old frame-based gap (10 frames) was ~1 s
    // and capped the count at ~1 chop/sec -- too strict. 0.30 s allows up to
    // ~3 chops/sec (faster than typical chopping, slow enough to reject bobs).
    this.minGapSec             = opts.minGapSec             ?? 0.30;
    // Shorter baseline (~1.5 s) so amplitude is measured vs the RECENT low point,
    // not a stale 3-s-old minimum (which let a frozen hand's 1 px jitter look
    // like a big peak).
    this.rollingBaselineFrames = opts.rollingBaselineFrames ?? 15;
    // Recent-motion gate: a stroke only counts if the wrist is actually
    // oscillating now (std over the last ~0.9 s >= minMotionStdPx). This kills
    // false counts when there's no real wrist/knife motion.
    this.motionWin             = opts.motionWin             ?? 9;
    this.minMotionStdPx        = opts.minMotionStdPx        ?? 11.0;
    this.smooth                = opts.smooth                ?? true;
    this.reset();
  }

  reset() {
    this.history          = [];   // [{y, frameIdx, tSec}, ...]
    this.rolling          = [];   // [y, y, ...]
    this.recent           = [];   // last motionWin y's (for the motion gate)
    this.lastStrokeTSec   = -1e9;
    this.lastStrokeFrame  = -1e9;
    this.nStrokes         = 0;
  }

  /** Push one wrist y sample. Returns a stroke event or null. */
  update(y, frameIdx, tSec) {
    const win = 2 * this.peakHalfWindow + 1;
    this.history.push({y, frameIdx, tSec});
    if (this.history.length > win) this.history.shift();
    this.rolling.push(y);
    if (this.rolling.length > this.rollingBaselineFrames) this.rolling.shift();
    this.recent.push(y);
    if (this.recent.length > this.motionWin) this.recent.shift();
    if (this.history.length < win) return null;

    // RAW center for the strict local-max test. (Validated fix from
    // live_full.py / the C++ port: comparing raw neighbors against the
    // BINOMIAL-SMOOTHED center rejected ~all fast peaks, because smoothing
    // pulls the peak below its raw neighbors. Use raw for the max test;
    // smoothing is only for a less-noisy amplitude.)
    const rawCenter = this.history[this.peakHalfWindow].y;
    let smoothCenter;
    if (this.smooth && win === 5) {
      const h = this.history;
      smoothCenter = (1*h[0].y + 4*h[1].y + 6*h[2].y + 4*h[3].y + 1*h[4].y) / 16.0;
    } else if (this.smooth && win === 3) {
      const h = this.history;
      smoothCenter = (h[0].y + h[1].y + h[2].y) / 3.0;
    } else {
      smoothCenter = rawCenter;
    }

    // Strict local-max on raw neighbors vs the RAW center.
    for (let i = 0; i < win; ++i) {
      if (i === this.peakHalfWindow) continue;
      if (this.history[i].y >= rawCenter) return null;
    }
    // Recent-motion gate: reject peaks when the wrist isn't actually moving
    // (a frozen hand's 1 px jitter is a strict local max but not a chop).
    if (this.recent.length >= 3) {
      let m = 0; for (const v of this.recent) m += v; m /= this.recent.length;
      let v2 = 0; for (const v of this.recent) v2 += (v - m) * (v - m);
      const std = Math.sqrt(v2 / this.recent.length);
      if (std < this.minMotionStdPx) return null;
    }
    let rollingMin = this.rolling[0];
    for (let i = 1; i < this.rolling.length; ++i) {
      if (this.rolling[i] < rollingMin) rollingMin = this.rolling[i];
    }
    const amp = smoothCenter - rollingMin;
    if (amp < this.minAmplitudePx) return null;

    const centerFrame = this.history[this.peakHalfWindow].frameIdx;
    const centerT     = this.history[this.peakHalfWindow].tSec;
    if ((centerT - this.lastStrokeTSec) < this.minGapSec) return null;

    this.lastStrokeTSec  = centerT;
    this.lastStrokeFrame = centerFrame;
    this.nStrokes += 1;
    return {peakFrame: centerFrame, peakTSec: centerT,
            peakWristY: rawCenter, amplitudePx: amp};
  }
}

// ----------------------------------------------------------------------
// WristMotionStats
// Rolling 60-frame std of wrist x and y; bookkeeping of:
//   motion_pct     = fraction of frames with std_y >= minStdPx
//   chop_like_pct  = fraction with std_y >= chopRatioVsX * std_x
// (Same logic as the C++ block + Python port.)
// ----------------------------------------------------------------------
export class WristMotionStats {
  constructor(opts = {}) {
    this.window      = opts.windowFrames    ?? 60;
    this.minStdPx    = opts.minStdPx        ?? 8.0;
    this.chopRatio   = opts.chopRatioVsX    ?? 1.5;
    this.reset();
  }

  reset() {
    this.xs = []; this.ys = [];
    this.sumX = this.sumY = 0;
    this.sumXX = this.sumYY = 0;
    this.nObserved = this.nActive = this.nChop = 0;
  }

  update(x, y) {
    this.xs.push(x); this.ys.push(y);
    this.sumX  += x;   this.sumY  += y;
    this.sumXX += x*x; this.sumYY += y*y;
    if (this.xs.length > this.window) {
      const ox = this.xs.shift(); const oy = this.ys.shift();
      this.sumX  -= ox;   this.sumY  -= oy;
      this.sumXX -= ox*ox; this.sumYY -= oy*oy;
    }
    if (this.xs.length === this.window) {
      const n = this.window;
      const mx = this.sumX / n;
      const my = this.sumY / n;
      const vx = Math.max(0, this.sumXX / n - mx * mx);
      const vy = Math.max(0, this.sumYY / n - my * my);
      const sx = Math.sqrt(vx);
      const sy = Math.sqrt(vy);
      this.nObserved += 1;
      if (sy >= this.minStdPx) {
        this.nActive += 1;
        if (sy >= this.chopRatio * sx) this.nChop += 1;
      }
      return {sx, sy};
    }
    return null;
  }

  pctMotion() {
    return this.nObserved > 0 ? 100 * this.nActive / this.nObserved : 0;
  }
  pctChop() {
    return this.nObserved > 0 ? 100 * this.nChop / this.nObserved : 0;
  }
}

// ----------------------------------------------------------------------
// RollingCorrelation -- Pearson over the last N samples.
// (Only used if we later add a predicted-blade overlay; included for
// architectural parity with the Python port.)
// ----------------------------------------------------------------------
export class RollingCorrelation {
  constructor(window = 60) {
    this.window = window;
    this.a = []; this.b = [];
    this.sumA = this.sumB = 0;
    this.sumAA = this.sumBB = 0;
    this.sumAB = 0;
    this.sumCorr = 0; this.nCorr = 0;
  }
  reset() {
    this.a = []; this.b = [];
    this.sumA = this.sumB = 0;
    this.sumAA = this.sumBB = 0;
    this.sumAB = 0;
    this.sumCorr = 0; this.nCorr = 0;
  }
  update(a, b) {
    this.a.push(a); this.b.push(b);
    this.sumA += a; this.sumB += b;
    this.sumAA += a*a; this.sumBB += b*b;
    this.sumAB += a*b;
    if (this.a.length > this.window) {
      const oa = this.a.shift(); const ob = this.b.shift();
      this.sumA -= oa; this.sumB -= ob;
      this.sumAA -= oa*oa; this.sumBB -= ob*ob;
      this.sumAB -= oa*ob;
    }
    const n = this.a.length;
    if (n < 2) return NaN;
    const ma = this.sumA / n;
    const mb = this.sumB / n;
    const va = this.sumAA / n - ma * ma;
    const vb = this.sumBB / n - mb * mb;
    const cab = this.sumAB / n - ma * mb;
    const denom = Math.sqrt(Math.max(0, va) * Math.max(0, vb));
    if (denom < 1e-9) return NaN;
    const c = cab / denom;
    this.sumCorr += c; this.nCorr += 1;
    return c;
  }
  mean() {
    return this.nCorr > 0 ? this.sumCorr / this.nCorr : NaN;
  }
}
