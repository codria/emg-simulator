"""One-shot sound effect with graceful fallback.

Uses QtMultimedia's low-latency QSoundEffect (WAV). If the file is missing or no
audio backend is available, it degrades to a silent no-op so the app still runs.
The bundled reach sound is not committed (效果音ラボ redistribution terms) — see
docs/decisions.md; drop a WAV at the configured path to enable it.
"""

from __future__ import annotations

from pathlib import Path


class Sfx:
    def __init__(self, path, volume: float = 0.7):
        self._eff = None
        if not path:
            return
        try:
            p = Path(path)
            if not p.exists():
                return
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(str(p.resolve())))
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
