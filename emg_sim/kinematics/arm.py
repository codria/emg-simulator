"""6-DOF manipulator kinematics.

numpy port of ``KinectArmSimulator/src/window3/arm.cpp`` (which was itself
ported from the Three.js reference ``arm_threejs_v21.html``).

This is a *faithful* port of the C++/GLM implementation. The GLM matrix
conventions are replicated exactly so that the numeric output matches the C++
reference (verified by ``tools/verify_ik_vs_cpp.py`` against a standalone build
of ``arm.cpp``):

* Homogeneous 4x4 transforms, column-vector convention ``v' = M @ v``.
* GLM stores column-major, but the *math* is standard; here we use ordinary
  row-major numpy arrays with ``M @ v``. The index translations are:
    - ``glm  Ts[k][3]``      (4th column = translation) -> ``Ts[k][:3, 3]``
    - ``glm::mat3(Ts[k])``   (rotation part)            -> ``Ts[k][:3, :3]``
    - ``glm  R * v``         (mat3 * vec3)              -> ``R @ v``
* The frame chain is built by post-multiplication:
  ``T = T @ Trans(offset) @ Rot(q, axis)``.
* ``forward_kinematics()`` returns ``num_joints() + 1`` transforms;
  ``Ts[0]`` is identity and ``Ts[i+1]`` is the world transform of joint frame
  ``i`` (i.e. *after* applying joint ``i``'s offset + rotation).

The C++ uses 32-bit ``float`` throughout; this port uses float64 (strictly
better conditioning for the exhibit). Geometry therefore matches the reference
to ~1e-6 rather than bit-exactly. The damped-least-squares IK is an iterative
solver, so its final joint angles match the reference to a small tolerance for
well-conditioned targets (see the verification harness for the exact bounds).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

# Match the literal used in arm.cpp (3.14159265f), not math.pi. The difference
# (~4e-9) is irrelevant numerically but keeps joint-limit / angle-wrap constants
# identical to the reference.
PI = 3.14159265
TWO_PI = 6.28318530

# J6 frame: flange far face at joint_w/2 + 0.006 (translate) + 0.006 (half-len).
# arm.cpp: static const glm::vec3 kTipOffsetLocal(0, 0, 0.017)
TIP_OFFSET_LOCAL = np.array([0.0, 0.0, 0.017])


class Axis(Enum):
    X = 0
    Y = 1
    Z = 2


_AXIS_VEC = {
    Axis.X: np.array([1.0, 0.0, 0.0]),
    Axis.Y: np.array([0.0, 1.0, 0.0]),
    Axis.Z: np.array([0.0, 0.0, 1.0]),
}


def _translation(v: np.ndarray) -> np.ndarray:
    """Homogeneous translation matrix; equals ``glm::translate(I, v)``."""
    T = np.eye(4)
    T[:3, 3] = v
    return T


def _rotation(angle: float, axis_vec: np.ndarray) -> np.ndarray:
    """Homogeneous rotation matrix matching ``glm::rotate(I, angle, axis)``.

    Standard right-handed Rodrigues rotation. ``axis_vec`` is assumed unit
    length (GLM normalizes internally; our axes are exact basis vectors).
    """
    x, y, z = axis_vec
    c = np.cos(angle)
    s = np.sin(angle)
    t = 1.0 - c
    return np.array(
        [
            [t * x * x + c,     t * x * y - s * z, t * x * z + s * y, 0.0],
            [t * x * y + s * z, t * y * y + c,     t * y * z - s * x, 0.0],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c,     0.0],
            [0.0,               0.0,               0.0,               1.0],
        ]
    )


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


@dataclass
class Joint:
    """One revolute joint: rotation ``axis`` at a local ``offset`` from the
    previous frame, with angle limits ``[qmin, qmax]`` (radians)."""

    axis: Axis
    offset: np.ndarray
    qmin: float = -PI
    qmax: float = PI


@dataclass
class ArmDimensions:
    """Arm link/tube dimensions (metres). Matches ``ArmDimensions`` in arm.h,
    which mirrors the ``arm_threejs_v21.html`` constants."""

    A: float = 0.060
    joint_w: float = 0.010
    joint_d: float = 0.054       # A * 0.9
    joint_d_j1: float = 0.046
    joint_d_j4: float = 0.046
    tube_d: float = 0.060        # A
    big_tube_d: float = 0.066    # A * 1.1
    bone_d: float = 0.060        # A
    upper_arm_len: float = 0.30
    forearm_len: float = 0.30
    t_base_len: float = 0.030    # base tube below J1 (-Z side)
    t2_len: float = 0.04
    t3_len: float = 0.060
    t4_len: float = 0.060
    t5_len: float = 0.060
    t6_len: float = 0.060
    t7_len: float = 0.05
    t8_len: float = 0.060
    t9_len: float = 0.060
    t10_len: float = 0.05


DEFAULT_DIMS = ArmDimensions()


@dataclass
class IKOptions:
    """Damped-least-squares IK options. Mirrors ``Manipulator::IKOptions`` in
    arm.h field-for-field (``lambda`` -> ``lambda_`` since ``lambda`` is a
    Python keyword)."""

    max_iter: int = 30
    tol: float = 1e-3
    lambda_: float = 0.08
    elbow_up: bool = True
    elbow_target: float = 1.5
    elbow_gain: float = 0.3
    max_step: float = 0.08
    # Adaptive damping: lambda boosted toward lambda_max when det(JJ^T) < det_thresh
    lambda_max: float = 0.50
    det_thresh: float = 1e-3
    # Per-iteration joint-angle clamp (rad). 0 = disabled.
    dq_max: float = 0.30
    # J4 forearm-roll: prefer local-Y toward arm-space +Y (shoulder protrusion dir)
    j4_down: bool = False
    j4_down_gain: float = 0.20
    # J5 wrist-pitch: prefer local-X toward arm-space +Y
    j5_down: bool = False
    j5_down_gain: float = 0.20
    # J1 yaw: drive toward target azimuth to resolve the Z-axis singularity
    j1_preferred: bool = False
    j1_preferred_gain: float = 0.10
    j1_target: float = 0.0


def _wrap_pi(diff: float) -> float:
    """Wrap an angle difference into (-pi, pi], matching the ±3.14159265
    branch used throughout arm.cpp."""
    if diff > PI:
        diff -= TWO_PI
    if diff < -PI:
        diff += TWO_PI
    return diff


def _inv3(M: np.ndarray):
    """3x3 inverse via adjugate/determinant, mirroring ``invert3x3`` in
    arm.cpp (returns ``None`` when ``|det| < 1e-12``). For the symmetric,
    damped matrix ``JJ^T + lambda^2 I`` this agrees with ``np.linalg.inv`` to
    machine precision while preserving the reference's singular-matrix guard."""
    det = (
        M[0, 0] * (M[1, 1] * M[2, 2] - M[1, 2] * M[2, 1])
        - M[0, 1] * (M[1, 0] * M[2, 2] - M[1, 2] * M[2, 0])
        + M[0, 2] * (M[1, 0] * M[2, 1] - M[1, 1] * M[2, 0])
    )
    if abs(det) < 1e-12:
        return None
    idet = 1.0 / det
    inv = np.empty((3, 3))
    inv[0, 0] = (M[1, 1] * M[2, 2] - M[1, 2] * M[2, 1]) * idet
    inv[0, 1] = -(M[0, 1] * M[2, 2] - M[0, 2] * M[2, 1]) * idet
    inv[0, 2] = (M[0, 1] * M[1, 2] - M[0, 2] * M[1, 1]) * idet
    inv[1, 0] = -(M[1, 0] * M[2, 2] - M[1, 2] * M[2, 0]) * idet
    inv[1, 1] = (M[0, 0] * M[2, 2] - M[0, 2] * M[2, 0]) * idet
    inv[1, 2] = -(M[0, 0] * M[1, 2] - M[0, 2] * M[1, 0]) * idet
    inv[2, 0] = (M[1, 0] * M[2, 1] - M[1, 1] * M[2, 0]) * idet
    inv[2, 1] = -(M[0, 0] * M[2, 1] - M[0, 1] * M[2, 0]) * idet
    inv[2, 2] = (M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]) * idet
    return inv


