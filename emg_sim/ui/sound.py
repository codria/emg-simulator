"""One-shot sound effect with graceful fallback.

Playback is deliberately kept **off** Qt's multimedia stack. QSoundEffect /
QtMultimedia (FFmpeg backend) opens and *enumerates* the system audio devices
from the GUI thread's event loop; on Windows that can block the loop for
*seconds* — worst of all when a Bluetooth device (the BioRadio) is active, since
audio-endpoint enumeration stalls on the BT stack. That was the "app freezes for
tens of seconds after connecting the device" bug: the freeze wasn't in our tick
(step/sfx/render all measured ~0), it was Qt opening the audio device *between*
frames, right after `QSoundEffect.play()` returned.

On Windows we instead play the WAV with the lightweight native `winsound` — no
device enumeration, no FFmpeg — on a short-lived daemon thread, so even a slow
audio-device open can never touch the GUI thread. Elsewhere (dev machines, where
the stall doesn't occur) we fall back to QSoundEffect.

Source priority is unchanged:
  1. the configured asset WAV if present (the real 効果音ラボ sound — not committed,
     see docs/decisions.md: their terms forbid redistributing the files);
  2. else a synthesized fallback (`synth` kind) so a fresh clone still has sound;
  3. else a silent no-op, so the app always runs.

`volume` is honoured on the QSoundEffect (non-Windows) path; winsound has no
per-sound gain, so on Windows the level is baked into the WAV (the synth SFX are
already tuned low; a real asset plays at its file level).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

_IS_WIN = sys.platform.startswith("win")


def _resolve_src(path, synth: str | None) -> str | None:
    if path and Path(path).exists():
        return str(Path(path).resolve())         # the real (uncommitted) asset wins
    if synth:
        from . import sfx_synth                   # fresh-clone fallback: synthesize it
        return sfx_synth.ensure(synth)
    return None


class Sfx:
    def __init__(self, path, volume: float = 0.7, synth: str | None = None):
        self._wav = _resolve_src(path, synth)
        self._volume = float(volume)
        self._eff = None                          # QSoundEffect (non-Windows only), lazy
        if self._wav is not None and not _IS_WIN:
            self._init_qt()

    def _init_qt(self) -> None:
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(self._wav))
            eff.setVolume(self._volume)
            self._eff = eff
        except Exception:
            self._eff = None

    @property
    def available(self) -> bool:
        return self._wav is not None

    def play(self) -> None:
        if self._wav is None:
            return
        if _IS_WIN:
            # Fire on a daemon thread: winsound opens only the default device (no
            # enumeration), and off the GUI thread a slow open can't freeze the UI.
            threading.Thread(target=self._play_win, daemon=True).start()
        elif self._eff is not None:
            try:
                self._eff.play()
            except Exception:
                pass

    def _play_win(self) -> None:
        try:
            import winsound

            winsound.PlaySound(self._wav, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except Exception:
            pass
