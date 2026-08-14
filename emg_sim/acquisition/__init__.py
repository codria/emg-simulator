"""Acquisition layer: input-source abstraction.

The rest of the app consumes an `InputSource` that yields raw 2-channel EMG
samples. A `DummySource` (synthetic EMG driven by keyboard/slider/auto) lets the
whole pipeline run without the BioRadio hardware; a real BioRadio source (via
pythonnet) plugs into the same interface later.
"""

from .source import InputSource
from .dummy import DummySource

__all__ = ["InputSource", "DummySource"]
