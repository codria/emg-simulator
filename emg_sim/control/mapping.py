"""Position control: normalized activation → polar (r, θ) → cartesian target → IK.

This is the "arm-side normalization" — it scales the [0,1] activation into the
arm's reachable workspace. Left arm → θ (azimuth), right arm → r (reach) by
default; `(r, θ)` are clamped to the reachable fan by construction so the IK
never receives an unreachable target (design §3).
"""

from __future__ import annotations

import numpy as np

from ..kinematics.arm import IKOptions, make_standard_arm


def polar_to_xyz(control_cfg, r: float, theta: float) -> np.ndarray:
    """Polar `(r, θ)` on the operation plane → cartesian target (z = z_plane)."""
    return np.array([r * np.cos(theta), r * np.sin(theta), control_cfg.z_plane])


class PolarController:
    def __init__(self, cfg):
        self.cfg = cfg.control
        self.arm = make_standard_arm()
        self.r = self.cfg.r_min
        self.theta = self.cfg.theta_min
        self.target = polar_to_xyz(self.cfg, self.r, self.theta)
        # settle the arm into the operation plane so it doesn't start pointing up
        for _ in range(60):
            self.arm.solve_ik(self.target, self._ik_opts())

    def _ik_opts(self) -> IKOptions:
        # adaptive elbow: fold when reaching near, straighten when reaching far,
        # interpolated by the current commanded r (uses the arm's full range).
        o = IKOptions()
        c = self.cfg
        span = max(1e-6, c.r_max - c.r_min)
        norm = min(1.0, max(0.0, (self.r - c.r_min) / span))
        o.elbow_target = c.elbow_target_near * (1.0 - norm) + c.elbow_target_far * norm
        o.elbow_gain = c.elbow_gain
        return o

    def _split(self, a_left: float, a_right: float) -> tuple[float, float]:
        """Return (a_r, a_theta) given (a_left, a_right) per cfg.left_axis."""
        if self.cfg.left_axis == "theta":
            return a_right, a_left      # left → θ, right → r
        return a_left, a_right          # left → r, right → θ

    def target_from_activation(self, a_left: float, a_right: float) -> tuple[float, float]:
        a_r, a_theta = self._split(a_left, a_right)
        full = max(1e-3, self.cfg.reach_full_activation)  # full effort → full range
        a_r = float(np.clip(a_r / full, 0.0, 1.0))
        a_theta = float(np.clip(a_theta / full, 0.0, 1.0))
        r = self.cfg.r_min + a_r * (self.cfg.r_max - self.cfg.r_min)
        theta = self.cfg.theta_min + a_theta * (self.cfg.theta_max - self.cfg.theta_min)
        return r, theta

    def update(self, a_left: float, a_right: float):
        """Advance one control step; returns (q, tip, target)."""
        self.r, self.theta = self.target_from_activation(a_left, a_right)
        self.target = polar_to_xyz(self.cfg, self.r, self.theta)
        self.arm.solve_ik(self.target, self._ik_opts())  # warm-started → smooth
        return self.arm.q.copy(), self.arm.tip_position(), self.target.copy()
