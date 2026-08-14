#!/usr/bin/env python
"""Verify the numpy IK/FK port against the C++ reference.

Loads ``tools/cpp_ref/ref_cases.json`` (produced by build_and_dump.sh from the
unmodified C++ arm.cpp) and re-runs every case through the numpy port in
``emg_sim.kinematics.arm``, reporting the maximum absolute differences.

FK is deterministic and must match near bit-exactly (float32 C++ vs float64
numpy → ~1e-6). IK is an iterative solver; for the fixed cases the final joint
angles match the reference to a small tolerance.

Run:  python tools/verify_ik_vs_cpp.py
Exit code 0 = all within tolerance, 1 = a case exceeded tolerance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emg_sim.kinematics.arm import IKOptions, make_standard_arm  # noqa: E402

REF = ROOT / "tools" / "cpp_ref" / "ref_cases.json"

# Tolerances
FK_ATOL = 1e-5      # deterministic geometry: float32/float64 rounding only
IK_TIP_ATOL = 5e-4  # both solvers drive the tip to the same place
IK_Q_ATOL = 5e-3    # final joint angles (rad) after fixed iteration budget


def _fmt(x: float) -> str:
    return f"{x:.2e}"


def main() -> int:
    data = json.loads(REF.read_text())

    fk_max = 0.0
    ik_q_max = 0.0
    ik_tip_max = 0.0
    failures: list[str] = []

    print("== FK cases ==")
    for i, case in enumerate(data["fk_cases"]):
        m = make_standard_arm()
        m.set_q(case["q"])
        Ts = m.forward_kinematics()
        origins = np.array([T[:3, 3] for T in Ts])
        ref_origins = np.array(case["frame_origins"])
        tip = m.tip_position()
        ref_tip = np.array(case["tip"])

        d_org = float(np.max(np.abs(origins - ref_origins)))
        d_tip = float(np.max(np.abs(tip - ref_tip)))
        d = max(d_org, d_tip)
        fk_max = max(fk_max, d)
        ok = d <= FK_ATOL
        if not ok:
            failures.append(f"FK case {i}: max diff {_fmt(d)} > {_fmt(FK_ATOL)}")
        print(f"  case {i}: origins {_fmt(d_org)}  tip {_fmt(d_tip)}  {'OK' if ok else 'FAIL'}")

    print("== IK cases ==")
    for i, case in enumerate(data["ik_cases"]):
        m = make_standard_arm()
        m.set_q(case["q0"])
        opts = IKOptions(**case["opts"])
        conv = m.solve_ik(case["target"], opts)
        q = np.asarray(m.q)
        ref_q = np.array(case["q_final"])
        tip = m.tip_position()
        ref_tip = np.array(case["tip_final"])

        d_q = float(np.max(np.abs(q - ref_q)))
        d_tip = float(np.max(np.abs(tip - ref_tip)))
        ik_q_max = max(ik_q_max, d_q)
        ik_tip_max = max(ik_tip_max, d_tip)
        conv_ok = conv == case["converged"]
        ok = d_q <= IK_Q_ATOL and d_tip <= IK_TIP_ATOL
        if not ok:
            failures.append(
                f"IK case {i}: dq {_fmt(d_q)} (tol {_fmt(IK_Q_ATOL)}), "
                f"dtip {_fmt(d_tip)} (tol {_fmt(IK_TIP_ATOL)})"
            )
        print(
            f"  case {i}: dq {_fmt(d_q)}  dtip {_fmt(d_tip)}  "
            f"conv py={conv} cpp={case['converged']}"
            f"{'' if conv_ok else ' (conv mismatch)'}  {'OK' if ok else 'FAIL'}"
        )

    print("\n== summary ==")
    print(f"  FK  max abs diff : {_fmt(fk_max)}  (tol {_fmt(FK_ATOL)})")
    print(f"  IK  max |dq|     : {_fmt(ik_q_max)}  (tol {_fmt(IK_Q_ATOL)})")
    print(f"  IK  max |dtip|   : {_fmt(ik_tip_max)}  (tol {_fmt(IK_TIP_ATOL)})")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1
    print("\nALL WITHIN TOLERANCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
