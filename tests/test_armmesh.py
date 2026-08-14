"""Tests for the parametric arm geometry port (no GUI / display needed —
armmesh imports only numpy + kinematics)."""

from __future__ import annotations

import numpy as np

from emg_sim.ui import armmesh


def _valid_soup(v):
    return v.ndim == 2 and v.shape[1] == 3 and len(v) % 3 == 0 and np.isfinite(v).all()


def test_cylinder_within_radius():
    v = armmesh.cylinder_tris(0.05, 0.2, 24)
    assert _valid_soup(v)
    assert np.max(np.hypot(v[:, 0], v[:, 1])) <= 0.05 + 1e-6
    assert np.max(np.abs(v[:, 2])) <= 0.1 + 1e-6


def test_curved_bone_endpoints():
    p0, p3 = (0, 0, 0.0), (0, -0.05, 0.3)
    v = armmesh.curved_bone_tris(p0, (0, 0, 0.12), (0, -0.05, 0.18), p3, 0.03)
    assert _valid_soup(v)
    # the swept tube stays within `radius` of the Bézier endpoints' span
    assert v[:, 2].min() >= -1e-6
    assert v[:, 2].max() <= 0.3 + 0.03 + 1e-6


def test_build_parts_shape():
    parts = armmesh.build_parts()
    assert len(parts) >= 18
    parents = set()
    for p in parts:
        assert _valid_soup(p["verts"])
        assert p["xform"].shape == (4, 4)
        assert len(p["color"]) == 3
        assert 0 <= p["parent"] <= 5
        parents.add(p["parent"])
    assert parents == {0, 1, 2, 3, 4, 5}  # every joint has at least one part
