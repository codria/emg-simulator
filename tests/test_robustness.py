"""Day-of robustness guards: the exhibit must survive bad input / bad config
without crashing or rendering garbage. All hardware-free.

See the freeze investigation + hardening: bounded BT queue and NaN sanitize live
in test_acquisition; here we cover the controller's last-good-pose guard and the
resilient config loader.
"""

import numpy as np

from emg_sim.config import Config
from emg_sim.control.mapping import PolarController


def test_controller_holds_last_good_pose_on_nonfinite_activation():
    # a NaN activation (e.g. from a degenerate numeric path) must not make the arm
    # vanish — the controller holds the last finite pose instead.
    ctrl = PolarController(Config())
    good = ctrl.arm.q.copy()
    assert np.all(np.isfinite(good))
    q, tip, target = ctrl.update(float("nan"), float("nan"))
    assert np.all(np.isfinite(q))          # never NaN
    assert np.all(np.isfinite(tip))
    assert np.allclose(q, good)            # specifically the last good pose


def test_controller_normal_update_still_moves():
    # the guard must not disturb the normal path: a finite drive still moves the arm.
    ctrl = PolarController(Config())
    start = ctrl.arm.q.copy()
    for _ in range(20):
        ctrl.update(0.8, 0.2)
    assert np.all(np.isfinite(ctrl.arm.q))
    assert not np.allclose(ctrl.arm.q, start)


def test_config_load_or_default_on_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json ", encoding="utf-8")
    cfg = Config.load_or_default(str(p))
    assert isinstance(cfg, Config)
    assert cfg.normalize.baseline_sec == Config().normalize.baseline_sec   # fell back


def test_config_load_or_default_on_missing(tmp_path):
    cfg = Config.load_or_default(str(tmp_path / "does_not_exist.json"))
    assert isinstance(cfg, Config)


def test_copy_tunables_resets_sliders_but_keeps_acquisition():
    # settings reset/load must restore the slider sections but PRESERVE the device
    # setup (acquisition), and mutate in place so the live engine keeps its refs.
    cfg = Config()
    cfg.normalize.sat_gain = 2.9
    cfg.game.reach_r = 0.099
    cfg.acquisition.dll_path = "keep.dll"
    cfg.acquisition.mac_hex = "ECFE7E1EB527"
    norm_obj = cfg.normalize
    cfg.copy_tunables_from(Config())              # reset to defaults
    d = Config()
    assert cfg.normalize.sat_gain == d.normalize.sat_gain    # tunables reset
    assert cfg.game.reach_r == d.game.reach_r
    assert cfg.acquisition.dll_path == "keep.dll"            # connection preserved
    assert cfg.acquisition.mac_hex == "ECFE7E1EB527"
    assert cfg.normalize is norm_obj                         # in place, not replaced


def test_config_load_or_default_valid_roundtrip(tmp_path):
    p = tmp_path / "ok.json"
    c = Config()
    c.game.reach_r = 0.077
    c.save(p)
    loaded = Config.load_or_default(str(p))
    assert abs(loaded.game.reach_r - 0.077) < 1e-9    # a good file still loads
