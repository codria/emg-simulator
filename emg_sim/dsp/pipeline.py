"""Raw EMG → smoothed amplitude (rectify → RMS window → EMA)."""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from .filter import EMGFilter


class RMSPipeline:
    """Front-end filter → rectify/RMS over a sliding window → light EMA. Keeps a
    longer rolling buffer of the *filtered* samples for the on-screen waveform, so
    the display is AC-coupled (the band-pass removes the electrode DC offset and
    baseline drift that would otherwise make the ground line wander) and matches
    the signal the RMS acts on. Disable the filter → the buffer shows raw.
    """

    def __init__(self, cfg):
        self.sr = int(cfg.signal.sample_rate)
        self.win = max(1, int(round(cfg.signal.rms_window_ms / 1000.0 * self.sr)))
        self.alpha = float(cfg.signal.ema_alpha)
        self.filter = EMGFilter(cfg)
        self._win = [deque(maxlen=self.win) for _ in range(2)]
        self._disp_n = max(1, int(round(cfg.signal.display_sec * self.sr)))
        self._disp = [deque([0.0] * self._disp_n, maxlen=self._disp_n) for _ in range(2)]
        self.rms = np.zeros(2)
        self.ema = np.zeros(2)

    def process(self, raw: np.ndarray) -> np.ndarray:
        """Feed new raw samples ``(k, 2)``; return current smoothed amplitude ``(2,)``."""
        filt = self.filter.process(raw)
        for ch in range(2):
            if raw.size:
                self._disp[ch].extend(filt[:, ch])  # display = filtered (AC-coupled)
                self._win[ch].extend(filt[:, ch])   # RMS = same filtered signal
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
