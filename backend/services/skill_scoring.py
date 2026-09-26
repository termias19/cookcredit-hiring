"""Cook skill scoring -- the chopping skill-test gate.

The browser (MediaPipe) captures the cook's wrist trajectory and uploads it as
JSON; this scores the *technique* (rock-chop oscillation quality) server-side so
the number is authoritative (never trust the client's score). Ported from the
CookCredit engine's validated oscillation metric (trained-chef russian_chop ~91).

Dependency-light: numpy + scipy.signal only -- the heavy CV (MediaPipe) runs in
the browser, so Render stays light. No OpenCV / MediaPipe here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.signal import find_peaks, welch

# Plausible chopping cadence band (Hz). Upper bound raised 4 -> 8 so fast claw-grip
# chopping is captured IN-band instead of being rejected/aliased: the old 1-4 Hz cap
# made a consistent 5-8 Hz elite chop FAIL (it fell outside the band) while a lazy 2 Hz
# wave scored gold — a skill inversion (see project_scorer_foolproofing_audit). min_dist
# below scales with CHOP_FMAX, so peaks up to ~CHOP_FMAX are resolvable (Nyquist-limited
# by capture fps). NOTE: robustly REJECTING fast-but-IRREGULAR flailing needs the elite
# sharpness gate (prominence/amplitude) + pilot-corpus calibration — deferred.
CHOP_FMIN, CHOP_FMAX = 1.0, 8.0
MIN_CYCLES = 3

# --- gate calibration (PROVISIONAL -- tune from the pilot corpus) ----------
PASS_SCORE = 55.0                 # >= this (and sufficient + robust) => skill_verified
TIERS = [(82.0, "gold"), (68.0, "silver"), (PASS_SCORE, "bronze")]

# --- robustness gate for the VERDICT (verified/tier), separate from the score ---
# `confidence` is computed by compute_oscillation_quality but was previously unused
# in the verdict, which let a brief fluke of pseudo-regular motion score a passing
# (even gold) result. A genuine chopping demonstration must be confident, SUSTAINED,
# and multi-cycle -- not a 1.5s/3-cycle blip. These are conservative floors, NOT
# calibrated cut points; tune alongside PASS_SCORE/TIERS once pilot data exists.
MIN_VERIFY_CONFIDENCE = 0.6
MIN_VERIFY_BOUT_SEC = 4.0
MIN_VERIFY_CYCLES = 6


@dataclass
class OscillationResult:
    oscillation_quality: float
    confidence: float
    sufficient: bool
    dom_freq_hz: float
    prominence: float
    peak_ratio: float
    interval_cv: Optional[float]
    amplitude_cv: Optional[float]
    n_cycles: int


def compute_oscillation_quality(signal, fps: float) -> Optional[OscillationResult]:
    if signal is None or len(signal) < 16:
        return None
    s = np.asarray(signal, dtype=np.float64)
    # High-pass detrend: subtract a ~1.5s moving-average baseline to remove the
    # low-frequency drift of the hand slowly repositioning across the board WITHOUT
    # removing the chop itself (drift ~0.5 Hz; chops 1-3 Hz; a 1.5s window high-passes
    # at ~0.67 Hz, between them). Plain mean-subtraction left the drift in, which
    # buried fast small-amplitude (expert) chopping. (Cf. the elite engine's slow-EWMA
    # baseline. A 0.7s window was too short -- it removed slow ~1.3 Hz chops too.)
    win = max(3, int(round(1.5 * fps)) | 1)   # odd window
    if len(s) > win:
        s = s - np.convolve(s, np.ones(win) / win, mode="same")
    else:
        s = s - np.mean(s)
    if np.std(s) < 1e-9:
        return None

    nperseg = min(len(s), max(64, int(fps * 3)))
    freqs, power = welch(s, fs=fps, nperseg=nperseg)
    band = (freqs >= CHOP_FMIN) & (freqs <= CHOP_FMAX)
    if not np.any(band) or np.sum(power[band]) < 1e-12:
        return None
    bf, bp = freqs[band], power[band]
    pk = int(np.argmax(bp))
    dom_freq = float(bf[pk])
    prominence = float(bp[pk] / np.sum(bp))
    peak_ratio = float(bp[pk] / max(np.median(bp), 1e-12))

    min_dist = max(1, int(fps / (CHOP_FMAX * 1.5)))
    peaks, _ = find_peaks(s, distance=min_dist,
                          prominence=0.15 * np.std(s) if np.std(s) > 0 else None)
    n_cycles = int(len(peaks))
    prom_gate = min(1.0, prominence / 0.30)

    if n_cycles < MIN_CYCLES:
        provisional = 100.0 * prom_gate * 0.4
        return OscillationResult(
            oscillation_quality=float(provisional), confidence=0.2,
            sufficient=False, dom_freq_hz=dom_freq, prominence=prominence,
            peak_ratio=peak_ratio, interval_cv=None, amplitude_cv=None,
            n_cycles=n_cycles)

    iv = np.diff(peaks) / fps
    interval_cv = float(np.std(iv) / max(np.mean(iv), 1e-9))
    amps = []
    for i in range(len(peaks) - 1):
        seg = s[peaks[i]:peaks[i + 1]]
        if len(seg):
            amps.append(float(s[peaks[i]] - np.min(seg)))
    amplitude_cv = (float(np.std(amps) / max(abs(np.mean(amps)), 1e-9)) if amps else 1.0)

    reg = max(0.0, 1.0 - min(interval_cv, 1.0))
    amp = max(0.0, 1.0 - min(amplitude_cv, 1.0))
    quality = 100.0 * prom_gate * (0.5 * reg + 0.5 * amp)
    confidence = float(min(1.0, (n_cycles / 6.0)) * min(1.0, prominence / 0.30))
    return OscillationResult(
        oscillation_quality=float(quality), confidence=confidence,
        sufficient=True, dom_freq_hz=dom_freq, prominence=prominence,
        peak_ratio=peak_ratio, interval_cv=interval_cv,
        amplitude_cv=amplitude_cv, n_cycles=n_cycles)


def refine_bout(s, fps: float):
    s = np.asarray(s, dtype=np.float64)
    n = len(s)
    win = max(int(1.5 * fps), 16)
    if n <= win:
        return 0, n
    step = max(1, int(0.5 * fps))
    starts, act = [], []
    for st in range(0, n - win + 1, step):
        seg = s[st:st + win] - np.mean(s[st:st + win])
        spec = np.abs(np.fft.rfft(seg))
        freqs = np.fft.rfftfreq(len(seg), d=1.0 / fps)
        band = (freqs >= CHOP_FMIN) & (freqs <= CHOP_FMAX)
        starts.append(st)
        act.append(float(np.sum(spec[band] ** 2)))
    act = np.asarray(act)
    if act.max() <= 0:
        return 0, n
    above = act >= 0.35 * act.max()
    best_len, best_s, i = 0, 0, 0
    while i < len(above):
        if above[i]:
            j = i
            while j < len(above) and above[j]:
                j += 1
            if j - i > best_len:
                best_len, best_s = j - i, i
            i = j
        else:
            i += 1
    if best_len == 0:
        return 0, n
    return starts[best_s], min(n, starts[best_s + best_len - 1] + win)


def _tier(score: float, verified: bool) -> Optional[str]:
    if not verified:
        return None
    for thr, name in TIERS:
        if score >= thr:
            return name
    return None


def _isfinite_num(x) -> bool:
    """A real, finite number (not bool, not NaN/Inf, not a string)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def classify_cut_technique(trajectory: list) -> Optional[dict]:
    """Recognize the knife TECHNIQUE (guillotine / rock_chop / slice) from the SAME captured
    trajectory -- uses the wrist 'w' + middle-MCP 'm' the browser already records per frame
    (cut_type.py, calibrated on the engine's TE exemplars). Returns None if 'm' is absent or
    there is too little signal. PRACTICE/feedback signal (forgeable client trajectory), NOT a
    certifying verdict (see project_scorer_foolproofing_audit)."""
    from services.cut_type import compute_features, classify_technique  # lazy: avoid load-order issues
    traj = [{"t": d["t"], "wx": d["w"][0], "wy": d["w"][1], "mx": d["m"][0], "my": d["m"][1]}
            for d in (trajectory or [])
            if d.get("p") and isinstance(d.get("w"), list) and isinstance(d.get("m"), list)
            and len(d["w"]) == 2 and len(d["m"]) == 2
            and all(_isfinite_num(v) for v in (d["t"], d["w"][0], d["w"][1], d["m"][0], d["m"][1]))]
    if len(traj) < 16:
        return None
    feats = compute_features(traj, 30.0)
    if feats is None:
        return None
    cls = classify_technique(feats)
    return {"technique": cls["technique"], "candidate": cls["candidate"],
            "confidence": cls["confidence"], "low_calibration": cls["low_calibration"],
            "scores": cls["scores"], "n_strokes": feats.n_strokes}


