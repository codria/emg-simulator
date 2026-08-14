"""Input-source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class InputSource(ABC):
    """Yields raw 2-channel EMG samples.

    ``read(dt)`` returns all samples that became available over the last ``dt``
    seconds as an ``(k, 2)`` float array (column 0 = left, 1 = right), where
    ``k`` may be 0. A real device ignores ``dt`` and drains its buffer; a
    synthetic source uses ``dt`` to generate ``round(dt * sample_rate)`` samples.
    """

    sample_rate: int = 1000
    n_channels: int = 2

    def start(self) -> None:  # optional lifecycle hooks
        pass

    def stop(self) -> None:
        pass

    @abstractmethod
    def read(self, dt: float) -> np.ndarray:
        """Return new samples, shape ``(k, 2)``."""
        raise NotImplementedError
