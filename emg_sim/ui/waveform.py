"""Raw EMG waveform panel — two stacked plots on the right of the screen.

Per the display decision: top = right arm, bottom = left arm. Shows the raw
(pre-normalization) signal so visitors see the muscle activity being measured.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets


class WaveformPanel(QtWidgets.QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.p_right = self._make_plot("EMG  R  (right arm)", (120, 200, 255))
        self.p_left = self._make_plot("EMG  L  (left arm)", (255, 170, 90))
        self.c_right = self.p_right.plot(pen=pg.mkPen((120, 200, 255), width=1))
        self.c_left = self.p_left.plot(pen=pg.mkPen((255, 170, 90), width=1))
        lay.addWidget(self.p_right, 1)
        lay.addWidget(self.p_left, 1)

    def _make_plot(self, title: str, color):
        p = pg.PlotWidget(title=title)
        p.setBackground((26, 26, 34))
        p.setYRange(-2.2, 2.2)
        p.setMouseEnabled(False, False)
        p.hideAxis("bottom")
        p.setMenuEnabled(False)
        ax = p.getAxis("left")          # scale ticks (arbitrary EMG units)
        ax.setTicks([[(-2, "-2"), (-1, "-1"), (0, "0"), (1, "1"), (2, "2")]])
        ax.setStyle(tickTextOffset=3)
        ax.setPen(pg.mkPen((120, 125, 140)))
        ax.setTextPen(pg.mkPen((150, 155, 170)))
        p.showGrid(x=False, y=True, alpha=0.15)
        return p

    def update_state(self, wave_left: np.ndarray, wave_right: np.ndarray) -> None:
        self.c_right.setData(wave_right)
        self.c_left.setData(wave_left)
