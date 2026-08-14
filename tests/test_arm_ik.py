"""Tests for the numpy arm kinematics port.

Two layers:
  * cross-check against the C++ reference (tools/cpp_ref/ref_cases.json)
  * self-consistency checks that need no reference file
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from emg_sim.kinematics.arm import (
    IKOptions,
    Manipulator,
    make_standard_arm,
)

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "tools" / "cpp_ref" / "ref_cases.json"
_ref = json.loads(REF.read_text()) if REF.exists() else None

# Tolerances vs C++ reference. Observed margins are ~1e-7 (float32 C++ vs
# float64 numpy); these leave 1000x+ headroom while still catching any real
# porting regression (which would be O(0.1+)).
FK_ATOL = 1e-5
IK_Q_ATOL = 1e-3
IK_TIP_ATOL = 1e-4

_fk_ids = list(range(len(_ref["fk_cases"]))) if _ref else []
_ik_ids = list(range(len(_ref["ik_cases"]))) if _ref else []


# --------------------------------------------------------------------------
#  Cross-check vs the C++ reference
# --------------------------------------------------------------------------
@pytest.mark.skipif(_ref is None, reason="ref_cases.json not generated (run tools/cpp_ref/build_and_dump.sh)")
@pytest.mark.parametrize("i", _fk_ids)
def test_fk_matches_cpp(i):
    case = _ref["fk_cases"][i]
    m = make_standard_arm()
    m.set_q(case["q"])
    origins = np.array([T[:3, 3] for T in m.forward_kinematics()])
    np.testing.assert_allclose(origins, case["frame_origins"], atol=FK_ATOL)
    np.testing.assert_allclose(m.tip_position(), case["tip"], atol=FK_ATOL)


@pytest.mark.skipif(_ref is None, reason="ref_cases.json not generated (run tools/cpp_ref/build_and_dump.sh)")
@pytest.mark.parametrize("i", _ik_ids)
def test_ik_matches_cpp(i):
    case = _ref["ik_cases"][i]
    m = make_standard_arm()
    m.set_q(case["q0"])
    conv = m.solve_ik(case["target"], IKOptions(**case["opts"]))
    np.testing.assert_allclose(m.q, case["q_final"], atol=IK_Q_ATOL)
    np.testing.assert_allclose(m.tip_position(), case["tip_final"], atol=IK_TIP_ATOL)
    assert conv == case["converged"]


# --------------------------------------------------------------------------
#  Self-consistency (no reference file needed)
# --------------------------------------------------------------------------
def test_fk_zero_pose_points_up():
    m = make_standard_arm()
    m.set_q([0, 0, 0, 0, 0, 0])
    tip = m.tip_position()
    # arm folded to zero points straight up +Z; x=y=0, tip z ~= 0.777 m
    assert abs(tip[0]) < 1e-9
    assert abs(tip[1]) < 1e-9
    assert tip[2] == pytest.approx(0.777, abs=1e-3)


def test_forward_kinematics_length():
    m = make_standard_arm()
    Ts = m.forward_kinematics()
    assert len(Ts) == m.num_joints() + 1
    assert np.allclose(Ts[0], np.eye(4))


def test_ik_reaches_reachable_target():
    m = make_standard_arm()
    target = np.array([0.0, 0.3, 0.5])
    reached = False
    for _ in range(20):  # up to 600 iters of the 30-iter solver
        if m.solve_ik(target):
            reached = True
            break
    assert reached
    assert np.linalg.norm(m.tip_position() - target) < 1e-3


def test_joint_limits_respected():
    m = make_standard_arm()
    for _ in range(10):
        m.solve_ik([0.3, -0.1, 0.35])
    q = m.q
    for i, j in enumerate(m.joints):
        assert j.qmin - 1e-9 <= q[i] <= j.qmax + 1e-9
    # J3 (elbow) is limited to [0, pi]
    assert 0.0 <= q[2] <= np.pi + 1e-9


def test_solve_ik_is_deterministic():
    a = make_standard_arm()
    a.set_q([0, 0, 0, 0, 0, 0])
    a.solve_ik([0.2, 0.1, 0.5])
    b = make_standard_arm()
    b.set_q([0, 0, 0, 0, 0, 0])
    b.solve_ik([0.2, 0.1, 0.5])
    np.testing.assert_array_equal(a.q, b.q)


def test_set_q_pads_and_clamps():
    m = make_standard_arm()
    # short vector pads with zeros
    m.set_q([0.1, 0.2])
    assert len(m.q) == 6
    assert m.q[2] == 0.0
    # J3 clamps below 0
    m.set_q([0, 0, -5.0, 0, 0, 0])
    assert m.q[2] == 0.0
    # J3 clamps above pi
    m.set_q([0, 0, 5.0, 0, 0, 0])
    assert m.q[2] == pytest.approx(np.pi, abs=1e-6)


def test_ikoptions_defaults_match_cpp():
    o = IKOptions()
    assert o.max_iter == 30
    assert o.lambda_ == pytest.approx(0.08)
    assert o.elbow_up is True
    assert o.elbow_target == pytest.approx(1.5)
    assert o.max_step == pytest.approx(0.08)


@pytest.mark.slow
def test_compute_max_reach_sane():
    m = make_standard_arm()
    reach = m.compute_max_reach()
    # arm spans ~0.6 m of links; max reach is a bit over the folded height
    assert 0.6 < reach < 1.0
