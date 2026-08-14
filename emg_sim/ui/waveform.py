"""Single-channel EMG plot: dim raw signal + bright control value (0..1).

The control-value line is the normalized activation — the value that actually
drives control and the reach judging. X axis is time in seconds (0 = now, older
to the left). A shaded rectangle at the right marks the RMS window (the span the
RMS averages over). One instance per arm.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from . import theme


def _dim(c):
    return tuple(int(x * 0.55) for x in c)


class WaveformPlot(QtWidgets.QWidget):
    def __init__(self, title: str, color, cfg):
        super().__init__()
        self.cfg = cfg
        self.sr = cfg.signal.sample_rate
        disp = cfg.signal.display_sec

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.p = pg.PlotWidget(title=title)
        self.p.setBackground((26, 26, 34))
        self.p.setYRange(-2.2, 2.2)
        self.p.setXRange(-disp, 0.0, padding=0)      # data fills to both edges
        self.p.setMouseEnabled(False, False)
        self.p.setMenuEnabled(False)
        self.p.setClipToView(True)
        self.p.setDownsampling(mode="peak", auto=True)  # stays fast at long windows

        axl = self.p.getAxis("left")         # raw = arbitrary units; ctrl = 0..1
        axl.setTicks([[(-2, "-2"), (-1, "-1"), (0, "0"), (1, "1"), (2, "2")]])
        axl.setStyle(tickTextOffset=3)
        axl.setPen(pg.mkPen((120, 125, 140)))
        axl.setTextPen(pg.mkPen((150, 155, 170)))
        axl.setLabel("raw a.u.  /  control 0–1")

        step = 2 if disp > 6 else 1
        axb = self.p.getAxis("bottom")       # time (s), 0 = now
        ticks = [(-t, f"-{t}s") for t in range(int(disp), 0, -step)] + [(0.0, "now")]
        axb.setTicks([ticks])
        axb.setPen(pg.mkPen((120, 125, 140)))
        axb.setTextPen(pg.mkPen((150, 155, 170)))
        axb.setLabel("time  (0 = now)")
        self.p.showGrid(x=True, y=True, alpha=0.15)
        self.p.addLegend(offset=(-6, 4), labelTextSize="7pt", brush=(30, 30, 40, 160))

        # RMS window: the most-recent span the RMS averages over
        self.rms_region = pg.LinearRegionItem(
            values=[-cfg.signal.rms_window_ms / 1000.0, 0.0], movable=False,
            brush=(140, 150, 175, 40), pen=pg.mkPen((150, 160, 185, 90)))
        self.rms_region.setZValue(-10)
        self.p.addItem(self.rms_region)

        self.raw = self.p.plot(pen=pg.mkPen(_dim(color), width=1), name="raw")
        self.act = self.p.plot(pen=pg.mkPen(color, width=2), name="control value")
        lay.addWidget(self.p)

    def update_state(self, raw, act) -> None:
        n = len(raw)
        x = (np.arange(n) - (n - 1)) / self.sr   # last sample at t=0, older negative
        self.raw.setData(x, raw)
        self.act.setData(x, act)
        self.rms_region.setRegion([-self.cfg.signal.rms_window_ms / 1000.0, 0.0])
