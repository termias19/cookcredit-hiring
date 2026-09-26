"""Cut-type intelligence -- recognize the knife TECHNIQUE and score execution.

The B2B differentiator: competitors can't tell a cut from a non-cut; we identify *which*
technique is happening and whether it was executed correctly, then score against the
matching rubric.

CALIBRATED (2026-06-04) on the three labeled TE technique exemplars (workflow wz0n2mflz),
extracted with a consistent MediaPipe pipeline. Honest findings that shaped this code:
  - Only TWO kinematic features separate the techniques:
      * tip/wrist VERTICAL-amplitude ratio (bout p95-p5): guillotine 0.76, slice 1.01,
        rock_chop 1.42  -> separates rock_chop (wrist pivots, tip sweeps) from guillotine
        (wrist drives the drop).
      * horizontal-draw dominance (per-stroke H/V + fast-phase |vx|/|vy|): slice 1.16/1.54
        vs guillotine 0.42 and rock_chop 0.54  -> isolates slice (draw cut).
  - blade-angle swing and corr(wrist_y,tip_y) DID NOT separate (guillotine 15deg ~ rock 16.5deg;
    corr all 0.74-0.83) because the "blade" is a 2.6x hand-pose extrapolation, not a detected
    knife. They are kept as confidence tie-breakers only, never gates.
  - all three TE clips are slow (~0.6-0.76 Hz) -> cadence is a SPEED axis, not a technique gate.
  - n=1 per class / single angle -> thresholds are soft and flagged `low_calibration` until a
    pilot corpus exists; the classifier returns 'uncertain' rather than guess.

FORGEABILITY: the technique derives from the client trajectory, which is forgeable
(see project_scorer_foolproofing_audit). This is a PRACTICE/feedback signal, NOT the B2B
certifying verdict, until video re-derivation + liveness + identity land (Launch 2).

Two axes: MOTION technique (here) x PRODUCT geometry (julienne/dice cube size -- needs the CV
output-half; returned null). Dependency-light: numpy + scipy.signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
from scipy.signal import find_peaks

BLADE_K = 2.6                  # blade tip = wrist + K*(mcp - wrist) (matches mise / engine)

# ---- CALIBRATED decision thresholds (measured on the 3 TE exemplars) --------------------
SLICE_HV_FAST      = 1.00      # fast-phase |vx|/|vy| >= this -> slice (measured slice 1.54)
SLICE_HV_PERSTROKE = 0.90      # per-stroke |dx|/|dy| >= this -> slice (slice 1.16 vs <=0.54)
ROCK_TIP_WRIST     = 1.10      # tip/wrist vert-amp ratio >= this -> rock_chop (between guillotine 0.76 and rock 1.35-1.42)
# Soft bands per class for transparency + confidence (over the two SEPARATING features).
BANDS = {
    "guillotine": {"tip_wrist_amp_ratio": (0.50, 1.05), "hv_fast": (0.0, 0.85)},
    "rock_chop":  {"tip_wrist_amp_ratio": (1.20, 1.90), "hv_fast": (0.0, 0.85)},
    "slice":      {"tip_wrist_amp_ratio": (0.60, 1.40), "hv_fast": (1.00, 3.0)},
}
MIN_STROKES, MIN_BOUT_SEC = 6, 4.0
# Segmenter tuning -- calibrated (offline sweep on the TE trajectories) to reproduce the
# curated counts (~38/49/44 vs target 33/49/49; the prior config over-counted jitter).
SEG_SMOOTH_SEC, SEG_MIN_SEP, SEG_PROM_FACTOR = 0.27, 0.35, 0.45


@dataclass
class CutFeatures:
    n_strokes: int
    duration_sec: float
    cadence_hz: float
    interval_cv: Optional[float]
    hand_scale_px: float
    tip_vert_amp_px: float            # bout p95-p5 of tip_y
    wrist_vert_amp_px: float          # bout p95-p5 of wrist_y
    tip_wrist_amp_ratio: float        # SEPARATES rock_chop vs guillotine
    hv_perstroke: float               # per-stroke median |dx|/|dy| (SEPARATES slice)
    hv_fast: float                    # fast-phase |vx|/|vy| (cleanest slice gate)
    corr_wrist_tip_y: float           # confidence-only (did NOT separate)
    angle_osc_deg: float              # confidence-only (did NOT separate)


def _detrend(y: np.ndarray, fps: float, win_sec: float = 1.5) -> np.ndarray:
    win = max(3, int(round(win_sec * fps)) | 1)
    if len(y) <= win:
        return y - np.mean(y)
    return y - np.convolve(y, np.ones(win) / win, mode="same")


def _detect_strokes(ty: np.ndarray, fps: float):
    """Downstroke peaks (y grows downward -> a chop is a local MAX). Robust segmenter:
    smooth + detrend + min separation + prominence relative to signal amplitude. Tuned
    (SEG_* constants) to reproduce the curated counts (~33 guillotine, ~49 rock/slice);
    the prior find_peaks(prominence=0.3*std) over-counted MediaPipe jitter."""
    k = max(1, int(round(SEG_SMOOTH_SEC * fps / 2.0)))
    s = np.convolve(ty, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    s = _detrend(s, fps)
    amp = float(np.percentile(s, 95) - np.percentile(s, 5))
    if amp < 1e-6:
        return np.array([], dtype=int), s
    dist = max(1, int(round(SEG_MIN_SEP * fps)))
    peaks, _ = find_peaks(s, distance=dist, prominence=SEG_PROM_FACTOR * amp)
    return peaks, s


def compute_features(traj: list, fps: float) -> Optional[CutFeatures]:
    """traj: list of frames {t, wx, wy, mx, my} (wrist + middle-MCP, pixels). Returns the
    calibrated discriminating features, or None if too little signal."""
    pts = [d for d in (traj or []) if d.get("wx") is not None and d.get("mx") is not None]
    if len(pts) < 16:
        return None
    t = np.array([d["t"] for d in pts], float)
    wx = np.array([d["wx"] for d in pts], float); wy = np.array([d["wy"] for d in pts], float)
    mx = np.array([d["mx"] for d in pts], float); my = np.array([d["my"] for d in pts], float)
    tx = wx + BLADE_K * (mx - wx); ty = wy + BLADE_K * (my - wy)

    span = float(t[-1] - t[0])
    if span <= 0.5:
        return None
    eff_fps = max(1.0, (len(t) - 1) / span)
    hand_scale = float(np.median(np.hypot(mx - wx, my - wy))) or 1.0

    peaks, _ = _detect_strokes(ty, eff_fps)
    n = int(len(peaks))
    if n < 3:
        return None

    iv = np.diff(t[peaks])
    interval_cv = float(np.std(iv) / max(np.mean(iv), 1e-9)) if len(iv) else None
    cadence = float(n / span)

    # Amplitude RATIO from bout p95-p5 (robust; the curated discriminator). guillotine<1, rock>1.
    tip_vert = float(np.percentile(ty, 95) - np.percentile(ty, 5))
    wrist_vert = float(np.percentile(wy, 95) - np.percentile(wy, 5))
    ratio = tip_vert / wrist_vert if wrist_vert > 1e-6 else (9.9 if tip_vert > 0 else 0.0)

    # Per-stroke horizontal-draw / vertical-drop (trough -> peak descent). Isolates slice.
    hv_list = []
    for i in range(1, n):
        a, b = peaks[i - 1], peaks[i]
        trough = a + int(np.argmin(ty[a:b + 1]))
        dy = abs(ty[b] - ty[trough]); dx = abs(tx[b] - tx[trough])
        if dy > 1e-6:
            hv_list.append(dx / dy)
    hv_perstroke = float(np.median(hv_list)) if hv_list else 0.0

    # Draw-during-DESCENT |vx|/|vy|: restrict to fast DOWNWARD frames (the actual cutting
    # phase). This isolates a slice's draw (horizontal WHILE descending) from a guillotine's
    # between-cut repositioning (horizontal with the blade lifted, vy~0) -- the cleanest slice
    # gate. (Using all fast frames let the lateral board-traverse inflate guillotine's ratio.)
    vx = np.diff(tx); vy = np.diff(ty)
    down = vy > 0
    if np.any(down):
        vyd, vxd = vy[down], vx[down]
        fast = vyd >= np.percentile(vyd, 60)
        hv_fast = float(np.sum(np.abs(vxd[fast])) / max(np.sum(vyd[fast]), 1e-9)) if np.any(fast) else 0.0
    else:
        hv_fast = 0.0

    # Confidence-only features (did NOT separate -- kept for transparency / tie-breaks).
    wy_hp = _detrend(wy, eff_fps); ty_hp = _detrend(ty, eff_fps)
    corr = float(np.corrcoef(wy_hp, ty_hp)[0, 1]) if np.std(wy_hp) > 1e-6 and np.std(ty_hp) > 1e-6 else 0.0
    dx_, dy_ = mx - wx, my - wy
    dn = np.hypot(dx_, dy_) + 1e-9
    ux, uy = dx_ / dn, dy_ / dn
    mvx, mvy = float(np.mean(ux)), float(np.mean(uy)); mvn = math.hypot(mvx, mvy) + 1e-9
    dev = np.degrees(np.arccos(np.clip(ux * (mvx / mvn) + uy * (mvy / mvn), -1.0, 1.0)))
    angle_osc = float(np.median([np.max(dev[peaks[i - 1]:peaks[i] + 1]) - np.min(dev[peaks[i - 1]:peaks[i] + 1])
                                 for i in range(1, n)])) if n > 1 else 0.0

    return CutFeatures(
        n_strokes=n, duration_sec=round(span, 2), cadence_hz=round(cadence, 3),
        interval_cv=round(interval_cv, 3) if interval_cv is not None else None,
        hand_scale_px=round(hand_scale, 2),
        tip_vert_amp_px=round(tip_vert, 2), wrist_vert_amp_px=round(wrist_vert, 2),
        tip_wrist_amp_ratio=round(ratio, 3),
        hv_perstroke=round(hv_perstroke, 3), hv_fast=round(hv_fast, 3),
        corr_wrist_tip_y=round(corr, 3), angle_osc_deg=round(angle_osc, 2),
    )


def _fit(value, lo, hi) -> float:
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1e-6)
    return max(0.0, 1.0 - (lo - value if value < lo else value - hi) / width)


def classify_technique(f: CutFeatures) -> dict:
    """2-feature decision tree calibrated on the TE exemplars (slice by draw-dominance, then
    rock_chop vs guillotine by the tip/wrist ratio). Fails safely to 'uncertain'."""
    # Soft per-class band fit (transparency + confidence), over the two separating features.
    scores = {}
    for tech, bands in BANDS.items():
        scores[tech] = round(float(np.mean([
            _fit(f.tip_wrist_amp_ratio, *bands["tip_wrist_amp_ratio"]),
            _fit(f.hv_fast, *bands["hv_fast"]),
        ])), 3)

    # Hard decision tree on the two measured separators: draw-during-descent (hv_fast)
    # isolates slice; then the tip/wrist vertical-amp ratio splits rock_chop from guillotine.
    if f.hv_fast >= SLICE_HV_FAST:
        tech = "slice"
        bd = (f.hv_fast - SLICE_HV_FAST) / SLICE_HV_FAST
    else:
        slice_margin = (SLICE_HV_FAST - f.hv_fast) / SLICE_HV_FAST     # margin from misfiring slice
        if f.tip_wrist_amp_ratio >= ROCK_TIP_WRIST:
            tech = "rock_chop"; ratio_margin = (f.tip_wrist_amp_ratio - ROCK_TIP_WRIST) / ROCK_TIP_WRIST
        else:
            tech = "guillotine"; ratio_margin = (ROCK_TIP_WRIST - f.tip_wrist_amp_ratio) / ROCK_TIP_WRIST
        bd = min(slice_margin, ratio_margin)

    # Confidence + 'uncertain' from the normalized distance to the DECISION boundary (the hard
    # tree), not the soft band-fit overlap (which muddied clean calls). Fails safely when close.
    confidence = round(float(np.clip(0.40 + bd, 0.0, 1.0)), 3)
    uncertain = (f.n_strokes < MIN_STROKES or f.duration_sec < MIN_BOUT_SEC or bd < 0.06)
    margin = bd
    # The guillotine<->rock_chop call rests on a single n=1/class ratio gap.
    low_calibration = tech in ("guillotine", "rock_chop")

    return {
        "technique": "uncertain" if uncertain else tech,
        "candidate": tech, "confidence": confidence, "margin": round(margin, 3),
        "scores": scores, "low_calibration": low_calibration,
        "flags": {
            "few_strokes": f.n_strokes < MIN_STROKES, "short_bout": f.duration_sec < MIN_BOUT_SEC,
        },
        "_note": "Calibrated on n=1/technique (single angle). Forgeable client signal -> practice "
                 "feedback, NOT a B2B certifying verdict (project_scorer_foolproofing_audit).",
    }


def score_guillotine_dice(f: CutFeatures, profile: dict) -> dict:
    """Score a guillotine-dice attempt. MOTION half (technique + execution) scored from
    kinematics; PRODUCT half (cube size/uniformity) needs the CV output-half -> null."""
    cls = classify_technique(f)
    required = profile.get("required_technique", "guillotine")
    technique_match = cls["candidate"] == required and cls["technique"] != "uncertain"
    technique_score = round(100.0 * cls["scores"].get(required, 0.0), 1)

    # draw_discipline: a guillotine is pure-vertical; penalize draw toward the slice boundary.
    # Uses hv_fast (draw-during-descent, clean) not hv_perstroke (repositioning-contaminated).
    # NOTE: execution sub-scores are PROVISIONAL -- the beginner->expert scale needs the pilot
    # corpus (one expert exemplar can't calibrate it). Classification is the validated part.
    draw_discipline = round(100.0 * float(np.clip(1.0 - f.hv_fast / SLICE_HV_FAST, 0.0, 1.0)), 1)
    rhythm = round(100.0 * max(0.0, 1.0 - min(f.interval_cv or 1.0, 1.0)), 1)
    bhz = profile.get("beginner_speed_hz", 0.5); ehz = profile.get("expert_speed_hz", 2.0)
    speed = round(100.0 * float(np.clip((f.cadence_hz - bhz) / max(ehz - bhz, 1e-6), 0, 1)), 1)

    return {
        "cut_type": "guillotine_dice",
        "technique_detected": cls["technique"],
        "technique_candidate": cls["candidate"],
        "technique_confidence": cls["confidence"],
        "technique_match": technique_match,
        "low_calibration": cls["low_calibration"],
        "technique_scores": cls["scores"],
        "motion_half": {
            "technique": technique_score,
            "draw_discipline": draw_discipline,   # guillotine = low horizontal draw
            "rhythm": rhythm,
            "speed": speed,
        },
        "product_half": {
            "fineness": None, "consistency": None, "cross_pass_detected": None,
            "note": "Cube size/uniformity + the 90deg cross-pass need the CV piece-measurement "
                    "output-half; not derivable from motion.",
        },
        "features": asdict(f),
        "note": "Motion-half (technique + execution) from kinematics. NOT a final B2B verdict until "
                "the CV product-half + anti-cheat/liveness land (project_scorer_foolproofing_audit). "
                "verticality/angle dropped as a gate -- did not separate on real data.",
    }
