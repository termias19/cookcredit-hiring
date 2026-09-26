// eliteStroke.js -- faithful JS port of cookcredit_elite/src/elite_stroke_engine.h
//
// The elite Layer-2 stroke detector. Three discriminators that ACTUALLY separate
// real chops from setup jitter (measured on the Russian-chop ground truth: 5/5 true,
// 0 false), and -- crucially -- that catch FAST / BRACED / shallow expert chopping a
// fixed-threshold peak detector silently drops:
//
//   1. SHARPNESS = prominence / amplitude. Rhythmic chopping = SMOOTH periodic
//      oscillation -> ROUNDED peaks (prom/amp ~0.05-0.16). Jitter = jerky -> POINTY
//      peaks (prom/amp >=0.47). A 0.25 threshold separates them. It is a RATIO, so it
//      is scale- and camera-invariant, and per-stroke, so distribution-independent.
//   2. REGULARITY run-gate. A candidate is confirmed only as a member of a burst of
//      >= run_len candidates whose intervals lie in a plausible cadence band. Kills
//      smooth-but-ISOLATED false positives sharpness alone lets through, while
//      preserving a beginner's uneven cadence (no hard CoV gate by default).
//   3. AMPLITUDE is an ADAPTIVE noise floor (k_noise * slow robust scale), NOT a fixed
//      pixel threshold -- a fixed 30/60px floor silently drops every braced expert
//      chop. The floor rejects micro-noise only; it never tries to separate chops.
//
// Signal convention: push a vertical position y in PIXELS, y increasing DOWNWARD, so
// a chop-contact is a local MAXIMUM. In the browser we feed the predicted BLADE-TIP y
// (wrist + K*(mcp - wrist)) -- same as the C++ driver's --signal blade.
//
// Evaluation lag = AMP_HALF_WIN frames (need the post-peak trough), and the run-gate
// confirms the first stroke of a burst RETROACTIVELY when the 2nd lands. So a stroke is
// reported a few frames after the actual peak, and a run can flush TWO strokes on one
// frame -- update() therefore returns an ARRAY of strokes confirmed THIS frame (0/1/2),
// mirroring the C++ updateAll().
//
// Same math + defaults as the C++ source. OpenCV-free, no external deps.

const PEAK_HALF_WIN = 3;   // strict local max over 7
const SHARP_LAG     = 2;   // prominence neighbour offset
const AMP_HALF_WIN  = 8;   // local trough half-window (== evaluation lag)
const CAP           = 2 * AMP_HALF_WIN + 4;   // 20-sample ring
const CAND_CAP      = 8;

export class EliteStrokeEngine {
  constructor(opts = {}) {
    this.fps              = opts.fps              ?? 30.0;
    // SHARPNESS gate: prom/amp <= max keeps rounded (chop) peaks, drops pointy jitter.
    this.maxSharpness     = opts.maxSharpness     ?? 0.25;
    // ADAPTIVE amplitude noise floor = max(minAmpAbsPx, kNoise * slowScale).
    this.minAmpAbsPx      = opts.minAmpAbsPx      ?? 5.0;
    this.kNoise           = opts.kNoise           ?? 1.5;
    this.scaleEwmaAlpha   = opts.scaleEwmaAlpha   ?? 0.02;   // slow: baseline motion
    // REGULARITY run-gate.
    this.runLen           = opts.runLen           ?? 2;
    this.requireIntervalCov = opts.requireIntervalCov ?? false;  // off: beginners' CoV > 0.30
    this.maxIntervalCov   = opts.maxIntervalCov   ?? 0.30;
    this.minIntervalS     = opts.minIntervalS     ?? 0.12;   // plausible cadence band (<=~8 Hz)
    this.maxIntervalS     = opts.maxIntervalS     ?? 1.50;   // (>=~0.67 Hz)
    this.burstGapS        = opts.burstGapS        ?? 1.50;   // gap that ends a burst
    this.emitImmediately  = opts.emitImmediately  ?? false;  // A/B: skip run confirmation
    // Refractory in FRAMES vs the last accepted candidate (~0.12s).
    this.refractoryFrames = (opts.refractoryFrames && opts.refractoryFrames > 0)
      ? opts.refractoryFrames
      : Math.max(1, Math.round(0.12 * this.fps));
    this.reset();
  }

  reset() {
    this.samples = [];            // {y, frame, t, logical}, newest last, length <= CAP
    this.logicalNewest = -1;
    this.slowMean = 0; this.slowScale = 0; this.slowInit = false;
    this.lastAcceptFrame = -1e9;
    this.cands = [];              // {frame, t, y, amp, sharp, logical}, oldest first
    this.emittedThroughLogical = -1;
    this.nCandidates = 0;
    this.nEmitted = 0;            // == confirmed stroke count (the live counter)
    this._batch = [];
  }

  // Live counter + diagnostics (parity with the C++ accessors).
  get nStrokes()   { return this.nEmitted; }
  get candidates() { return this.nCandidates; }
  get emitted()    { return this.nEmitted; }

