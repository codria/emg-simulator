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

_ACTIVE_THRESH = 0.15  # activation above this counts as "someone is flexing"


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
        self.idle_t = 0.0
        self.attract = False

        # per-sample history of the normalized activation (the value that actually
        # drives control/judging) for overlay on the waveform
        disp_n = max(1, int(round(self.cfg.signal.display_sec * self.cfg.signal.sample_rate)))
        self._act_hist = [deque([0.0] * disp_n, maxlen=disp_n) for _ in range(2)]

    # -- main loop ---------------------------------------------------------
    def step(self, dt: float):
        self.t += dt
        raw = self.source.read(dt)
        self.amp = self.dsp.process(raw)

        if self.norm.capturing:
            self.norm.feed_baseline(self.amp)
        self.activation = self.norm.normalize(self.amp)

        k = raw.shape[0] if raw.size else 0
        if k:
            self._act_hist[0].extend([float(self.activation[0])] * k)
            self._act_hist[1].extend([float(self.activation[1])] * k)

        self.q, self.tip, self.target = self.control.update(
            float(self.activation[0]), float(self.activation[1])
        )
        self.event = self.game.update(self.tip, dt)
        self._update_idle(dt)
        return self.event

    def _update_idle(self, dt: float) -> None:
        if self.attract:
            return  # leave attract only on real user input (notify_user_input)
        if float(np.max(self.activation)) > _ACTIVE_THRESH:
            self.idle_t = 0.0
        else:
            self.idle_t += dt
            if self.idle_t >= self.cfg.game.attract_idle_sec:
                self.set_attract(True)

    # -- attract mode ------------------------------------------------------
    def set_attract(self, on: bool) -> None:
        self.attract = on
        if isinstance(self.source, DummySource):
            self.source.set_mode("auto" if on else "manual")

    def notify_user_input(self) -> None:
        """Call on real user activity (keypress / slider / device signal)."""
        self.idle_t = 0.0
        if self.attract:
            self.set_attract(False)

    # -- calibration flow (係員キー押下) -----------------------------------
    def start_baseline(self) -> None:
        self.notify_user_input()
        self.norm.start_baseline()

    def finish_baseline(self) -> None:
        self.norm.finish_baseline()

    def reset_session(self) -> None:
        self.norm.reset_adaptation()
        self.game._reset_round()

    def rebuild_dsp(self) -> None:
        """Recreate the RMS pipeline after config changes (window/EMA)."""
        self.dsp = RMSPipeline(self.cfg)

    # -- views for the GUI -------------------------------------------------
    def waveform(self, ch: int) -> np.ndarray:
        return self.dsp.waveform(ch)

    def activation_history(self, ch: int) -> np.ndarray:
        return np.fromiter(self._act_hist[ch], float)
