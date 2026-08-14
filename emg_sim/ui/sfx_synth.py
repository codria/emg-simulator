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
    """Short subtle "tick" — a fast-decaying noise burst + faint ring (a "ツッ")."""
    dur = 0.032
    t = np.arange(int(_SR * dur)) / _SR
    env = np.exp(-t / 0.005)                      # ~5 ms decay → crisp tick
    rng = np.random.default_rng(42)               # fixed → identical every run
    sig = rng.standard_normal(t.size) * env       # noise body
    sig += 0.6 * np.sin(2 * np.pi * 2600.0 * t) * env   # faint tone so it's not pure hiss
    sig /= np.max(np.abs(sig)) + 1e-9
    return 0.28 * sig                             # kept quiet / understated


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
        if not p.exists():
            _write_wav(_BUILDERS[kind](), p)
        return str(p)
    except Exception:
        return None
