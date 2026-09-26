"""Numerical parity with the published September 7 wrist.js and score.js.

This kernel does not authenticate its input. Only independently extracted video
samples may become server evidence. Client trajectories must remain unverified.
Source hashes and parity fixtures are recorded in tests/fixtures/published_motion.
"""
from collections import deque
from math import exp, floor, isfinite, sqrt
from statistics import median


def _rounded(value):
    return None if value is None else floor(value + .5)


def _steady(values, k):
    if len(values) < 3:
        return None
    center = median(values)
    if center <= 0:
        return None
    deviation = 1.4826 * median(abs(value - center) for value in values)
    return min(100, max(0, 100 * exp(-k * deviation / center)))


def score_motion_samples(samples):
    """Score bounded, ordered (seconds, wrist-x-pixels, wrist-y-pixels) samples.

    Pixel coordinates must use the source camera's coordinate system. Scaling,
    cropping, dropout treatment and sampling are part of video verification,
    not facts inferred or accepted from an applicant's numerical score.
    """
    if not isinstance(samples, (list, tuple)) or len(samples) > 4000:
        raise ValueError('Motion samples must be a bounded sequence')
    history, baseline, recent = deque(maxlen=5), deque(maxlen=15), deque(maxlen=9)
    xs, ys = deque(), deque()
    sx = sy = sxx = syy = 0.0
    observed = active = chopping = 0
    times, amplitudes = [], []
    previous = -float('inf')
    last_peak = -1e9
    for sample in samples:
        if not isinstance(sample, (list, tuple)) or len(sample) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in sample):
            raise ValueError('Motion samples must contain finite coordinates and timestamps')
        t, x, y = sample
        if t <= previous or t < 0 or t > 180 or max(abs(x), abs(y)) > 16384:
            raise ValueError('Motion samples exceed the supported capture bounds')
        previous = t
        history.append((t, y)); baseline.append(y); recent.append(y)
        xs.append(x); ys.append(y)
        sx += x; sy += y; sxx += x*x; syy += y*y
        if len(xs) > 60:
            ox, oy = xs.popleft(), ys.popleft()
            sx -= ox; sy -= oy; sxx -= ox*ox; syy -= oy*oy
        if len(xs) == 60:
            std_x = sqrt(max(0, sxx / 60 - (sx / 60)**2))
            std_y = sqrt(max(0, syy / 60 - (sy / 60)**2))
            observed += 1
            if std_y >= 8:
                active += 1
                if std_y >= 1.5 * std_x:
                    chopping += 1
        if len(history) < 5:
            continue
        center_t, center_y = history[2]
        if any(y_at >= center_y for i, (_, y_at) in enumerate(history) if i != 2):
            continue
        smooth = sum(weight * row[1] for weight, row in zip((1, 4, 6, 4, 1), history)) / 16
        if len(recent) >= 3:
            mean = sum(recent) / len(recent)
            if sqrt(sum((v - mean)**2 for v in recent) / len(recent)) < 11:
                continue
        amplitude = smooth - min(baseline)
        if amplitude < 18 or center_t - last_peak < .30:
            continue
        last_peak = center_t
        times.append(center_t); amplitudes.append(amplitude)
    return summarize_motion(times, amplitudes, observed, active, chopping)


def summarize_motion(times, amplitudes, observed, active, chopping):
    """Published score summary, shared by uninterrupted and control-event replay."""
    intervals = [b-a for a, b in zip(times, times[1:])]
    rhythm = _steady(intervals, 1.0) if len(times) >= 3 else None
    consistency = _steady(amplitudes, 1.1)
    percentage = 100 * chopping / observed if observed else 0
    form = percentage if percentage > 0 else None
    axes = [(v, w) for v, w in ((rhythm, .45), (consistency, .30), (form, .25)) if v is not None]
    overall = sum(v*w for v, w in axes) / sum(w for _, w in axes) if axes and len(times) >= 3 else None
    cadence = 1 / median(intervals) if len(times) >= 3 and median(intervals) > 0 else 0
    return {'overall': _rounded(overall), 'rhythm': _rounded(rhythm),
            'consistency': _rounded(consistency), 'form': _rounded(form),
            'strokes': len(times), 'cadence': floor(cadence*100 + .5) / 100,
            'motionPercent': 100*active/observed if observed else 0,
            'observedWindows': observed, 'activeWindows': active, 'choppingWindows': chopping,
            'strokeTimes': times, 'strokeAmplitudes': amplitudes}
