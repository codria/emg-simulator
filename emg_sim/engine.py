"""Engine — headless orchestrator wiring the layers into a per-frame step.

    source.read(dt) → dsp (RMS/EMA) → normalize (activation) → control (IK, q)
                    → game (reach/score)

Qt-free so the whole simulation is unit-testable; the GUI just calls `step(dt)`
on a timer and reads the exposed state to render.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from .config import Config
from .acquisition import DummySource, InputSource
from .dsp import RMSPipeline, Normalizer
from .control import PolarController
from .game import ReachingGame


class Engine:
    def __init__(self, cfg: Config | None = None, source: InputSource | None = None,
                 seed: int | None = None):
        self.cfg = cfg or Config()
        self.source = source or DummySource(self.cfg, mode="manual", seed=seed)
        self.dsp = RMSPipeline(self.cfg)
        self.norm = Normalizer(self.cfg)
        self.control = PolarController(self.cfg)
        self.game = ReachingGame(self.cfg, seed=seed)

        self.amp = np.zeros(2)
        self.activation = np.zeros(2)
        self.q = self.control.arm.q.copy()
        self.tip = self.control.arm.tip_position()
        self.target = self.control.target.copy()
        self.event = None

        self.t = 0.0
        self.attract = False

        # per-sample history of the smoothed amplitude (amp = the envelope the
        # baseline/scale act on) for the waveform's amplitude-domain overlay
        disp_n = max(1, int(round(self.cfg.signal.display_sec * self.cfg.signal.sample_rate)))
        self._amp_hist = [deque([0.0] * disp_n, maxlen=disp_n) for _ in range(2)]

    # -- main loop ---------------------------------------------------------
    def step(self, dt: float):
        self.t += dt
        raw = self.source.read(dt)
        self.amp = self.dsp.process(raw)

        if self.norm.capturing:
            self.norm.feed_baseline(self.amp)
        self.activation = self.norm.normalize(self.amp, dt)

        k = raw.shape[0] if raw.size else 0
        if k:
            self._amp_hist[0].extend([float(self.amp[0])] * k)
            self._amp_hist[1].extend([float(self.amp[1])] * k)

        self.q, self.tip, self.target = self.control.update(
            float(self.activation[0]), float(self.activation[1])
        )
        self.event = self.game.update(self.tip, dt)
        return self.event

    # -- attract mode (demo) — entered only on demand (D key), never on idle -----
    def set_attract(self, on: bool) -> None:
        self.attract = on
        if isinstance(self.source, DummySource):
            self.source.set_mode("auto" if on else "manual")

    def notify_user_input(self) -> None:
        """Call on real user activity (keypress / slider / device signal)."""
        if self.attract:
            self.set_attract(False)

    def set_source(self, source) -> None:
        """Swap the input source at runtime. Starts the new source first; if that
        raises (bad DLL / no device), the current source is left running."""
        try:
            source.start()
        except Exception:
            try:
                source.stop()
            except Exception:
                pass
            raise
        old, self.source = self.source, source
        if old is not None and old is not source:
            try:
                old.stop()
            except Exception:
                pass
        self._adopt_source_rate()      # match the DSP to the new source's real rate

    # -- calibration flow (係員キー押下) -----------------------------------
    def start_baseline(self) -> None:
        self.notify_user_input()
        self.norm.start_baseline()

    def finish_baseline(self) -> None:
        self.norm.finish_baseline()

    def reset_session(self) -> None:
        self.norm.reset_adaptation()
        self.game._reset_round()

    def reset_pose(self) -> None:
        """Re-home the arm and re-solve IK — recover from a flipped (inverse-joint) pose."""
        self.control.reset_pose()
        self.q = self.control.arm.q.copy()
        self.tip = self.control.arm.tip_position()

    def rebuild_dsp(self) -> None:
        """Recreate the RMS pipeline after config changes (window/EMA)."""
        self.dsp = RMSPipeline(self.cfg)

    def start_source(self) -> None:
        """Start the current source, then adopt its actual sample rate."""
        self.source.start()
        self._adopt_source_rate()

    def _adopt_source_rate(self) -> None:
        """A real device may stream at a rate other than the config default (e.g. a
        BioRadio at 2000 Hz vs the 1000 Hz default). Adopt it so the DSP window,
        band-pass/notch Nyquist and the waveform buffer match the real stream
        instead of a stale assumption. No-op for the dummy source (already in sync)."""
        sr = getattr(self.source, "sample_rate", None)
        if sr and int(sr) != int(self.cfg.signal.sample_rate):
            self.cfg.signal.sample_rate = int(sr)
            self.rebuild_dsp()
            disp_n = max(1, int(round(self.cfg.signal.display_sec * self.cfg.signal.sample_rate)))
            self._amp_hist = [deque([0.0] * disp_n, maxlen=disp_n) for _ in range(2)]

    # -- views for the GUI -------------------------------------------------
    def waveform(self, ch: int) -> np.ndarray:
        return self.dsp.waveform(ch)

    def amp_history(self, ch: int) -> np.ndarray:
        return np.fromiter(self._amp_hist[ch], float)
