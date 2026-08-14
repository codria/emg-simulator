"""Headless tests for the MVP core: config, dummy source, dsp, normalize,
control mapping, game, and the engine integration."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emg_sim.config import Config
from emg_sim.acquisition import DummySource
from emg_sim.dsp import RMSPipeline, Normalizer
from emg_sim.control import PolarController, polar_to_xyz
from emg_sim.game import ReachingGame
from emg_sim.engine import Engine


def _horiz_r(p) -> float:
    return math.hypot(p[0], p[1])


# -- config -----------------------------------------------------------------
def test_config_roundtrip(tmp_path):
    c = Config()
    c.control.r_max = 0.42
    c.game.hold_sec = 0.33
    p = tmp_path / "cfg.json"
    c.save(p)
    d = Config.load(p)
    assert d.control.r_max == pytest.approx(0.42)
    assert d.game.hold_sec == pytest.approx(0.33)
    assert d.signal.sample_rate == c.signal.sample_rate


# -- dummy source -----------------------------------------------------------
def test_dummy_rms_tracks_drive():
    cfg = Config()
    dsp = RMSPipeline(cfg)
    src = DummySource(cfg, seed=1)
    src.set_drive(0.0, 0.0)
    for _ in range(60):
        amp0 = dsp.process(src.read(1 / 60))
    src.set_drive(1.0, 1.0)
    for _ in range(60):
        amp1 = dsp.process(src.read(1 / 60))
    assert amp0[0] < 0.1           # rest ≈ noise floor
    assert amp1[0] > 0.5           # full drive ≈ 1.0
    assert amp1[1] > amp0[1]


def test_dummy_auto_mode_moves():
    cfg = Config()
    src = DummySource(cfg, mode="auto", seed=2)
    src.read(1.0)
    d1 = src.drive.copy()
    src.read(3.0)
    d2 = src.drive.copy()
    assert not np.allclose(d1, d2)


# -- normalize --------------------------------------------------------------
def test_normalize_soft_sat_bounded():
    n = Normalizer(Config())
    a = n.normalize(np.array([100.0, 100.0]))  # huge input
    assert np.all(a <= 1.0) and np.all(a >= 0.0)  # bounded
    # nominal "full effort" (x ≈ scale) is eased by tanh, not hard-pegged
    n2 = Normalizer(Config())
    a2 = n2.normalize(np.array([n2.scale[0], n2.scale[1]]))
    assert np.all(a2 < 0.98)


def test_normalize_baseline_subtracts():
    n = Normalizer(Config())
    n.start_baseline()
    for _ in range(10):
        n.feed_baseline(np.array([0.2, 0.2]))
    n.finish_baseline()
    assert np.allclose(n.baseline, 0.2, atol=1e-6)
    # at baseline amplitude, activation is ~0
    assert np.all(n.normalize(np.array([0.2, 0.2])) < 1e-6)


def test_normalize_adaptation_upward_only():
    # with no time passing (dt = 0) the leaky peak doesn't decay → upward-only
    n = Normalizer(Config())
    for _ in range(50):
        n.normalize(np.array([1.0, 1.0]))
    hi = n.scale.copy()
    for _ in range(50):
        n.normalize(np.array([0.05, 0.05]))
    assert np.all(n.scale >= hi - 1e-9)  # never decreases without a time step


def test_normalize_peak_decays():
    # a leaky peak lets the scale recover after a one-off high, so the extremes
    # stay reachable (dt > 0 decays the peak; halflife shortened for the test)
    cfg = Config()
    cfg.normalize.peak_halflife_sec = 2.0
    n = Normalizer(cfg)
    for _ in range(30):  # brief high effort latches the scale up
        n.normalize(np.array([2.0, 2.0]), dt=1 / 60)
    hi = n.scale.copy()
    assert np.all(hi > cfg.normalize.fallback_scale)
    for _ in range(600):  # ~10 s of lower sustained effort (>> halflife)
        n.normalize(np.array([0.3, 0.3]), dt=1 / 60)
    assert np.all(n.scale < hi - 1e-3)                             # recovered downward
    assert np.all(n.scale >= cfg.normalize.fallback_scale - 1e-9)  # not below the floor


# -- control mapping --------------------------------------------------------
def test_mapping_extremes():
    cfg = Config()
    ctrl = PolarController(cfg)
    r, th = ctrl.target_from_activation(0.0, 0.0)
    assert r == pytest.approx(cfg.control.r_min)
    assert th == pytest.approx(cfg.control.theta_min)
    r, th = ctrl.target_from_activation(1.0, 1.0)
    assert r == pytest.approx(cfg.control.r_max)     # right → r
    assert th == pytest.approx(cfg.control.theta_max)  # left → θ


def test_mapping_full_reach_tracks_sat_gain():
    # lowering sat_gain caps full-effort activation at tanh(sat_gain); full_ref must
    # track it so full effort still hits r_max/θ_max instead of falling short.
    cfg = Config()
    cfg.normalize.sat_gain = 1.0                      # tanh(1.0) ≈ 0.76 < reach_full 0.9
    ctrl = PolarController(cfg)
    a_full = float(np.tanh(cfg.normalize.sat_gain))   # max activation a full contraction reaches
    r, th = ctrl.target_from_activation(a_full, a_full)
    assert r == pytest.approx(cfg.control.r_max)
    assert th == pytest.approx(cfg.control.theta_max)


def test_mapping_target_reachable_and_tracks():
    cfg = Config()
    cfg.normalize.sat_gain = 1.6      # pin the effort→reach mapping (full_ref = 0.9)
    ctrl = PolarController(cfg)
    for _ in range(80):
        q, tip, target = ctrl.update(0.8, 0.6)
    # target on the operation plane, within the fan
    assert target[2] == pytest.approx(cfg.control.z_plane)
    assert cfg.control.r_min - 1e-6 <= _horiz_r(target) <= cfg.control.r_max + 1e-6
    # tip converged onto the target
    assert np.linalg.norm(tip - target) < 5e-3


# -- game -------------------------------------------------------------------
def test_game_reach_needs_dwell():
    cfg = Config()
    g = ReachingGame(cfg)
    at = g.target_xyz
    # brief touch (< hold_sec) does not count
    assert g.update(at, cfg.game.hold_sec * 0.5) is None
    # leaving resets the dwell
    assert g.update(at + np.array([1.0, 0, 0]), 0.1) is None
    # sustained dwell counts
    ev = g.update(at, cfg.game.hold_sec + 1e-3)
    assert ev in ("reached", "round_complete")


def test_game_reach_zone_is_rtheta_box():
    # hit zone is an (r,θ) box: independent per-axis tolerances (θ eased separately)
    cfg = Config()
    dr = cfg.game.reach_r
    dth = math.radians(cfg.game.reach_theta_deg)
    hold = cfg.game.hold_sec + 1e-3

    def reached(r, th):
        g = ReachingGame(cfg)                       # fresh so the respawn can't interfere
        g.target_rt = (0.45, 1.2)
        g.target_xyz = polar_to_xyz(cfg.control, 0.45, 1.2)
        return g.update(polar_to_xyz(cfg.control, r, th), hold) in ("reached", "round_complete")

    r0, t0 = 0.45, 1.2
    assert reached(r0, t0)                          # dead centre
    assert reached(r0 + dr * 0.8, t0)               # inside r tolerance
    assert reached(r0, t0 + dth * 0.8)              # inside θ tolerance
    assert not reached(r0 + dr * 1.5, t0)           # outside r tolerance
    assert not reached(r0, t0 + dth * 1.5)          # outside θ tolerance


def test_game_round_completes_after_five():
    cfg = Config()
    g = ReachingGame(cfg)
    events = []
    for _ in range(5):
        events.append(g.update(g.target_xyz, cfg.game.hold_sec + 1e-3))
    assert events.count("reached") == 4
    assert events[-1] == "round_complete"
    assert g.last_round_time is not None


def test_game_target_in_fan_and_separated():
    cfg = Config()
    g = ReachingGame(cfg)
    prev = g.target_xyz.copy()
    for _ in range(20):
        g.spawn()
        r = _horiz_r(g.target_xyz)
        assert cfg.control.r_min - 1e-6 <= r <= cfg.control.r_max + 1e-6
        assert np.linalg.norm(g.target_xyz - prev) >= cfg.game.min_target_sep - 1e-6
        prev = g.target_xyz.copy()


def test_game_target_respects_edge_margin():
    cfg = Config()
    c, m = cfg.control, cfg.game.target_margin
    dr = (c.r_max - c.r_min) * m
    dt = (c.theta_max - c.theta_min) * m
    g = ReachingGame(cfg, seed=1)
    for _ in range(200):
        r, th = g._rand_rt()
        assert c.r_min + dr - 1e-9 <= r <= c.r_max - dr + 1e-9
        assert c.theta_min + dt - 1e-9 <= th <= c.theta_max - dt + 1e-9


# -- engine integration -----------------------------------------------------
def test_engine_full_drive_reaches_out():
    eng = Engine(seed=3)
    eng.source.set_drive(1.0, 1.0)
    for _ in range(180):  # ~3 s
        eng.step(1 / 60)
    assert _horiz_r(eng.tip) > 0.5          # arm extended near r_max
    assert abs(eng.tip[2] - eng.cfg.control.z_plane) < 0.02   # on the operation plane


def test_engine_zero_drive_stays_in():
    eng = Engine(seed=4)
    eng.source.set_drive(0.0, 0.0)
    for _ in range(600):  # 10 s idle — attract is D-key only now, no auto-enter
        eng.step(1 / 60)
    # retracted toward the inner edge (arm folds to its inner reach limit, which
    # may exceed r_min if r_min is set below what the arm can fold to)
    assert _horiz_r(eng.tip) < 0.35
    assert not eng.attract


def test_engine_attract_toggle():
    eng = Engine(seed=5)
    eng.source.set_drive(0.0, 0.0)
    eng.step(1 / 60)
    assert not eng.attract                  # idle never auto-enters attract
    eng.set_attract(True)                   # D key enters demo
    assert eng.attract and eng.source.mode == "auto"
    eng.notify_user_input()                 # any real input exits demo
    assert not eng.attract and eng.source.mode == "manual"