def score_trajectory(trajectory: list) -> dict:
    """Score an uploaded capture trajectory.

    trajectory: list of {t: float, p: 0|1, w: [x,y] | null, ...} as produced by
    the browser capture app (wrist y-position over time = the chop oscillator).
    Returns a JSON-safe dict with the authoritative skill_score + verdict.
    """
    # Drop non-finite / non-numeric samples (NaN/Inf x or y, string coords) so a
    # malformed or poisoned capture can't reach the scorer or the demonstration-
    # data store, and can't soft-fail into a bogus persisted grade.
    pts = [(d["t"], d["w"][1]) for d in (trajectory or [])
           if d.get("p") and isinstance(d.get("w"), list) and len(d["w"]) == 2
           and _isfinite_num(d["t"]) and _isfinite_num(d["w"][0]) and _isfinite_num(d["w"][1])]
    if len(pts) < 16:
        return {"ok": False, "reason": "too few tracked frames",
                "skill_score": None, "verified": False, "tier": None}

    ts = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    span = float(ts[-1] - ts[0])
    if span <= 0.5:
        return {"ok": False, "reason": "capture too short",
                "skill_score": None, "verified": False, "tier": None}

    fps = max(1.0, (len(ts) - 1) / span)
    n = max(16, int(round(span * fps)) + 1)
    grid = np.linspace(ts[0], ts[-1], n)
    vals = np.interp(grid, ts, ys)
    i0, i1 = refine_bout(vals, fps)
    res = compute_oscillation_quality(vals[i0:i1], fps)
    if res is None:
        return {"ok": False, "reason": "no scorable chopping bout",
                "skill_score": None, "verified": False, "tier": None}

    score = round(res.oscillation_quality, 2)
    bout_sec = (i1 - i0) / fps
    # Robust = a confident, sustained, multi-cycle bout. The verdict requires it
    # (not just score >= PASS_SCORE) so erratic/short motion can't earn a pass.
    # The score itself is still reported for honest feedback.
    robust = bool(res.confidence >= MIN_VERIFY_CONFIDENCE
                  and bout_sec >= MIN_VERIFY_BOUT_SEC
                  and res.n_cycles >= MIN_VERIFY_CYCLES)
    verified = bool(res.sufficient and robust and score >= PASS_SCORE)
    # Data-quality flag: a near-zero interval AND amplitude CV is a machine-perfect
    # signal (metronome / synthetic), not human chopping. Not rejected in PRACTICE
    # mode, but flagged so the demonstration-data pipeline can exclude it and the
    # future validation path can treat it as suspect.
    icv, acv = res.interval_cv, res.amplitude_cv
    suspect_synthetic = bool(res.sufficient and icv is not None and acv is not None
                             and icv < 0.02 and acv < 0.02)
    return {
        "ok": True,
        "skill_score": score,
        "verified": verified,
        "tier": _tier(score, verified),
        "sufficient": res.sufficient,
        "robust": robust,
        "confidence": round(res.confidence, 3),
        "n_cycles": res.n_cycles,
        "dom_freq_hz": round(res.dom_freq_hz, 3),
        "interval_cv": round(icv, 3) if icv is not None else None,
        "amplitude_cv": round(acv, 3) if acv is not None else None,
        "suspect_synthetic": suspect_synthetic,
        "bout_sec": round(bout_sec, 2),
        "fps_est": round(fps, 1),
        "pass_threshold": PASS_SCORE,
        # Cut TYPE (guillotine/rock_chop/slice) from the same trajectory -- the B2B-screen
        # differentiator. None if the capture lacks the middle-MCP 'm'. Practice signal only.
        "technique": classify_cut_technique(trajectory),
    }
