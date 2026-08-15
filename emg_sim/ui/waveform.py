"""Single-channel EMG plot: the amplitude-domain terms that make up the control
value. Shows the raw signal and the smoothed envelope ``amp``, plus the three
references the normalization uses — ``baseline`` (subtracted), ``scale`` (the
divisor, drawn at ``baseline+scale`` = the "full effort" level) and the leaky
``peak`` the scale follows. Everything is on one amplitude axis (a.u.); the 0–1
control value ``tanh(sat_gain·(amp−baseline)/scale)`` is read off the bars, not
here. X axis is time (0 = now, older to the left). One instance per arm.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

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

        axl = self.p.getAxis("left")         # amplitude (a.u. for dummy, volts for a device)
        axl.setStyle(tickTextOffset=3)       # ticks auto-generate to fit the auto-scaled range
        self._yhi = 0.0                      # eased y-range high-water (autoscale)
        axl.setPen(pg.mkPen((120, 125, 140)))
        axl.setTextPen(pg.mkPen((150, 155, 170)))
        axl.setLabel("amplitude (a.u.)")

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
        self.amp = self.p.plot(pen=pg.mkPen(color, width=2), name="amp (envelope)")

        # the three terms of  activation = tanh(sat_gain·(amp − baseline) / scale):
        #   numerator = amp − baseline (gap above the baseline line)
        #   denominator = scale (drawn at baseline+scale = amp level for full effort)
        #   peak = the leaky high-water mark the scale follows
        # all amplitude-domain, one line per channel (independent L/R).
        dash = QtCore.Qt.PenStyle.DashLine
        dot = QtCore.Qt.PenStyle.DotLine
        fill = (26, 26, 34, 170)             # readable over the raw signal
        self.base_line = pg.InfiniteLine(
            angle=0, movable=False, pen=pg.mkPen((150, 155, 165), width=1, style=dash),
            label="baseline",       # anchor the text's top edge to the line → label sits below
            labelOpts={"position": 0.14, "color": (175, 180, 190), "fill": fill,
                       "anchors": [(0.5, 0), (0.5, 0)]})
        self.scale_line = pg.InfiniteLine(
            angle=0, movable=False, pen=pg.mkPen((225, 228, 236), width=1, style=dash),
            label="scale", labelOpts={"position": 0.40, "color": (228, 231, 238), "fill": fill})
        self.peak_line = pg.InfiniteLine(
            angle=0, movable=False, pen=pg.mkPen((240, 140, 120), width=1, style=dot),
            label="peak", labelOpts={"position": 0.66, "color": (242, 152, 132), "fill": fill})
        for ln in (self.base_line, self.scale_line, self.peak_line):
            ln.setZValue(5)
            self.p.addItem(ln)
        lay.addWidget(self.p)

    def update_state(self, raw, amp, baseline=0.0, scale=0.0, peak=0.0) -> None:
        self.sr = self.cfg.signal.sample_rate        # may have been adopted from a device
        n = len(raw)
        t = (np.arange(n) - (n - 1)) / self.sr   # last sample at t=0, older negative
        self.raw.setData(t, raw)
        self.amp.setData(t, amp)
        self.rms_region.setRegion([-self.cfg.signal.rms_window_ms / 1000.0, 0.0])
        b = float(baseline)
        self.base_line.setPos(b)                     # subtracted floor
        self.scale_line.setPos(b + float(scale))     # amp here → x/scale = 1 (満力)
        self.peak_line.setPos(b + float(peak))       # leaky high-water mark
        self._autoscale_y(raw, amp, b, float(peak))

    def _autoscale_y(self, raw, amp, b, peak) -> None:
        """Fit the y-axis to the actual signal. A device streams volts (~±0.05) while
        the dummy is a.u. (~±2) — the old fixed range hid one or the other. Fit a high
        percentile of |raw| (so occasional spikes don't shrink everything) together
        with the envelope and the leaky peak; ease the range so it doesn't jitter.
        (`scale` is intentionally excluded: a mis-tuned fallback would push the whole
        signal flat — lower `fallback_scale` in Settings and its line drops into view.)"""
        pk = float(np.percentile(np.abs(raw), 98)) if len(raw) else 0.0
        top = max(pk, float(np.max(amp)) if len(amp) else 0.0, abs(b) + float(peak), 1e-3)
        self._yhi = max(top, self._yhi * 0.9)        # rise now, decay slowly (~1 s)
        hi = self._yhi * 1.25
        self.p.setYRange(-hi, hi, padding=0)
