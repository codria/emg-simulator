"""Synthesize small UI sounds to WAV, so the app has working SFX on a fresh clone
without shipping the (uncommitted) 効果音ラボ material files — see docs/decisions.md,
their terms forbid redistributing the files. Used ONLY as a fallback when the
configured asset WAV is absent; if the real WAV is present it always wins.

Pure numpy + stdlib `wave` (no external deps). Written once to a temp cache and
loaded by QSoundEffect like any other WAV.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np

_SR = 44100


def _write_wav(samples: np.ndarray, path: Path) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SR)
        w.writeframes(pcm.tobytes())


def enter_click() -> np.ndarray:
    """Short bright "tick" (~24 ms), tuned to the real カーソル移動6 sound measured from
    its waveform: peak ≈ 0.24, spectral centroid ≈ 8 kHz, energy mostly 4–9 kHz, fast
    attack + ~8 ms decay. Two tonal peaks (≈4.4 k / 7.5 k) over band-limited noise
    reproduce its bimodal, high-passed character (measured 2–6 k ≈ 28 %, >6 k ≈ 65 %)."""
    dur = 0.034
    n = int(_SR * dur)
    t = np.arange(n) / _SR
    env = np.exp(-t / 0.008)                       # ~8 ms decay → ~24 ms audible
    rng = np.random.default_rng(42)                # fixed → identical every run
    sp = np.fft.rfft(rng.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1 / _SR)
    sp[(fr < 3500) | (fr > 9500)] = 0              # band-limit noise to the active band
    noise = np.fft.irfft(sp, n=n)
    noise /= np.max(np.abs(noise)) + 1e-9
    sig = 0.18 * noise
    sig += 0.55 * np.sin(2 * np.pi * 4450.0 * t)   # measured lower peak
    sig += 0.80 * np.sin(2 * np.pi * 7500.0 * t)   # measured upper energy (6–9 kHz)
    sig *= env
    sig /= np.max(np.abs(sig)) + 1e-9
    return 0.24 * sig                              # matched subtle level


def reach_chime() -> np.ndarray:
    """Two ascending tones — a small pleasant "success" confirmation."""
    parts = []
    for freq, dur in ((784.0, 0.10), (1175.0, 0.15)):   # G5 → D6 (a fifth up)
        t = np.arange(int(_SR * dur)) / _SR
        env = np.sin(np.pi * t / dur)             # smooth bell in/out
        parts.append(np.sin(2 * np.pi * freq * t) * env)
    sig = np.concatenate(parts)
    return 0.30 * sig


_BUILDERS = {"enter": enter_click, "reach": reach_chime}
_CACHE = Path(tempfile.gettempdir()) / "emg_sim_sfx"


def ensure(kind: str) -> str | None:
    """Return a path to a synthesized WAV for `kind`, generating it on first use.
    Returns None on any failure (caller degrades to silence)."""
    if kind not in _BUILDERS:
        return None
    try:
        _CACHE.mkdir(parents=True, exist_ok=True)
        p = _CACHE / f"{kind}.wav"
        _write_wav(_BUILDERS[kind](), p)          # regenerate each run: cheap, never stale
        return str(p)
    except Exception:
        return None
