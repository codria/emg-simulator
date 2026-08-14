"""Settings dialog — live-tunable sliders + JSON save/load.

Sliders mutate the Config dataclasses *in place*, so the running engine
components (which hold references to the sub-configs) pick up changes
immediately. Changing the RMS window / EMA rebuilds the DSP pipeline.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import Config

_USER_CFG = Path("config") / "user.json"


class _SliderRow(QtWidgets.QWidget):
    def __init__(self, label, obj, attr, lo, hi, decimals=2, on_change=None):
        super().__init__()
        self.obj, self.attr, self.lo, self.hi = obj, attr, lo, hi
        self.decimals, self.on_change = decimals, on_change
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        name = QtWidgets.QLabel(label)
        name.setMinimumWidth(140)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.val = QtWidgets.QLabel()
        self.val.setMinimumWidth(56)
        self.val.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(name)
        h.addWidget(self.slider, 1)
        h.addWidget(self.val)
        self.refresh()
        self.slider.valueChanged.connect(self._changed)

    def _to_slider(self, value):
        return int(round((value - self.lo) / (self.hi - self.lo) * 1000))

    def _changed(self, v):
        value = round(self.lo + (v / 1000.0) * (self.hi - self.lo), self.decimals)
        setattr(self.obj, self.attr, value)
        self.val.setText(f"{value:.{self.decimals}f}")
        if self.on_change:
            self.on_change()

    def refresh(self):
        cur = getattr(self.obj, self.attr)
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(cur))
        self.slider.blockSignals(False)
        self.val.setText(f"{cur:.{self.decimals}f}")


class _SatCurve(QtWidgets.QWidget):
    """Live preview of the soft-saturation curve  activation = tanh(gain · x)."""

    def __init__(self):
        super().__init__()
        self.gain = 1.6
        self.setFixedHeight(108)

    def set_gain(self, g: float) -> None:
        self.gain = float(g)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        x0, y0, x1, y1 = 26, h - 16, w - 10, 20        # plot area (y0 bottom, y1 top)
        xmax = 2.0
        p.fillRect(self.rect(), QtGui.QColor("#12141a"))         # black background
        p.setPen(QtGui.QPen(QtGui.QColor("#d7dbe4"), 1))         # white frame
        p.drawRect(x0, y1, x1 - x0, y0 - y1)

        def sx(v):
            return x0 + (v / xmax) * (x1 - x0)

        def sy(v):
            return y0 + v * (y1 - y0)                   # v in 0..1

        p.setPen(QtGui.QPen(QtGui.QColor("#3b3f4b"), 1, QtCore.Qt.PenStyle.DashLine))  # dim grid
        for g in (0.5, 1.0):
            p.drawLine(x0, int(sy(g)), x1, int(sy(g)))
        xf = int(sx(1.0))
        p.drawLine(xf, y0, xf, y1)                      # x = 1 (満力比)

        p.setPen(QtGui.QColor("#d0d4de"))                        # white labels
        f = p.font()
        f.setPointSize(7)
        p.setFont(f)
        p.drawText(6, int(sy(1.0)) + 4, "1")
        p.drawText(6, int(sy(0.0)) + 2, "0")
        p.drawText(xf - 8, y0 + 13, "満力")

        path = QtGui.QPainterPath()
        for i in range(65):
            xv = xmax * i / 64
            pt = QtCore.QPointF(sx(xv), sy(math.tanh(self.gain * xv)))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QtGui.QPen(QtGui.QColor("#4d9fff"), 2))         # blue curve
        p.drawPath(path)

        p.setPen(QtGui.QColor("#c2c7d2"))                        # white title
        p.drawText(x0, y1 - 6, f"効きカーブ  tanh({self.gain:.2f}·x)   横=力み比 / 縦=活性度")


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, engine, cfg, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = cfg
        self.setWindowTitle("設定 (Settings)")
        self.setModal(False)

        lay = QtWidgets.QVBoxLayout(self)
        rebuild = engine.rebuild_dsp
        # bold section titles; keep the slider rows themselves normal weight
        self.setStyleSheet(
            "QGroupBox { font-weight: bold; margin-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QGroupBox QLabel { font-weight: normal; }"
        )
        # sliders grouped under headings (each group ≈ one config section)
        groups = [
            ("平滑化・正規化", [
                ("RMS 窓 (ms)", cfg.signal, "rms_window_ms", 10, 600, 0, rebuild),
                ("EMA α", cfg.signal, "ema_alpha", 0.05, 1.0, 2, rebuild),
                ("ソフト飽和 gain", cfg.normalize, "sat_gain", 0.5, 3.0, 2, None),
                ("オンライン適応率", cfg.normalize, "adapt_rate", 0.0, 0.2, 3, None),
                ("scale 下限 (小=高感度)", cfg.normalize, "fallback_scale", 0.1, 1.0, 2, None),
                ("peak 半減期 (s)", cfg.normalize, "peak_halflife_sec", 3.0, 180.0, 1, None),
            ]),
            ("操作範囲・アーム", [
                ("r_min", cfg.control, "r_min", 0.23, 0.60, 2, lambda: self._clamp_r("r_min")),
                ("r_max", cfg.control, "r_max", 0.30, 0.90, 2, lambda: self._clamp_r("r_max")),
                ("肘 near (畳み)", cfg.control, "elbow_target_near", 1.0, 3.0, 2, None),
                ("肘 far (伸展)", cfg.control, "elbow_target_far", 0.0, 1.0, 2, None),
            ]),
            ("ターゲッティング", [
                ("目標マージン (端除外)", cfg.game, "target_margin", 0.0, 0.4, 2, None),
                ("到達 r 許容 (m)", cfg.game, "reach_r", 0.02, 0.12, 3, None),
                ("到達 θ 許容 (deg)", cfg.game, "reach_theta_deg", 1.0, 30.0, 1, None),
                ("滞在時間 (s)", cfg.game, "hold_sec", 0.1, 1.0, 2, None),
                ("マーカー遅延 (s)", cfg.ui, "marker_delay_sec", 0.0, 8.0, 1, None),
            ]),
        ]
        self.rows = []
        self.sat_curve = _SatCurve()                 # live tanh preview under the gain slider
        for title, specs in groups:
            box = QtWidgets.QGroupBox(title)
            v = QtWidgets.QVBoxLayout(box)
            v.setSpacing(4)
            for label, obj, attr, lo, hi, dec, cb in specs:
                if attr == "sat_gain":
                    cb = lambda: self.sat_curve.set_gain(cfg.normalize.sat_gain)
                row = _SliderRow(label, obj, attr, lo, hi, dec, cb)
                self.rows.append(row)
                v.addWidget(row)
                if attr == "sat_gain":
                    v.addWidget(self.sat_curve)
            lay.addWidget(box)
        self.sat_curve.set_gain(cfg.normalize.sat_gain)   # initial draw

        btns = QtWidgets.QHBoxLayout()
        b_save = QtWidgets.QPushButton("保存")
        b_load = QtWidgets.QPushButton("読込")
        b_save.clicked.connect(self._save)
        b_load.clicked.connect(self._load)
        self.status = QtWidgets.QLabel()
        btns.addWidget(b_save)
        btns.addWidget(b_load)
        btns.addWidget(self.status, 1)
        lay.addLayout(btns)
        lay.addStretch(1)
        self.resize(480, 650)

    def _clamp_r(self, which: str) -> None:
        c = self.cfg.control
        if which == "r_min" and c.r_min > c.r_max:
            c.r_min = c.r_max
        elif which == "r_max" and c.r_max < c.r_min:
            c.r_max = c.r_min
        for row in self.rows:
            if row.attr in ("r_min", "r_max"):
                row.refresh()

    def _save(self):
        _USER_CFG.parent.mkdir(exist_ok=True)
        self.cfg.save(_USER_CFG)
        self.status.setText(f"保存: {_USER_CFG}")

    def _load(self):
        if not _USER_CFG.exists():
            self.status.setText("保存ファイルがありません")
            return
        loaded = Config.load(_USER_CFG)
        # copy fields in place so live references stay valid
        for sec in ("signal", "normalize", "control", "game", "ui"):
            src, dst = getattr(loaded, sec), getattr(self.cfg, sec)
            for f in vars(src):
                setattr(dst, f, getattr(src, f))
        self.engine.rebuild_dsp()
        for row in self.rows:
            row.refresh()
        self.status.setText(f"読込: {_USER_CFG}")
