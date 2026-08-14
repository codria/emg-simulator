"""Single-channel EMG plot: dim raw signal + bright control value (0..1).

The control-value line is the normalized activation — the value that actually
drives control and the reach judging. One instance per arm, placed left/right of
the drive controls in the bottom row.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6 import QtWidgets


def _dim(c):
    return tuple(int(x * 0.55) for x in c)


class WaveformPlot(QtWidgets.QWidget):
    def __init__(self, title: str, color):
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.p = pg.PlotWidget(title=title)
        self.p.setBackground((26, 26, 34))
        self.p.setYRange(-2.2, 2.2)
        self.p.setMouseEnabled(False, False)
        self.p.hideAxis("bottom")
        self.p.setMenuEnabled(False)
        ax = self.p.getAxis("left")          # 0..1 = normalized control value
        ax.setTicks([[(-2, "-2"), (-1, "-1"), (0, "0"), (1, "1"), (2, "2")]])
        ax.setStyle(tickTextOffset=3)
        ax.setPen(pg.mkPen((120, 125, 140)))
        ax.setTextPen(pg.mkPen((150, 155, 170)))
        self.p.showGrid(x=False, y=True, alpha=0.15)
        self.p.addLegend(offset=(-6, 4), labelTextSize="7pt", brush=(30, 30, 40, 160))

        self.raw = self.p.plot(pen=pg.mkPen(_dim(color), width=1), name="raw")
        self.act = self.p.plot(pen=pg.mkPen(color, width=2), name="control value")
        lay.addWidget(self.p)

    def update_state(self, raw, act) -> None:
        self.raw.setData(raw)
        self.act.setData(act)
