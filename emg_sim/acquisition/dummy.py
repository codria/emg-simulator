"""Synthetic EMG source for development, demo and attract mode.

Each channel has a *drive* in [0, 1]. Raw EMG is generated as a noise floor plus
drive-scaled broadband noise, so its RMS tracks the drive and the raw waveform
looks EMG-ish on screen. Drive is set externally (keyboard / slider = manual
mode) or by an internal sweep (auto mode, used for attract / demo).

This means the dummy exercises the *full* DSP + normalization path (baseline,
soft-sat, adaptation), not just a shortcut [0,1] signal — so that pipeline gets
developed and demoed for real before the BioRadio arrives.
"""

from __future__ import annotations

import math

import numpy as np

from .source import InputSource

# EMG-realistic amplitudes in MILLIVOLTS — the app's amplitude unit (the real
# BioRadio read() converts its volts to mV), so dummy and device share one scale.
_BASE_AMP = 0.05   # rest noise floor (per-sample std ~0.05 mV)
_BURST_AMP = 1.5   # full-drive burst std (~1.5 mV, a strong contraction)


class DummySource(InputSource):
    def __init__(self, cfg, mode: str = "manual", seed: int = 0):
        self.sample_rate = int(cfg.signal.sample_rate)
        self.mode = mode                       # "manual" | "auto"
        self._drive = np.zeros(2)              # [left, right] in [0,1]
        self._t = 0.0
        self._carry = 0.0                      # fractional-sample accumulator
        self._rng = np.random.default_rng(seed)

    # -- manual control (keyboard / slider) --------------------------------
    def set_drive(self, left: float, right: float) -> None:
        self._drive[0] = float(np.clip(left, 0.0, 1.0))
        self._drive[1] = float(np.clip(right, 0.0, 1.0))

    @property
    def drive(self) -> np.ndarray:
        return self._drive.copy()

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    # -- auto sweep (attract / demo) ---------------------------------------
    def _auto_drive(self, t: float) -> tuple[float, float]:
        left = 0.5 + 0.45 * math.sin(2 * math.pi * 0.05 * t)
        right = 0.5 + 0.35 * math.sin(2 * math.pi * 0.037 * t + 1.0)
        return left, right

    # -- InputSource -------------------------------------------------------
    def read(self, dt: float) -> np.ndarray:
        if dt <= 0:
            return np.empty((0, 2))
        exact = dt * self.sample_rate + self._carry
        n = int(exact)
        self._carry = exact - n
        self._t += dt
        if self.mode == "auto":
            self.set_drive(*self._auto_drive(self._t))
        if n <= 0:
            return np.empty((0, 2))

        out = np.empty((n, 2))
        for ch in range(2):
            d = self._drive[ch]
            floor = self._rng.normal(0.0, _BASE_AMP, n)
            burst = self._rng.normal(0.0, d * _BURST_AMP, n)
            out[:, ch] = floor + burst
        return out
