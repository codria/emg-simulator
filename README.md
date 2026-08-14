# emg-simulator

EMG-driven robot-arm reaching game for an open-campus exhibit. Two forearm EMG
channels drive a simulated 6-DOF robot arm in polar `(r, θ)` control: left arm →
reach `r`, right arm → azimuth `θ`. Full-Python implementation.

Design and rationale: [`docs/emg_robotarm_exhibit_design.md`](docs/emg_robotarm_exhibit_design.md).

## Status

| Layer (design §8) | Role | Status |
|---|---|---|
| acquisition | input-source abstraction + dummy (kbd/slider/auto); BioRadio later | **MVP** (dummy) |
| signal_processing | rectify / RMS / EMA (+ normalize §5); band-pass/notch later | **MVP** |
| transform | activation → `(r, θ)` → cartesian target (position control) | **MVP** |
| **kinematics** | 6-DOF arm model + damped-least-squares IK | **done, verified vs C++** |
| rendering | PyQtGraph GL scene + EMG bars + waveforms | **MVP** |
| game | target spawn / dwell reach detection / 5-reach score / attract | **MVP** |

A full end-to-end **MVP vertical slice** runs on the dummy input source (no
hardware): dummy EMG → RMS/normalize → position-control mapping → IK →
3D scene + bars + waveforms + reaching game. Remaining for the real exhibit:
the BioRadio acquisition (pythonnet) and band-pass/notch filtering.

`kinematics` is ported from the C++ reference `KinectArmSimulator/src/window3/arm.cpp`
(itself a port of a Three.js implementation) and verified numerically against it
(see below). Decisions are logged in [`docs/decisions.md`](docs/decisions.md).

## Setup

Uses the conda env `env_emg-simulator` (Python 3.13).

```bash
conda activate env_emg-simulator
pip install -r requirements.txt
```

The MVP needs `numpy` / `scipy` / `pytest` plus the rendering stack
(`PySide6` / `pyqtgraph` / `PyOpenGL`). The BioRadio acquisition dependency
(`pythonnet`) is deferred.

## Run the app (MVP)

```bash
python -m emg_sim.app            # interactive
python -m emg_sim.app --auto     # start in attract / demo mode
```

Controls: hold **F** / **J** to flex the left / right arm (or use the drive
sliders); **B** captures the baseline (力を抜いて); **R** resets the session;
**D** toggles attract/demo; **S** opens the settings window (live sliders for
RMS window, marker delay, r-range, judging thresholds, … + JSON save/load).
A headless screenshot for CI/preview:

```bash
python -m emg_sim.app --screenshot out.png --frames 240
```

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
