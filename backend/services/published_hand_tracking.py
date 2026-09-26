"""Published hand selection and wrist dropout handling for video extraction.

Consumes independently detected normalized wrists, never applicant trajectories.
One instance is one uninterrupted hand-selection segment. This is not a verifier.
"""
import math


class PublishedHandTracker:
    def __init__(self, hand):
        if hand not in ('Left', 'Right'):
            raise ValueError('A selected hand is required')
        self.hand = hand
        self.anchor = None
        self.held = None
        self.held_at = None
        self.velocity = (0, 0)
        self.previous_time = -1

    def update(self, time_sec, wrists, labels, *, session_time_sec=None):
        if (isinstance(time_sec, bool) or not isinstance(time_sec, (int, float)) or
                not math.isfinite(time_sec) or time_sec < 0 or not self.previous_time < time_sec <= 180):
            raise ValueError('Ordered bounded observation times are required')
        if not isinstance(wrists, (list, tuple)) or len(wrists) > 2:
            raise ValueError('At most two detected hands are supported')
        for wrist in wrists:
            if (not isinstance(wrist, (list, tuple)) or len(wrist) != 2 or
                    any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in wrist)):
                raise ValueError('Finite independently detected wrist coordinates are required')
        if not isinstance(labels, (list, tuple)) or len(labels) != len(wrists):
            raise ValueError('Each detected hand needs a label entry')
        clock = time_sec if session_time_sec is None else session_time_sec
        if (isinstance(clock, bool) or not isinstance(clock, (int, float)) or
                not math.isfinite(clock) or not 0 <= clock <= 180):
            raise ValueError('A bounded session clock is required')
        self.previous_time = time_sec
        index = None
        if len(wrists) == 1:
            index = 0
        elif wrists:
            if self.anchor is not None:
                index = min(range(len(wrists)), key=lambda i: math.hypot(
                    wrists[i][0]-self.anchor[0], wrists[i][1]-self.anchor[1]))
            else:
                index = next((i for i, label in enumerate(labels) if label == self.hand), 0)
        if index is not None:
            point = tuple(wrists[index])
            self.anchor = point
            if self.held is not None:
                dt = max(.001, clock-self.held_at)
                self.velocity = tuple((point[i]-self.held[i])/dt for i in (0, 1))
            self.held, self.held_at = point, clock
            return {'wrist': list(point), 'extrapolated': False}
        if self.held is not None and clock-self.held_at < .15:
            elapsed = clock-self.held_at
            return {'wrist': [self.held[i]+max(-.20, min(.20, self.velocity[i]*elapsed))
                              for i in (0, 1)], 'extrapolated': True}
        return None


    def change_hand(self, hand):
        """Published swapHand clears the anchor, but retains wrist/velocity hold."""
        if hand not in ('Left', 'Right'):
            raise ValueError('A selected hand is required')
        self.hand = hand
        self.anchor = None
