"""Amplitude → normalized activation in [0,1] (§5), left/right independent.

Design "合わせ技":
  * baseline (脱力) subtraction — captured on command, more reliable than MVC
  * scale division with a fallback fixed gain (also a floor) so it always moves
  * slow adaptation of the scale toward a *leaky* peak — a one-off artifact / max
    clench decays out instead of latching the gain up forever (which would block
    the extremes); the scale never drops below the fallback floor
  * tanh soft saturation so a loose calibration never pegs hard
"""

from __future__ import annotations

import numpy as np


class Normalizer:
    def __init__(self, cfg):
        self.cfg = cfg.normalize
        self.baseline = np.zeros(2)
        self.scale = np.full(2, float(self.cfg.fallback_scale))
        self._peak = np.zeros(2)
        self._cap = None  # baseline-capture accumulator

    def normalize(self, amp: np.ndarray, dt: float = 0.0) -> np.ndarray:
        x = np.maximum(0.0, amp - self.baseline)
        if self.cfg.adapt_rate > 0.0:
            # leaky peak: a "recent-max" high-water mark that slowly forgets stale
            # highs, so a one-off artifact / max clench can't latch the gain up for
            # good (dt = frame time; no decay when called without it, e.g. in tests).
            hl = self.cfg.peak_halflife_sec
            if hl > 0.0 and dt > 0.0:
                self._peak = self._peak * (0.5 ** (dt / hl))
            self._peak = np.maximum(self._peak, x)
            # ease the scale toward the leaky peak — both ways — but never below the
            # fallback floor (keeps it from getting over-sensitive when idle).
            target = np.maximum(self._peak, self.cfg.fallback_scale)
            self.scale = self.scale + self.cfg.adapt_rate * (target - self.scale)
        scale = np.maximum(self.scale, 1e-6)
        a = x / scale
        if self.cfg.soft_sat:
            a = np.tanh(self.cfg.sat_gain * a)
        else:
            a = np.clip(a, 0.0, 1.0)
        return a

    # -- baseline (脱力) capture -------------------------------------------
    def start_baseline(self) -> None:
        self._cap = [[], []]

    def feed_baseline(self, amp: np.ndarray) -> None:
        if self._cap is not None:
            self._cap[0].append(float(amp[0]))
            self._cap[1].append(float(amp[1]))

    def finish_baseline(self) -> None:
        if self._cap is not None and self._cap[0] and self._cap[1]:
            self.baseline = np.array([float(np.mean(self._cap[0])), float(np.mean(self._cap[1]))])
        self._cap = None

    @property
    def capturing(self) -> bool:
        return self._cap is not None

    @property
    def peak(self) -> np.ndarray:
        """Per-channel high-water mark of (amp − baseline); the scale follows it."""
        return self._peak

    def reset_adaptation(self) -> None:
        self._peak = np.zeros(2)
        self.scale = np.full(2, float(self.cfg.fallback_scale))
