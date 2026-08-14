"""Runtime configuration (nested dataclasses + JSON persistence).

Exposed to the settings window (sliders) later; values that the design doc marks
as "tune on real hardware" (RMS window, r/θ range, judging thresholds, marker
delay) all live here so they can be adjusted and saved without code changes.
"""

# NOTE: intentionally no `from __future__ import annotations` — _build() below
# relies on dataclass field .type being the real class, not a string.

import json
import math
from dataclasses import dataclass, field, fields, asdict, is_dataclass
from pathlib import Path


@dataclass
class SignalConfig:
    sample_rate: int = 1000        # Hz (dummy synthetic EMG / device rate)
    rms_window_ms: float = 150.0   # RMS window, design says 100–300 ms
    ema_alpha: float = 0.3         # light EMA on top of RMS (0..1, higher = snappier)
    display_sec: float = 1.5       # raw-waveform history shown on screen
    # real-EMG front-end filter (§6); applied before rectify/RMS, not to display
    filter_enabled: bool = True
    bp_low: float = 20.0           # band-pass low (Hz)
    bp_high: float = 450.0         # band-pass high (Hz; clamped below Nyquist)
    bp_order: int = 4
    notch_freq: float = 50.0       # mains notch (50 or 60 Hz)
    notch_q: float = 30.0


@dataclass
class NormalizeConfig:
    baseline_sec: float = 2.0      # "力を抜いて" baseline capture duration
    soft_sat: bool = True          # tanh soft saturation
    sat_gain: float = 1.6          # activation = tanh(sat_gain * x / scale)
    adapt_rate: float = 0.05       # online upward scale adaptation (0 = off)
    fallback_scale: float = 0.5    # fixed-gain fallback so it always moves


@dataclass
class ControlConfig:
    # Reachable band (annulus) is r∈[0.34, 0.71] with the relaxed elbow bias
    # below — the arm can't fold to its own base (hence r_min>0) and now extends
    # near full reach instead of staying bent. Defaults sit inside the band.
    r_min: float = 0.36
    r_max: float = 0.70
    theta_min: float = 0.0
    theta_max: float = math.pi
    z_plane: float = 0.045         # operation plane at the shoulder (Tube3 centre)
    left_axis: str = "theta"       # left arm → θ; right arm → r (swap: "r")
    # Activation counted as "full effort" → maps to r_max/θ_max. Because the soft
    # saturation caps full-effort activation below 1.0 (~tanh(sat_gain)), without
    # this the arm never reaches r_max (and never visibly extends). Rescale so
    # full effort uses the whole reach; control below stays smooth.
    reach_full_activation: float = 0.9
    # elbow-up IK bias. The C++ default (1.5 / 0.3) pins the elbow bent (~63° even
    # at max reach); a weaker bias keeps a natural "elbow up" pose at rest yet lets
    # the arm straighten to reach far targets (~0.71 vs 0.64).
    elbow_target: float = 1.0
    elbow_gain: float = 0.15


@dataclass
class GameConfig:
    reach_dist: float = 0.05       # tip within 5 cm of target
    hold_sec: float = 0.4          # dwell time to count as reached (0.3–0.5)
    targets_per_round: int = 5     # 5 reaches → time → reset
    min_target_sep: float = 0.15   # next target at least this far from current
    attract_idle_sec: float = 8.0  # idle → attract mode


@dataclass
class UIConfig:
    marker_enabled: bool = True    # target marker on the bars (position control)
    marker_delay_sec: float = 3.0  # delayed fade-in
    show_waveform: bool = True     # raw waveforms on the right (top=R, bottom=L)
    sfx_enabled: bool = True       # reach-success sound effect
    sfx_reach: str = "assets/sfx/reach.wav"  # optional; no-op if missing
    sfx_volume: float = 0.7


@dataclass
class Config:
    signal: SignalConfig = field(default_factory=SignalConfig)
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    game: GameConfig = field(default_factory=GameConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Config":
        return _build(cls, json.loads(Path(path).read_text(encoding="utf-8")))


def _build(cls, d: dict):
    """Reconstruct a (possibly nested) dataclass from a plain dict, ignoring
    unknown keys and filling missing ones with defaults."""
    vals = {}
    for f in fields(cls):
        if f.name not in d:
            continue
        if is_dataclass(f.type) and isinstance(d[f.name], dict):
            vals[f.name] = _build(f.type, d[f.name])
        else:
            vals[f.name] = d[f.name]
    return cls(**vals)
