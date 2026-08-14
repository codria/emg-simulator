# emg-simulator

EMG-driven robot-arm reaching game for an open-campus exhibit. Two forearm EMG
channels drive a simulated 6-DOF robot arm in polar `(r, θ)` control: left arm →
reach `r`, right arm → azimuth `θ`. Full-Python implementation.

Design and rationale: [`docs/emg_robotarm_exhibit_design.md`](docs/emg_robotarm_exhibit_design.md).

## Status

| Layer (design §8) | Role | Status |
|---|---|---|
| acquisition | BioRadio .NET SDK via pythonnet (worker thread) | not started |
| signal_processing | band-pass / notch / rectify / RMS / normalize / soft-sat | not started |
| transform | L/R → `(r, θ)` → cartesian target | not started |
| **kinematics** | 6-DOF arm model + damped-least-squares IK | **done, verified vs C++** |
| rendering | PyQtGraph GL scene + EMG bars | not started |
| game | target spawn / reach detection / score | not started |

`kinematics` is ported from the C++ reference `KinectArmSimulator/src/window3/arm.cpp`
(itself a port of a Three.js implementation) and verified numerically against it
(see below).

## Setup

Uses the conda env `env_emg-simulator` (Python 3.13).

```bash
conda activate env_emg-simulator
pip install -r requirements.txt
```

The current milestone needs only `numpy` / `scipy` / `pytest`; rendering and
acquisition dependencies are commented out in `requirements.txt` until those
layers are built.

## Tests

```bash
pytest              # full suite (incl. the slow max-reach probe)
pytest -m "not slow"   # fast suite (~0.2 s)
```

Tests live in `tests/`. They cover the numpy kinematics port both by
self-consistency and by cross-checking every case against the committed C++
reference `tools/cpp_ref/ref_cases.json`.

## Verifying the kinematics port against C++

The port replicates the C++/GLM math exactly (see the module docstring in
[`emg_sim/kinematics/arm.py`](emg_sim/kinematics/arm.py)). To (re)generate the
reference truth file and check the port:

```bash
# 1. build the C++ dumper against the unmodified arm.cpp + GLM, emit ref_cases.json
bash tools/cpp_ref/build_and_dump.sh [path-to-KinectArmSimulator/KinectArmSimulator]

# 2. run the numpy port on the same cases and report max diffs
python tools/verify_ik_vs_cpp.py
```

Requires `g++` (mingw64) and the KinectArmSimulator repo only for step 1;
`ref_cases.json` is committed, so the pytest cross-check runs without a C++
toolchain. Observed agreement: FK ~1e-7, IK joint angles ~1e-7 (float32 C++ vs
float64 numpy rounding).

## Layout

```
emg_sim/                 # the Python package
  kinematics/arm.py      # arm model + IK (the only implemented layer)
tools/
  cpp_ref/               # C++ reference dumper + committed ref_cases.json
  verify_ik_vs_cpp.py    # numpy-vs-C++ diff report
tests/                   # pytest suite
docs/                    # design document
```
