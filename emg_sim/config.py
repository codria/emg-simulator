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
    rms_window_ms: float = 400.0   # RMS window (ms); smoother/slower at high values
    ema_alpha: float = 0.20        # light EMA on top of RMS (0..1, higher = snappier)
    display_sec: float = 10.0      # waveform history window (wider = slower scroll)
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
    sat_gain: float = 1.2          # activation = tanh(sat_gain * x / scale)
    adapt_rate: float = 0.05       # scale adaptation speed toward the peak (0 = off)
    fallback_scale: float = 0.5    # scale floor/initial in MILLIVOLTS (~0.5 mV, half a
                                   # typical ~1 mV EMG). Below the flex peak so the
                                   # leaky-peak can adapt down to it; lower = more sensitive.
    peak_halflife_sec: float = 120.0 # leaky-peak decay: stale highs fade (≈ recent-max
                                     # window) so a one-off artifact / max clench doesn't
                                     # latch the scale up forever and block the extremes


@dataclass
class ControlConfig:
    # Physical reach ≈ [0.14, 0.73] at the shoulder plane (adaptive elbow folds in
    # near the base, straightens out far, so the whole physical range is usable —
    # no solver-imposed inner limit). r_min sits a bit above the physical floor as a
    # comfortable operating floor: control gets twitchy very close to the base.
    r_min: float = 0.23
    r_max: float = 0.70
    theta_min: float = 0.0
    theta_max: float = math.pi
    z_plane: float = 0.045         # operation plane at the shoulder (Tube3 centre)
    left_axis: str = "theta"       # left arm → θ; right arm → r (swap: "r")
    # Activation counted as "full effort" → maps to r_max/θ_max. Soft saturation
    # caps full-effort activation below 1.0 (~tanh(sat_gain)); without this the arm
    # never reaches r_max. PolarController.full_ref() also caps this by tanh(sat_gain)
    # at runtime, so lowering sat_gain still reaches the extremes.
    reach_full_activation: float = 0.9
    # Adaptive elbow-up bias: fold when reaching near (r→r_min), straighten when
    # reaching far (r→r_max), interpolated by r. This lets the arm use its full
    # physical range instead of the ~0.29 inner limit a fixed bias imposed — the
    # limit was a solver artifact, not the arm. Also gives a natural fold/extend
    # look. C++ used a fixed 1.5/0.3.
    elbow_target_near: float = 2.0   # at r_min: elbow folded (~144°)
    elbow_target_far: float = 0.1    # at r_max: elbow nearly straight
    elbow_gain: float = 0.15
    # keep the manipulator pointing down at the target (null-space bias)
    tool_down: bool = True
    tool_down_gain: float = 0.35


@dataclass
class GameConfig:
    # Target hit zone is an (r, θ) box (a fan wedge), tuned per-axis so the θ
    # difficulty (high-gain: arc = r·Δθ) can be eased independently of r.
    reach_r: float = 0.05          # radial half-tolerance (m): |r_tip − r_target|
    reach_theta_deg: float = 7.0   # angular half-tolerance (deg): |θ_tip − θ_target|
    hold_sec: float = 0.4          # dwell time to count as reached (0.3–0.5)
    targets_per_round: int = 5     # 5 reaches → time → reset
    min_target_sep: float = 0.15   # next target at least this far from current
    # Inset targets away from every fan edge (fraction of each range), since the
    # extremes are hard to hold: r_max ≈ full extension/effort, r_min ≈ rest,
    # θ_min/θ_max ≈ extreme sweep. Applies to r AND θ.
    target_margin: float = 0.12


@dataclass
class UIConfig:
    marker_enabled: bool = True    # target marker on the bars (position control)
    marker_delay_sec: float = 3.0  # delayed fade-in
    show_waveform: bool = True     # raw waveforms on the right (top=R, bottom=L)
    sfx_enabled: bool = True       # sound effects (reach + zone-enter)
    sfx_reach: str = "assets/sfx/reach.wav"  # reach-success; no-op if missing
    sfx_enter: str = "assets/sfx/enter.wav"  # subtle click when the tip enters the target zone
    sfx_volume: float = 0.7


@dataclass
class AcquisitionConfig:
    source: str = "dummy"          # "dummy" (keyboard/slider) | "bioradio" (real device)
    dll_path: str = ""             # path to BioRadioSDK.dll (free GLNeuroTech SDK)
    mac_hex: str = ""              # BioRadio MAC as hex; "" = first device found
    device: str = ""               # device name to match; "" = any
    left: int = 0                  # BioPotential channel index → left arm
    right: int = 1                 # BioPotential channel index → right arm


# the settings-window sections (everything the sliders touch) — NOT `acquisition`,
# so resetting/loading tuning never disturbs the device/connection setup.
_TUNABLE_SECTIONS = ("signal", "normalize", "control", "game", "ui")


@dataclass
class Config:
    signal: SignalConfig = field(default_factory=SignalConfig)
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    game: GameConfig = field(default_factory=GameConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    acquisition: AcquisitionConfig = field(default_factory=AcquisitionConfig)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Config":
        return _build(cls, json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def load_or_default(cls, path) -> "Config":
        """Load a Config JSON, or fall back to defaults if it's missing/corrupt, so a
        bad config file can never stop the app from starting (important for the live
        exhibit). Prints a note to stderr on fallback."""
        try:
            return cls.load(path)
        except Exception as e:
            import sys
            print(f"config load failed ({path}): {e}; using defaults", file=sys.stderr)
            return cls()

    def copy_tunables_from(self, other: "Config") -> None:
        """Copy the settings-window sections (all except `acquisition`) from `other`
        into this config *in place*, so the running engine's live references stay
        valid. Backs both the settings dialog's Load and Reset-to-defaults."""
        for sec in _TUNABLE_SECTIONS:
            src, dst = getattr(other, sec), getattr(self, sec)
            for f in vars(src):
                setattr(dst, f, getattr(src, f))


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
