"""Parametric arm geometry — numpy port of the C++ renderer (arm_render.cpp).

The C++ arm is built from procedurally generated parts (no mesh files, §9
resolved): straight tubes/hubs via `genCylinder`, the forearm via a cubic-Bézier
swept tube `genCurvedBone`, a flange, all parented to joint frames with fixed
local transforms. This ports the geometry generators and `build()`'s part list
so PyQtGraph can draw the same arm; each part becomes one GLMeshItem whose
transform is `Ts[parent+1] @ local_xform` every frame.

Geometry is emitted as triangle soup (Ntri*3, 3); the scene builds MeshData with
consecutive faces and flat shading, so per-vertex normals aren't needed.
"""

from __future__ import annotations

import numpy as np

from ..kinematics.arm import ArmDimensions, DEFAULT_DIMS, Axis

_TWO_PI = 6.2831853
_HALF_PI = 1.5707963

# part colors (match arm_render.cpp)
C_SHELL = (0.96, 0.96, 0.97)
C_HUB = (0.55, 0.55, 0.57)
C_FLANGE = (0.75, 0.78, 0.86)


# -- transforms (glm-compatible: standard M @ v, row-major) -----------------
def _T(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _Rx(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]])


def _Ry(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


# -- geometry generators (positions only; triangle soup) --------------------
def cylinder_tris(radius: float, length: float, seg: int = 48) -> np.ndarray:
    hl = length * 0.5
    tris = []
    for i in range(seg):
        a0 = i / seg * _TWO_PI
        a1 = (i + 1) / seg * _TWO_PI
        c0, s0, c1, s1 = np.cos(a0), np.sin(a0), np.cos(a1), np.sin(a1)
        p00 = [radius * c0, radius * s0, -hl]
        p01 = [radius * c1, radius * s1, -hl]
        p10 = [radius * c0, radius * s0, hl]
        p11 = [radius * c1, radius * s1, hl]
        ct, cb = [0, 0, hl], [0, 0, -hl]
        tris += [p00, p01, p11, p00, p11, p10, ct, p10, p11, cb, p01, p00]
    return np.array(tris, dtype=float)


def curved_bone_tris(p0, c1, c2, p3, radius, seg_along=48, seg_around=24) -> np.ndarray:
    p0, c1, c2, p3 = (np.asarray(v, float) for v in (p0, c1, c2, p3))

    def bez(t):
        u = 1 - t
        return u**3 * p0 + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t**3 * p3

    def tan(t):
        u = 1 - t
        return 3 * u * u * (c1 - p0) + 6 * u * t * (c2 - c1) + 3 * t * t * (p3 - c2)

    rings = np.zeros((seg_along + 1, seg_around, 3))
    prev_right = np.array([1.0, 0.0, 0.0])
    init = False
    for i in range(seg_along + 1):
        t = i / seg_along
        c = bez(t)
        tg = tan(t)
        tg = tg / np.linalg.norm(tg)
        if not init:
            up = np.array([0, 0, 1.0]) if abs(tg[2]) < 0.9 else np.array([1.0, 0, 0])
            right = np.cross(up, tg)
            init = True
        else:
            right = prev_right - tg * np.dot(prev_right, tg)
        right = right / np.linalg.norm(right)
        prev_right = right
        up2 = np.cross(tg, right)
        up2 = up2 / np.linalg.norm(up2)
        for k in range(seg_around):
            a = k / seg_around * _TWO_PI
            rings[i, k] = c + (np.cos(a) * right + np.sin(a) * up2) * radius

    tris = []
    for i in range(seg_along):
        for k in range(seg_around):
            kn = (k + 1) % seg_around
            a, b = rings[i, k], rings[i, kn]
            cc, dd = rings[i + 1, kn], rings[i + 1, k]
            tris += [a, b, cc, a, cc, dd]
    c_start = bez(0.0)
    for k in range(seg_around):
        kn = (k + 1) % seg_around
        tris += [c_start, rings[0, kn], rings[0, k]]
    c_end = bez(1.0)
    for k in range(seg_around):
        kn = (k + 1) % seg_around
        tris += [c_end, rings[seg_along, k], rings[seg_along, kn]]
    return np.array(tris, dtype=float)


# -- part list (port of Renderer::build) ------------------------------------
def build_parts(d: ArmDimensions = DEFAULT_DIMS) -> list[dict]:
    """Return parts as dicts: {parent, verts (N,3), xform (4,4), color}."""
    parts: list[dict] = []

    def add(parent, verts, xform, color):
        parts.append({"parent": parent, "verts": verts, "xform": xform, "color": color})

    def tube(parent, radius, length, xform):
        add(parent, cylinder_tris(radius, length), xform, C_SHELL)

    # hub drum at every joint
    axes = [Axis.Z, Axis.Y, Axis.Y, Axis.Z, Axis.Y, Axis.Z]
    for i, ax in enumerate(axes):
        hx = _Rx(-_HALF_PI) if ax == Axis.Y else np.eye(4)
        hub_r = (d.joint_d_j1 if i == 0 else d.joint_d_j4 if i == 3 else d.joint_d) / 2.0
        add(i, cylinder_tris(hub_r, d.joint_w, 64), hx, C_HUB)

    # base tube (-Z) and tube2 (+Z) on J1
    tube(0, d.tube_d / 2, d.t_base_len, _T(0, 0, -(d.joint_w / 2 + d.t_base_len / 2)))
    tube(0, d.tube_d / 2, d.t2_len, _T(0, 0, d.joint_w / 2 + d.t2_len / 2))
    z3 = d.joint_w / 2 + d.t2_len
    tube(0, d.big_tube_d / 2, d.t3_len, _T(0, 0, z3) @ _Rx(-_HALF_PI))

    # J2: tube4, upper-arm bone, tube5
    ty = -d.joint_w / 2 - d.t4_len / 2
    tube(1, d.big_tube_d / 2, d.t4_len, _T(0, ty, 0) @ _Rx(-_HALF_PI))
    add(1, cylinder_tris(d.bone_d / 2, d.upper_arm_len), _T(0, ty, d.upper_arm_len / 2), C_SHELL)
    tube(1, d.big_tube_d / 2, d.t5_len, _T(0, ty, d.upper_arm_len) @ _Rx(-_HALF_PI))

    # J3: tube6, tube7
    j2y = -d.t3_len / 2 - d.joint_w / 2
    t4y = -d.joint_w / 2 - d.t4_len / 2
    j3y = t4y + d.t5_len / 2 + d.joint_w / 2
    t6y = -(j2y + j3y)
    tube(2, d.big_tube_d / 2, d.t6_len, _T(0, t6y, 0) @ _Rx(-_HALF_PI))
    tube(2, d.tube_d / 2, d.t7_len, _T(0, t6y, d.t7_len / 2))

    # J4: curved forearm bone, tube8
    fey = -d.A / 2 - d.joint_w - d.bone_d / 2
    z0 = d.joint_w / 2
    bone = curved_bone_tris(
        (0, 0, z0),
        (0, 0, z0 + d.forearm_len * 0.40),
        (0, fey, z0 + d.forearm_len * 0.60),
        (0, fey, z0 + d.forearm_len),
        d.bone_d / 2,
    )
    add(3, bone, np.eye(4), C_SHELL)
    ftz = d.joint_w / 2 + d.forearm_len
    tube(3, d.big_tube_d / 2, d.t8_len, _T(0, fey, ftz) @ _Rx(-_HALF_PI))

    # J5: tube9, tube10
    t9y = d.A / 2 + d.joint_w / 2
    tube(4, d.big_tube_d / 2, d.t9_len, _T(0, t9y, 0) @ _Rx(-_HALF_PI))
    tube(4, d.tube_d / 2, d.t10_len, _T(0, t9y, d.t10_len / 2))

    # J6: flange
    add(5, cylinder_tris(0.024, 0.012, 32), _T(0, 0, d.joint_w / 2 + 0.006), C_FLANGE)
    return parts