  // Fetch the sample at a logical index, if still in the ring (else null/evicted).
  _atLogical(L) {
    if (L < 0 || L > this.logicalNewest) return null;
    const len = this.samples.length;
    const idx = L - this.logicalNewest + (len - 1);   // newest is the last element
    if (idx < 0 || idx >= len) return null;           // evicted (fell off the ring)
    return this.samples[idx];
  }

  // Push one vertical sample; returns an array of strokes confirmed THIS frame.
  update(y, frame, tSec) {
    this._batch = [];
    // ----- push sample -----
    this.logicalNewest += 1;
    this.samples.push({ y, frame, t: tSec, logical: this.logicalNewest });
    if (this.samples.length > CAP) this.samples.shift();
    // ----- update adaptive scale (slow EWMA mean + MAD proxy) -----
    if (!this.slowInit) {
      this.slowMean = y; this.slowScale = 0; this.slowInit = true;
    } else {
      const a = this.scaleEwmaAlpha;
      this.slowMean = (1 - a) * this.slowMean + a * y;
      this.slowScale = (1 - a) * this.slowScale + a * Math.abs(y - this.slowMean);
    }
    this._evaluateCenter();
    return this._batch;
  }

  _evaluateCenter() {
    const center = this.logicalNewest - AMP_HALF_WIN;
    if (center < AMP_HALF_WIN) return;          // need a full window on both sides
    const c = this._atLogical(center);
    if (!c) return;
    const yc = c.y;

    // strict local maximum over [-PEAK_HALF_WIN, +PEAK_HALF_WIN]
    for (let k = -PEAK_HALF_WIN; k <= PEAK_HALF_WIN; k++) {
      if (k === 0) continue;
      const s = this._atLogical(center + k);
      if (!s) return;
      if (s.y >= yc) return;                    // not a strict max
    }

    // local trough -> amplitude
    let trough = yc;
    for (let k = -AMP_HALF_WIN; k <= AMP_HALF_WIN; k++) {
      const s = this._atLogical(center + k);
      if (s && s.y < trough) trough = s.y;
    }
    const amp = yc - trough;

    // ADAPTIVE noise floor (rejects micro-jitter only)
    const ampFloor = Math.max(this.minAmpAbsPx, this.kNoise * this.slowScale);
    if (amp < ampFloor) return;

    // SHARPNESS = prominence / amplitude
    const lL = this._atLogical(center - SHARP_LAG);
    const lR = this._atLogical(center + SHARP_LAG);
    if (!lL || !lR) return;
    const prom = yc - 0.5 * (lL.y + lR.y);
    const sharpness = amp > 1e-6 ? prom / amp : 9.9;
    if (sharpness > this.maxSharpness) return;  // pointy => jitter

    // refractory vs last accepted candidate
    if (c.frame - this.lastAcceptFrame < this.refractoryFrames) return;
    this.lastAcceptFrame = c.frame;

    this.nCandidates += 1;
    const cand = { frame: c.frame, t: c.t, y: yc, amp, sharp: sharpness, logical: center };

    if (this.emitImmediately) { this._emit(cand, 0.0); return; }
    this._pushCandidate(cand);
    this._confirmIfRegular();
  }

  _pushCandidate(c) {
    // burst boundary: a long gap ends the run.
    if (this.cands.length > 0) {
      const back = this.cands[this.cands.length - 1];
      if (c.t - back.t > this.burstGapS) this.cands = [];
    }
    this.cands.push(c);
    if (this.cands.length > CAND_CAP) this.cands.shift();
  }

  _confirmIfRegular() {
    const n = this.cands.length;
    if (n < this.runLen) return;
    const start = n - this.runLen;
    // intervals over the last run_len candidates
    let sum = 0, sumsq = 0, nIv = 0;
    for (let i = start + 1; i < n; i++) {
      const dt = this.cands[i].t - this.cands[i - 1].t;
      if (dt < this.minIntervalS || dt > this.maxIntervalS) return;  // implausible cadence
      sum += dt; sumsq += dt * dt; nIv++;
    }
    if (nIv === 0) return;
    const mean = sum / nIv;
    const varr = sumsq / nIv - mean * mean;
    const cov = mean > 1e-9 ? Math.sqrt(varr > 0 ? varr : 0) / mean : 9.9;
    if (this.requireIntervalCov && cov > this.maxIntervalCov) return;

    // Regular run confirmed: emit every candidate in the run not yet emitted
    // (retroactive for the first run_len-1, immediate after).
    for (let i = start; i < n; i++) {
      const c = this.cands[i];
      if (c.logical > this.emittedThroughLogical) this._emit(c, cov);
    }
  }

  _emit(c, cov) {
    const sTerm  = 1 - Math.min(1, c.sharp / this.maxSharpness);
    const cvTerm = this.emitImmediately ? 0.5 : 1 - Math.min(1, cov / this.maxIntervalCov);
    const confidence = Math.max(0.05, 0.5 * sTerm + 0.5 * cvTerm);
    this.emittedThroughLogical = Math.max(this.emittedThroughLogical, c.logical);
    this.nEmitted += 1;
    this._batch.push({
      peakFrame: c.frame, peakTSec: c.t, peakY: c.y,
      amplitudePx: c.amp, sharpness: c.sharp, intervalCov: cov, confidence,
    });
  }
}
