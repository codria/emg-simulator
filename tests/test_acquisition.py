"""BioRadioSource unit tests — the device-independent parts.

The pythonnet/SDK path (load, discover, connect, stream) needs the vendor DLL
and hardware, so it's exercised by tools/bioradio_smoketest.py, not here. What
we *can* test without either: the per-frame read() sample assembly and the
DLL-missing guard.
"""

import numpy as np
import pytest

from emg_sim.acquisition import BioRadioSource, discover


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
