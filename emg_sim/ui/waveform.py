"""Raw EMG waveform panel — two stacked plots on the right of the screen.

Top = right arm, bottom = left arm. Each shows the raw (pre-normalization) signal
dimly plus the normalized activation — the value that actually drives control and
the reach judging — as a bright overlaid line (0..1).
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from . import theme


def _dim(c):
    return tuple(int(x * 0.55) for x in c)


class WaveformPanel(QtWidgets.QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.p_right = self._make_plot("Right Arm EMG")
        self.p_left = self._make_plot("Left Arm EMG")
        # raw (dim) + activation = control/judging value (bright), per-channel hue
        self.raw_right = self.p_right.plot(pen=pg.mkPen(_dim(theme.R_COLOR), width=1), name="raw")
        self.act_right = self.p_right.plot(pen=pg.mkPen(theme.R_COLOR, width=2), name="control value")
        self.raw_left = self.p_left.plot(pen=pg.mkPen(_dim(theme.L_COLOR), width=1), name="raw")
        self.act_left = self.p_left.plot(pen=pg.mkPen(theme.L_COLOR, width=2), name="control value")
        lay.addWidget(self.p_right, 1)
        lay.addWidget(self.p_left, 1)

    def _make_plot(self, title: str):
        p = pg.PlotWidget(title=title)
        p.setBackground((26, 26, 34))
        p.setYRange(-2.2, 2.2)
        p.setMouseEnabled(False, False)
        p.hideAxis("bottom")
        p.setMenuEnabled(False)
        ax = p.getAxis("left")          # scale ticks (0..1 = normalized control value)
        ax.setTicks([[(-2, "-2"), (-1, "-1"), (0, "0"), (1, "1"), (2, "2")]])
        ax.setStyle(tickTextOffset=3)
        ax.setPen(pg.mkPen((120, 125, 140)))
        ax.setTextPen(pg.mkPen((150, 155, 170)))
        p.showGrid(x=False, y=True, alpha=0.15)
        p.addLegend(offset=(-6, 4), labelTextSize="7pt", brush=(30, 30, 40, 160))
        return p

    def update_state(self, raw_l, raw_r, act_l, act_r) -> None:
        self.raw_right.setData(raw_r)
        self.act_right.setData(act_r)
        self.raw_left.setData(raw_l)
        self.act_left.setData(act_l)
