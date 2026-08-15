"""BioRadioSource unit tests — the device-independent parts.

The pythonnet/SDK path (load, discover, connect, stream) needs the vendor DLL
and hardware, so it's exercised by tools/bioradio_smoketest.py, not here. What
we *can* test without either: the per-frame read() sample assembly and the
DLL-missing guard.
"""

import threading
import time

import numpy as np
import pytest

from emg_sim.acquisition import BioRadioSource, discover, make_source
from emg_sim.acquisition.bioradio import _V_TO_MV   # read() converts volts → mV
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
    src._buf = [[], []]                  # normally created by start(); the poll fills it
    return src


def test_read_assembles_two_channels():
    src = _source_with([_FakeSignal([1.0, 2.0, 3.0]), _FakeSignal([4.0, 5.0, 6.0])])
    src._pump()                          # one poll (device → queue), then read drains it
    out = src.read(1 / 60)
    assert out.shape == (3, 2)
    assert np.allclose(out[:, 0], np.array([1, 2, 3]) * _V_TO_MV)
    assert np.allclose(out[:, 1], np.array([4, 5, 6]) * _V_TO_MV)


def test_read_aligns_mismatched_lengths():
    src = _source_with([_FakeSignal([1.0, 2.0, 3.0]), _FakeSignal([4.0, 5.0])])
    src._pump()
    out = src.read(1 / 60)
    assert out.shape == (2, 2)           # min of the two channel lengths
    assert np.allclose(out[:, 1], np.array([4, 5]) * _V_TO_MV)


def test_read_empty_returns_0x2():
    src = _source_with([_FakeSignal([]), _FakeSignal([])])
    src._pump()
    assert src.read(1 / 60).shape == (0, 2)


def test_read_before_start_returns_0x2():
    src = BioRadioSource("unused.dll")
    assert src._bp is None
    assert src.read(1 / 60).shape == (0, 2)


def test_custom_channel_mapping_swaps_columns():
    src = BioRadioSource("unused.dll", left=1, right=0)
    src._bp = [_FakeSignal([10.0, 11.0]), _FakeSignal([20.0, 21.0])]
    src._buf = [[], []]
    src._pump()
    out = src.read(1 / 60)
    assert np.allclose(out[:, 0], np.array([20, 21]) * _V_TO_MV)   # left arm reads channel index 1
    assert np.allclose(out[:, 1], np.array([10, 11]) * _V_TO_MV)   # right arm reads channel index 0


class _DrainingSignal:
    """Like _FakeSignal but drains on read, as the real SDK does."""

    def __init__(self, data):
        self._data = list(data)

    def GetScaledValueArray(self):
        d, self._data = self._data, []
        return d


def test_poll_thread_streams_into_read_and_stops():
    # the background poll thread drains the device into the queue; read() consumes it
    src = _source_with([_DrainingSignal([1.0, 2.0, 3.0]), _DrainingSignal([4.0, 5.0, 6.0])])
    src._stop = threading.Event()
    src._poll = threading.Thread(target=src._poll_loop, daemon=True)
    src._poll.start()
    time.sleep(0.05)                     # several 5 ms poll cycles
    src._stop.set()
    src._poll.join(timeout=1.0)
    assert not src._poll.is_alive()      # exits promptly on the stop signal
    out = src.read(1 / 60)
    assert out.shape == (3, 2)
    assert np.allclose(out[:, 0], np.array([1, 2, 3]) * _V_TO_MV)


def test_pump_caps_buffer_dropping_oldest():
    # under a main-loop stall the poll thread must bound the queue and keep the NEWEST
    # samples (stay real-time), not grow an unbounded backlog of stale EMG.
    src = _source_with([_FakeSignal(list(range(1, 11))), _FakeSignal(list(range(101, 111)))])
    src._buf_cap = 5
    src._pump()
    assert len(src._buf[0]) == 5 and len(src._buf[1]) == 5
    assert src._buf[0] == [6, 7, 8, 9, 10]           # oldest dropped, newest kept
    assert src._buf[1] == [106, 107, 108, 109, 110]


def test_read_sanitizes_nonfinite_samples():
    # a BT/electrode dropout can yield NaN/Inf; one such sample must not reach the
    # pipeline (it would poison the baseline mean and every downstream value).
    src = _source_with([_FakeSignal([1.0, float("nan"), 3.0]),
                        _FakeSignal([4.0, float("inf"), float("-inf")])])
    src._pump()
    out = src.read(1 / 60)
    assert np.isfinite(out).all()
    assert np.allclose(out[:, 0], np.array([1.0, 0.0, 3.0]) * _V_TO_MV)
    assert np.allclose(out[:, 1], np.array([4.0, 0.0, 0.0]) * _V_TO_MV)


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