class Manipulator:
    """6-DOF serial manipulator. Port of ``arm::Manipulator``."""

    def __init__(self, joints: list[Joint] | None = None):
        self.joints: list[Joint] = list(joints) if joints else []
        self.q = np.zeros(len(self.joints))

    # -- introspection -----------------------------------------------------
    def num_joints(self) -> int:
        return len(self.joints)

    @property
    def _qmin(self) -> np.ndarray:
        return np.array([j.qmin for j in self.joints])

    @property
    def _qmax(self) -> np.ndarray:
        return np.array([j.qmax for j in self.joints])

    # -- state -------------------------------------------------------------
    def set_q(self, q) -> None:
        """Set all joint angles, resizing (pad with 0) and clamping to limits.
        Mirrors ``Manipulator::setQ(vector)``."""
        n = len(self.joints)
        q = np.asarray(q, dtype=float).ravel()
        if len(q) < n:
            q = np.concatenate([q, np.zeros(n - len(q))])
        else:
            q = q[:n].copy()
        self.q = np.clip(q, self._qmin, self._qmax)

    def set_q_i(self, i: int, val: float) -> None:
        if i < 0 or i >= len(self.q):
            return
        self.q[i] = _clamp(val, self.joints[i].qmin, self.joints[i].qmax)

    # -- kinematics --------------------------------------------------------
    def forward_kinematics(self) -> list[np.ndarray]:
        """World transform of every joint frame. Length ``num_joints() + 1``;
        ``Ts[0]`` identity, ``Ts[i+1]`` frame after joint ``i``."""
        Ts = [np.eye(4)]
        T = np.eye(4)
        for i, j in enumerate(self.joints):
            T = T @ _translation(j.offset)
            T = T @ _rotation(self.q[i], _AXIS_VEC[j.axis])
            Ts.append(T)
        return Ts

    def tip_position(self) -> np.ndarray:
        Ts = self.forward_kinematics()
        tip = Ts[-1] @ np.array([*TIP_OFFSET_LOCAL, 1.0])
        return tip[:3]

    def _world_axis(self, i: int, Ts: list[np.ndarray]) -> np.ndarray:
        R = Ts[i + 1][:3, :3]
        v = R @ _AXIS_VEC[self.joints[i].axis]
        return v / np.linalg.norm(v)

    def solve_ik(self, target, opts: IKOptions | None = None) -> bool:
        """Damped-least-squares (Levenberg–Marquardt) Jacobian IK with
        null-space secondary tasks. Port of ``Manipulator::solveIK``.

        Mutates ``self.q`` in place; returns ``True`` if the tip reached
        ``target`` within ``opts.tol``, else ``False`` after ``max_iter``.
        """
        if opts is None:
            opts = IKOptions()
        target = np.asarray(target, dtype=float)
        n = len(self.joints)
        if len(self.q) != n:
            self.q = np.zeros(n)

        qmin, qmax = self._qmin, self._qmax

        for _ in range(opts.max_iter):
            Ts = self.forward_kinematics()
            tip = (Ts[-1] @ np.array([*TIP_OFFSET_LOCAL, 1.0]))[:3]

            e = target - tip
            if float(e @ e) < opts.tol * opts.tol:
                return True

            elen = np.linalg.norm(e)
            if elen > opts.max_step:
                e = e * (opts.max_step / elen)

            # Geometric Jacobian columns: J_i = z_i x (tip - p_i)
            J = np.zeros((3, n))
            for i in range(n):
                z_i = self._world_axis(i, Ts)
                p_i = Ts[i + 1][:3, 3]
                J[:, i] = np.cross(z_i, tip - p_i)

            A = J @ J.T  # symmetric 3x3 = JJ^T

            det = (
                A[0, 0] * (A[1, 1] * A[2, 2] - A[1, 2] * A[2, 1])
                - A[0, 1] * (A[1, 0] * A[2, 2] - A[1, 2] * A[2, 0])
                + A[0, 2] * (A[1, 0] * A[2, 1] - A[1, 1] * A[2, 0])
            )
            lam = opts.lambda_
            if opts.det_thresh > 0.0 and det < opts.det_thresh:
                t = max(det / opts.det_thresh, 0.0)
                lam += opts.lambda_max * (1.0 - t)
            A = A + (lam * lam) * np.eye(3)

            inv = _inv3(A)
            if inv is None:
                return False

            tmp = inv @ e
            dq = J.T @ tmp  # dq[i] = J_cols[i] . tmp

            # Secondary tasks combined into one vector, projected once through
            # the null space. Gain ratios encode priority.
            dq_sec = np.zeros(n)

            # J1 yaw -> target azimuth (resolves Z-axis singularity)
            if opts.j1_preferred and n >= 1:
                dq_sec[0] += opts.j1_preferred_gain * _wrap_pi(opts.j1_target - self.q[0])

            # J3 elbow -> elbow_target (highest-priority secondary)
            if opts.elbow_up and n >= 3:
                dq_sec[2] += opts.elbow_gain * (opts.elbow_target - self.q[2])

            # J4 forearm-roll: local-Y toward arm-space +Y
            if opts.j4_down and n >= 4:
                Rp = Ts[4][:3, :3]
                d = Rp.T @ np.array([0.0, 1.0, 0.0])
                diff = _wrap_pi(float(np.arctan2(-d[0], d[1])) - self.q[3])
                dq_sec[3] += opts.j4_down_gain * diff

            # J5 wrist-pitch -> 0
            if opts.j5_down and n >= 5:
                dq_sec[4] += opts.j5_down_gain * (-self.q[4])

            tmp1 = J @ dq_sec           # sum_i J_cols[i] * dq_sec[i]
            tmp2 = inv @ tmp1
            dq = dq + (dq_sec - J.T @ tmp2)

            if opts.dq_max > 0.0:
                dq = np.clip(dq, -opts.dq_max, opts.dq_max)

            self.q = np.clip(self.q + dq, qmin, qmax)

        return False

    def compute_max_reach(self) -> float:
        """Probe maximum reachable distance (for r_max normalization). Port of
        ``Manipulator::computeMaxReach``."""
        n = len(self.joints)
        if n == 0:
            return 1.0

        dirs = [
            np.array([0.0, 0.0, 1.0]),
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, -1.0, 0.0]),
            np.array([1.0, 0.0, 1.0]) / np.sqrt(2.0),
            np.array([0.0, -1.0, 1.0]) / np.sqrt(2.0),
            np.array([1.0, -1.0, 0.0]) / np.sqrt(2.0),
            np.array([0.0, 0.0, -1.0]),
        ]
        starts = [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, -1.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.5, -0.5, 0.0, 0.0, 0.0],
            [0.0, -1.5, 0.5, 0.0, 0.0, 0.0],
            [0.0, 1.5, 0.0, 0.0, 0.0, 0.0],
        ]
        starts = [np.array((s + [0.0] * n)[:n]) for s in starts]

        opts = IKOptions()
        opts.max_iter = 1
        opts.lambda_ = 0.02
        opts.elbow_up = False

        global_best = 0.0
        q_save = self.q.copy()

        for direction in dirs:
            for start in starts:
                self.q = start.copy()
                best = 0.0
                dist = 0.3
                for _ in range(50):
                    tgt = direction * dist
                    for _ in range(60):
                        self.solve_ik(tgt, opts)
                    reach = float(np.linalg.norm(self.tip_position()))
                    if reach > best + 1e-4:
                        best = reach
                        dist += 0.03
                    else:
                        break
                if best > global_best:
                    global_best = best
        self.q = q_save
        return global_best


