"""Signal processing (§6) + normalization (§5).

`RMSPipeline` turns raw EMG into a smoothed per-channel amplitude (rectify → RMS
window → EMA) and keeps a rolling buffer for the on-screen waveform.
`Normalizer` turns that amplitude into a normalized activation in [0,1]
(baseline subtraction → scale → tanh soft-sat), left/right independent.

Real EMG additionally needs band-pass + 50/60 Hz notch before RMS (scipy); the
synthetic dummy has no mains hum so the MVP skips it — see the TODO in
pipeline.py.
"""

from .pipeline import RMSPipeline
from .normalize import Normalizer

__all__ = ["RMSPipeline", "Normalizer"]
