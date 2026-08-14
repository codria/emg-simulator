"""Amplitude → normalized activation in [0,1] (§5), left/right independent.

Design "合わせ技":
  * baseline (脱力) subtraction — captured on command, more reliable than MVC
  * scale division with a fallback fixed gain so it always moves
  * upward-only, slow online adaptation of the scale to the observed peak
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

    def normalize(self, amp: np.ndarray) -> np.ndarray:
        x = np.maximum(0.0, amp - self.baseline)
        if self.cfg.adapt_rate > 0.0:
            self._peak = np.maximum(self._peak, x)
            # upward-only, slow
            self.scale = self.scale + self.cfg.adapt_rate * np.maximum(0.0, self._peak - self.scale)
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

    def reset_adaptation(self) -> None:
        self._peak = np.zeros(2)
        self.scale = np.full(2, float(self.cfg.fallback_scale))
