"""Acquisition layer: input-source abstraction.

The rest of the app consumes an `InputSource` that yields raw 2-channel EMG
samples. A `DummySource` (synthetic EMG driven by keyboard/slider/auto) lets the
whole pipeline run without the BioRadio hardware; a real BioRadio source (via
pythonnet) plugs into the same interface later.
"""

from .source import InputSource
from .dummy import DummySource
from .bioradio import BioRadioSource, discover  # pythonnet import is deferred to start()


def make_source(cfg):
    """Build the input source selected by `cfg.acquisition` (dummy or bioradio)."""
    a = cfg.acquisition
    if a.source == "bioradio":
        return BioRadioSource(a.dll_path,
                              mac_id=int(a.mac_hex, 16) if a.mac_hex else None,
                              device_id=a.device or None, left=a.left, right=a.right)
    return DummySource(cfg, mode="manual")


__all__ = ["InputSource", "DummySource", "BioRadioSource", "discover", "make_source"]
