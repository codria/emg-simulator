"""Reaching game (§4): spawn target in the fan, dwell-based reach detection,
5-reach round with a time, endless loop otherwise."""

from __future__ import annotations

import numpy as np

from ..control.mapping import polar_to_xyz


class ReachingGame:
    def __init__(self, cfg, seed: int = 0):
        self.cfg = cfg.game
        self.ctrl = cfg.control
        self.rng = np.random.default_rng(seed)
        self.reached = 0
        self.round_time = 0.0
        self.last_round_time: float | None = None
        self.hold = 0.0
        self.target_rt = (self.ctrl.r_min, self.ctrl.theta_min)
        self.target_xyz = polar_to_xyz(self.ctrl, *self.target_rt)
        self.spawn()

    def _rand_rt(self) -> tuple[float, float]:
        # r via sqrt so targets are uniform over the annulus AREA, not over (r,θ)
        # (plain uniform-r clusters targets toward the inner edge).
        r0, r1 = self.ctrl.r_min, self.ctrl.r_max
        r = float(np.sqrt(self.rng.uniform(r0 * r0, r1 * r1)))
        th = float(self.rng.uniform(self.ctrl.theta_min, self.ctrl.theta_max))
        return r, th

    def spawn(self) -> None:
        """New target inside the fan, at least min_target_sep from the current one."""
        cur = self.target_xyz
        r, th, xyz = self.target_rt[0], self.target_rt[1], self.target_xyz
        for _ in range(50):
            r, th = self._rand_rt()
            xyz = polar_to_xyz(self.ctrl, r, th)
            if np.linalg.norm(xyz - cur) >= self.cfg.min_target_sep:
                break
        self.target_rt = (r, th)
        self.target_xyz = xyz
        self.hold = 0.0

    def update(self, tip, dt: float):
        """Advance the game; returns 'reached', 'round_complete', or None."""
        self.round_time += dt
        d = float(np.linalg.norm(np.asarray(tip) - self.target_xyz))
        event = None
        if d < self.cfg.reach_dist:
            self.hold += dt
            if self.hold >= self.cfg.hold_sec:
                self.reached += 1
                if self.reached >= self.cfg.targets_per_round:
                    self.last_round_time = self.round_time
                    event = "round_complete"
                    self._reset_round()
                else:
                    event = "reached"
                    self.spawn()
        else:
            self.hold = 0.0
        return event

    def _reset_round(self) -> None:
        self.reached = 0
        self.round_time = 0.0
        self.spawn()

    @property
    def hold_frac(self) -> float:
        if self.cfg.hold_sec <= 0:
            return 1.0
        return min(1.0, self.hold / self.cfg.hold_sec)
