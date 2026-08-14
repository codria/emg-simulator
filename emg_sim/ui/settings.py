"""Settings dialog — live-tunable sliders + JSON save/load.

Sliders mutate the Config dataclasses *in place*, so the running engine
components (which hold references to the sub-configs) pick up changes
immediately. Changing the RMS window / EMA rebuilds the DSP pipeline.
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

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


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, engine, cfg, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = cfg
        self.setWindowTitle("設定 (Settings)")
        self.setModal(False)

        lay = QtWidgets.QVBoxLayout(self)
        rebuild = engine.rebuild_dsp
        specs = [
            ("RMS 窓 (ms)", cfg.signal, "rms_window_ms", 50, 400, 0, rebuild),
            ("EMA α", cfg.signal, "ema_alpha", 0.05, 1.0, 2, rebuild),
            ("ソフト飽和 gain", cfg.normalize, "sat_gain", 0.5, 3.0, 2, None),
            ("オンライン適応率", cfg.normalize, "adapt_rate", 0.0, 0.2, 3, None),
            ("r_min", cfg.control, "r_min", 0.34, 0.55, 2, None),
            ("r_max", cfg.control, "r_max", 0.40, 0.64, 2, None),
            ("到達距離 (m)", cfg.game, "reach_dist", 0.02, 0.12, 3, None),
            ("滞在時間 (s)", cfg.game, "hold_sec", 0.1, 1.0, 2, None),
            ("マーカー遅延 (s)", cfg.ui, "marker_delay_sec", 0.0, 8.0, 1, None),
        ]
        self.rows = []
        for label, obj, attr, lo, hi, dec, cb in specs:
            row = _SliderRow(label, obj, attr, lo, hi, dec, cb)
            self.rows.append(row)
            lay.addWidget(row)

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
        self.resize(440, 380)

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
