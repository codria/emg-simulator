"""BioRadioSource unit tests — the device-independent parts.

The pythonnet/SDK path (load, discover, connect, stream) needs the vendor DLL
and hardware, so it's exercised by tools/bioradio_smoketest.py, not here. What
we *can* test without either: the per-frame read() sample assembly and the
DLL-missing guard.
"""

import numpy as np
import pytest

from emg_sim.acquisition import BioRadioSource, discover, make_source
from emg_sim.config import Config
from emg_sim.engine import Engine


class _FakeSignal:
    """Stands in for a .NET Signal: GetScaledValueArray() returns buffered values."""

    def __init__(self, data):
        self._data = data

    def GetScaledValueArray(self):
        return list(self._data)


def _source_with(bp):
    src = BioRadioSource("unused.dll")   # __init__ never touches pythonnet/the DLL
    src._bp = bp
    return src


def test_read_assembles_two_channels():
    src = _source_with([_FakeSignal([1.0, 2.0, 3.0]), _FakeSignal([4.0, 5.0, 6.0])])
    out = src.read(1 / 60)
    assert out.shape == (3, 2)
    assert np.allclose(out[:, 0], [1, 2, 3])
    assert np.allclose(out[:, 1], [4, 5, 6])


def test_read_aligns_mismatched_lengths():
    src = _source_with([_FakeSignal([1.0, 2.0, 3.0]), _FakeSignal([4.0, 5.0])])
    out = src.read(1 / 60)
    assert out.shape == (2, 2)           # min of the two channel lengths
    assert np.allclose(out[:, 1], [4, 5])


def test_read_empty_returns_0x2():
    src = _source_with([_FakeSignal([]), _FakeSignal([])])
    assert src.read(1 / 60).shape == (0, 2)


def test_read_before_start_returns_0x2():
    src = BioRadioSource("unused.dll")
    assert src._bp is None
    assert src.read(1 / 60).shape == (0, 2)


def test_custom_channel_mapping_swaps_columns():
    src = BioRadioSource("unused.dll", left=1, right=0)
    src._bp = [_FakeSignal([10.0, 11.0]), _FakeSignal([20.0, 21.0])]
    out = src.read(1 / 60)
    assert np.allclose(out[:, 0], [20, 21])   # left arm reads channel index 1
    assert np.allclose(out[:, 1], [10, 11])   # right arm reads channel index 0


def test_missing_dll_raises_cleanly():
    with pytest.raises(FileNotFoundError):
        discover("does_not_exist.dll")
    with pytest.raises(FileNotFoundError):
        BioRadioSource("does_not_exist.dll").start()


# -- source factory + runtime swap ------------------------------------------
def test_make_source_selects_by_config():
    cfg = Config()
    assert type(make_source(cfg)).__name__ == "DummySource"   # default
    cfg.acquisition.source = "bioradio"
    cfg.acquisition.dll_path = "x.dll"
    src = make_source(cfg)
    assert isinstance(src, BioRadioSource) and src.dll_path == "x.dll"


class _FakeSource:
    def __init__(self, fail=False):
        self.fail, self.started, self.stopped = fail, False, False

    def start(self):
        if self.fail:
            raise RuntimeError("no device")
        self.started = True

    def stop(self):
        self.stopped = True

    def read(self, dt):
        return np.zeros((0, 2))


def test_set_source_swaps_and_starts_new():
    eng = Engine(seed=1)
    old = eng.source
    new = _FakeSource()
    eng.set_source(new)
    assert eng.source is new and new.started
    assert eng.source is not old


def test_set_source_rolls_back_on_failure():
    eng = Engine(seed=1)
    old = eng.source
    bad = _FakeSource(fail=True)
    with pytest.raises(RuntimeError):
        eng.set_source(bad)
    assert eng.source is old          # unchanged on failure
    assert bad.stopped                # cleaned up the half-open source
