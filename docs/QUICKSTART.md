# Quick start — clone & run on a clean machine

Get the exhibit app running from nothing. **No hardware is required**: it starts
on a built-in dummy input source (keyboard / sliders / auto-demo), so you can
play the full reaching game before a BioRadio is ever connected.

## Prerequisites

- **git**
- **Python 3.10–3.13** (64-bit). PySide6 wheels may not exist yet for 3.14 — use
  3.13 if unsure (`python --version` to check).
- A machine with a **desktop GPU / OpenGL display**. The 3D scene needs real
  OpenGL; a remote/headless box renders the 3D pane blank (everything else still
  works).

Windows is the primary target (the exhibit PC), but the app and tests also run on
macOS/Linux. The BioRadio acquisition is Windows-only and optional.

## 1. Clone

```bash
git clone https://github.com/codria/emg-simulator.git
cd emg-simulator
```

## 2. Create an isolated environment

Pick **one**. A virtualenv is the most portable:

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Windows (Git Bash):    source .venv/Scripts/activate
# macOS / Linux:         source .venv/bin/activate
```

…or conda (matches the project's dev env):

```bash
conda create -n env_emg-simulator python=3.13 -y
conda activate env_emg-simulator
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

Pulls numpy / scipy / PySide6 / pyqtgraph / PyOpenGL / pytest (and, on Windows,
`pythonnet` for the optional BioRadio path). The first install downloads
~150 MB (PySide6), so give it a minute.

## 4. Run

```bash
python -m emg_sim.app            # interactive (dummy input)
python -m emg_sim.app --auto     # start in attract / demo mode
```

You should see the 3D arm + two EMG bars + waveforms + the reaching game.

### Controls

| Key | Action |
|---|---|
| **F** / **J** (hold) | flex left / right arm — **F → θ** (azimuth), **J → r** (reach). Or drag the two on-screen sliders. |
| **B** | capture the rest baseline ("力を抜いて" — relax for a couple of seconds) |
| **D** | toggle attract / demo mode |
| **S** | settings window — live sliders (RMS window, EMA, soft-sat gain, scale floor, reach tolerances r/θ, …) + JSON save/load |
| **C** | connection dialog — switch input between Dummy and a real BioRadio |
| **R** | reset the round |
| mouse | drag to orbit, wheel to zoom the 3D scene |

**The game:** move both bars into their target bands so the arm tip enters the
green **(r, θ) wedge**, then hold it there briefly — a bright "charge" fills the
wedge and a flash confirms the reach. A subtle click plays when the tip enters
the zone, and a chime on a successful reach.

## 5. Run the tests (optional)

```bash
pytest                 # full suite
pytest -m "not slow"   # fast subset (~seconds)
```

## Sound

Works out of the box. If the (uncommitted) sound files are absent — which they
are on a fresh clone — the app **synthesizes** a subtle enter-click and a reach
chime at startup, so there is nothing to set up. For the nicer original SFX, drop
WAVs at `assets/sfx/enter.wav` and `assets/sfx/reach.wav` (gitignored 效果音ラボ
material — see [`docs/decisions.md`](decisions.md) for provenance and why they are
not committed). Any of this needs a working audio output device.

## Real BioRadio (optional, Windows only)

Not needed to try the app. When you have the hardware:

1. Download the free **BioRadio SDK for Windows** from GLNeuroTech and note the
   path to `API/BioRadioSDK.dll` (AnyCPU / .NET 4.5; **not** committed here).
2. Program 2 EMG channels + the sample rate in **BioCapture** first (otherwise
   the signal list comes back empty).
3. Launch pointing at the DLL, or switch at runtime with the **C** key:

```bash
python -m emg_sim.app --bioradio "C:\path\to\API\BioRadioSDK.dll"
python -m emg_sim.app --bioradio "…\BioRadioSDK.dll" --list-devices   # scan, print, exit
```

Details: [`CLAUDE.md`](../CLAUDE.md) and [`docs/emg_robotarm_exhibit_design.md`](emg_robotarm_exhibit_design.md).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'PySide6'`** — the environment isn't
  active, or deps aren't installed. Re-activate it and re-run
  `pip install -r requirements.txt`.
- **PySide6 fails to install** — you are probably on Python 3.14 (no wheels yet).
  Use Python 3.10–3.13.
- **PySide6 install fails with `OSError: [Errno 2]` and a "long path" hint**
  (Windows) — PySide6 ships very deeply-nested files that overflow the 260-char
  `MAX_PATH` limit. Fix either way:
  - clone to a **short path** (e.g. `C:\emg-simulator`, not a deep nested folder), or
  - enable long paths once (Admin PowerShell, then reboot):
    ```powershell
    New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
      -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
    ```
- **The 3D pane is blank / OpenGL errors** — it needs a real OpenGL display; on
  Windows, Qt uses ANGLE (OpenGL ES) by default. Update the GPU driver if it
  persists. On a remote/headless machine the 3D pane is expected to be blank
  (`python -m emg_sim.app --screenshot out.png` also renders it blank there).
- **No sound** — the machine needs an audio output device; the synthesized
  fallback still requires a working audio backend. `sfx_enabled` (config) toggles
  all SFX.
- **Settings don't persist** — the **S** window's *Save* writes
  `config/user.json`; reload it with the window's *Load* button or
  `python -m emg_sim.app --config config/user.json`.
