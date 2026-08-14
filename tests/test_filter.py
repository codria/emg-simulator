"""Tests for the EMG front-end filter (band-pass + mains notch)."""

from __future__ import annotations

import numpy as np

from emg_sim.config import Config
from emg_sim.dsp.filter import EMGFilter


def _atten(freq, cfg=None):
    """Output/input RMS ratio for a steady sine at `freq` (after transient)."""
    cfg = cfg or Config()
    sr = cfg.signal.sample_rate
    t = np.arange(2 * sr) / sr
    x = np.sin(2 * np.pi * freq * t)
    y = EMGFilter(cfg).process(np.column_stack([x, x]))[:, 0]
    n0 = sr  # drop 1 s of filter transient
    return np.sqrt(np.mean(y[n0:] ** 2)) / np.sqrt(np.mean(x[n0:] ** 2))


def test_passband_100hz_passes():
    assert _atten(100) > 0.7


def test_lowband_5hz_attenuated():
    assert _atten(5) < 0.2


def test_mains_50hz_notched():
    assert _atten(50) < 0.2


def test_disabled_is_identity():
    cfg = Config()
    cfg.signal.filter_enabled = False
    x = np.random.default_rng(0).normal(size=(128, 2))
    assert np.allclose(EMGFilter(cfg).process(x), x)


def test_streaming_matches_batch():
    cfg = Config()
    x = np.random.default_rng(1).normal(size=(1000, 2))
    y_batch = EMGFilter(cfg).process(x)
    f = EMGFilter(cfg)
    chunks = [f.process(x[i:i + 17]) for i in range(0, 1000, 17)]
    y_stream = np.vstack(chunks)
    assert np.allclose(y_batch, y_stream, atol=1e-9)
