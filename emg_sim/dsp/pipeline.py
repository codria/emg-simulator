"""Raw EMG → smoothed amplitude (rectify → RMS window → EMA)."""

from __future__ import annotations

import math
from collections import deque

import numpy as np


class RMSPipeline:
    """Per-channel RMS over a sliding window, then a light EMA. Also keeps a
    longer rolling buffer of raw samples for the on-screen waveform.

    TODO(real EMG): prepend a band-pass (≈20–450 Hz) + 50/60 Hz notch
    (scipy.signal) before the RMS. The synthetic dummy needs neither.
    """

    def __init__(self, cfg):
        self.sr = int(cfg.signal.sample_rate)
        self.win = max(1, int(round(cfg.signal.rms_window_ms / 1000.0 * self.sr)))
        self.alpha = float(cfg.signal.ema_alpha)
        self._win = [deque(maxlen=self.win) for _ in range(2)]
        self._disp_n = max(1, int(round(cfg.signal.display_sec * self.sr)))
        self._disp = [deque([0.0] * self._disp_n, maxlen=self._disp_n) for _ in range(2)]
        self.rms = np.zeros(2)
        self.ema = np.zeros(2)

    def process(self, raw: np.ndarray) -> np.ndarray:
        """Feed new raw samples ``(k, 2)``; return current smoothed amplitude ``(2,)``."""
        for ch in range(2):
            if raw.size:
                col = raw[:, ch]
                self._win[ch].extend(col)
                self._disp[ch].extend(col)
            if self._win[ch]:
                w = np.fromiter(self._win[ch], float)
                self.rms[ch] = math.sqrt(float(np.mean(w * w)))
            else:
                self.rms[ch] = 0.0
        self.ema = self.alpha * self.rms + (1.0 - self.alpha) * self.ema
        return self.ema.copy()

    def waveform(self, ch: int) -> np.ndarray:
        """Rolling raw-sample buffer for channel ``ch`` (0=left, 1=right)."""
        return np.fromiter(self._disp[ch], float)