def make_standard_arm(dims: ArmDimensions = DEFAULT_DIMS) -> Manipulator:
    """Build the 6-DOF C-shape arm. Port of ``arm::makeStandardArm``."""
    d = dims

    j2_y = -d.t3_len / 2.0 - d.joint_w / 2.0
    j2_z = d.joint_w / 2.0 + d.t2_len
    tube4_y = -d.joint_w / 2.0 - d.t4_len / 2.0
    j3_y = tube4_y + d.t5_len / 2.0 + d.joint_w / 2.0
    j3_global_y = j2_y + j3_y
    j4_y_local = -j3_global_y
    j4_z = d.t7_len + d.joint_w / 2.0
    j5_y = -d.A / 2.0 - d.joint_w / 2.0
    j5_z = d.joint_w / 2.0 + d.forearm_len
    j6_y_local = d.A / 2.0 + d.joint_w / 2.0
    j6_z = d.t10_len + d.joint_w / 2.0

    joints = [
        Joint(Axis.Z, np.array([0.0, 0.0, 0.0]), -4.0 * PI, 4.0 * PI),   # J1 base yaw
        Joint(Axis.Y, np.array([0.0, j2_y, j2_z])),                       # J2 shoulder pitch
        Joint(Axis.Y, np.array([0.0, j3_y, d.upper_arm_len]), 0.0, PI),   # J3 elbow (up only)
        Joint(Axis.Z, np.array([0.0, j4_y_local, j4_z])),                 # J4 forearm roll
        Joint(Axis.Y, np.array([0.0, j5_y, j5_z])),                       # J5 wrist pitch
        Joint(Axis.Z, np.array([0.0, j6_y_local, j6_z])),                 # J6 tool roll
    ]
    return Manipulator(joints)
