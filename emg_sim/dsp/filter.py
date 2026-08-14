"""Real-EMG front-end filter (§6): band-pass + mains notch.

Streaming, stateful IIR (SOS) filter applied to the raw bipolar EMG before
rectify/RMS: a Butterworth band-pass (≈20–450 Hz, removes motion-artifact drift
and out-of-band noise) plus an IIR notch at the mains frequency (50/60 Hz).

The synthetic dummy has no mains hum, so this changes little there; it matters
for the real BioRadio signal. Enable/tune via SignalConfig (settings window).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, sosfilt_zi, tf2sos


class EMGFilter:
    def __init__(self, cfg):
        s = cfg.signal
        self.enabled = bool(s.filter_enabled)
        self.sos = None
        self.zi = None
        if not self.enabled:
            return

        sr = float(s.sample_rate)
        nyq = sr / 2.0
        hi = min(float(s.bp_high), 0.95 * nyq)
        lo = max(1.0, min(float(s.bp_low), hi - 1.0))

        sos_bp = butter(int(s.bp_order), [lo, hi], btype="band", fs=sr, output="sos")
        b, a = iirnotch(float(s.notch_freq), float(s.notch_q), fs=sr)
        sos_notch = tf2sos(b, a)
        self.sos = np.vstack([sos_bp, sos_notch])

        z = sosfilt_zi(self.sos)
        self.zi = [np.zeros_like(z), np.zeros_like(z)]  # per channel, start at rest

    def process(self, raw: np.ndarray) -> np.ndarray:
        """Filter raw ``(k, 2)`` → filtered ``(k, 2)`` (identity if disabled)."""
        if not self.enabled or self.sos is None or raw.size == 0:
            return raw
        out = np.empty_like(raw)
        for ch in range(2):
            out[:, ch], self.zi[ch] = sosfilt(self.sos, raw[:, ch], zi=self.zi[ch])
        return out
