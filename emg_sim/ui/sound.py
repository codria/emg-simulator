"""One-shot sound effect with graceful fallback.

Uses QtMultimedia's low-latency QSoundEffect (WAV). Source priority:
  1. the configured asset WAV if present (the real 效果音ラボ sound — not committed,
     see docs/decisions.md: their terms forbid redistributing the files);
  2. else a synthesized fallback (`synth` kind) so a fresh clone still has sound;
  3. else a silent no-op, so the app always runs.
"""

from __future__ import annotations

from pathlib import Path


class Sfx:
    def __init__(self, path, volume: float = 0.7, synth: str | None = None):
        self._eff = None
        src = None
        if path and Path(path).exists():
            src = str(Path(path).resolve())        # the real (uncommitted) asset wins
        elif synth:
            from . import sfx_synth                 # fresh-clone fallback: synthesize it
            src = sfx_synth.ensure(synth)
        if src is None:
            return
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(src))
            eff.setVolume(float(volume))
            self._eff = eff
        except Exception:
            self._eff = None

    @property
    def available(self) -> bool:
        return self._eff is not None

    def play(self) -> None:
        if self._eff is not None:
            try:
                self._eff.play()
            except Exception:
                pass
