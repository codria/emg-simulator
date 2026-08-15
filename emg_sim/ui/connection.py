"""Connection dialog (C key) — switch the input source live and test the link.

Toggle **Dummy** (keyboard/slider) vs a real **BioRadio**. For BioRadio: point at
the SDK DLL, *scan* for devices, pick one, and *apply* to connect. Applying swaps
the running engine's source (`engine.set_source`) — the DSP/normalizer keep their
state, only the raw-sample origin changes. If the connect fails, the current
source keeps running and the error is shown. "保存" persists the choice to the
same `config/user.json` the settings dialog uses.
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..acquisition import BioRadioSource, DummySource, discover, make_source

_USER_CFG = Path("config") / "user.json"
_OK, _ERR, _WARN = "#2f9e57", "#c0504d", "#b8860b"


def _short_err(e: Exception) -> str:
    """One-line summary of an exception. pythonnet/.NET errors carry a big stack
    trace (`場所 …` frames) we don't want filling the status label."""
    return str(e).splitlines()[0].split(" ---> ")[0].strip() or repr(e)


class ConnectionDialog(QtWidgets.QDialog):
    def __init__(self, engine, cfg, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = cfg
        self.setWindowTitle("接続 (Connection)")
        self.setModal(False)
        a = cfg.acquisition

        lay = QtWidgets.QVBoxLayout(self)

        # -- source toggle --------------------------------------------------
        self.rb_dummy = QtWidgets.QRadioButton("ダミー入力（キーボード / スライダ）")
        self.rb_bio = QtWidgets.QRadioButton("BioRadio 実機")
        (self.rb_bio if a.source == "bioradio" else self.rb_dummy).setChecked(True)
        lay.addWidget(self.rb_dummy)
        lay.addWidget(self.rb_bio)

        # -- BioRadio settings ---------------------------------------------
        self.box = QtWidgets.QGroupBox("BioRadio 設定")
        form = QtWidgets.QFormLayout(self.box)

        dll_row = QtWidgets.QHBoxLayout()
        self.ed_dll = QtWidgets.QLineEdit(a.dll_path)
        self.ed_dll.setPlaceholderText(r"...\API\BioRadioSDK.dll")
        b_browse = QtWidgets.QPushButton("参照…")
        b_browse.clicked.connect(self._browse)
        dll_row.addWidget(self.ed_dll, 1)
        dll_row.addWidget(b_browse)
        form.addRow("SDK DLL", dll_row)

        scan_row = QtWidgets.QHBoxLayout()
        self.b_scan = QtWidgets.QPushButton("スキャン")
        self.b_scan.clicked.connect(self._scan)
        self.cmb = QtWidgets.QComboBox()
        if a.mac_hex:                            # show the remembered device so the field
            try:                                 # isn't empty (re-connectable without a rescan)
                self.cmb.addItem(f"(保存済み)  {a.mac_hex}", int(a.mac_hex, 16))
            except ValueError:
                pass
        scan_row.addWidget(self.b_scan)
        scan_row.addWidget(self.cmb, 1)
        form.addRow("デバイス", scan_row)

        ch_row = QtWidgets.QHBoxLayout()
        self.sp_left = QtWidgets.QSpinBox()
        self.sp_left.setRange(0, 7)
        self.sp_left.setValue(a.left)
        self.sp_right = QtWidgets.QSpinBox()
        self.sp_right.setRange(0, 7)
        self.sp_right.setValue(a.right)
        ch_row.addWidget(QtWidgets.QLabel("左"))
        ch_row.addWidget(self.sp_left)
        ch_row.addSpacing(12)
        ch_row.addWidget(QtWidgets.QLabel("右"))
        ch_row.addWidget(self.sp_right)
        ch_row.addStretch(1)
        form.addRow("EMG ch", ch_row)
        lay.addWidget(self.box)

        # -- status + buttons ----------------------------------------------
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        # reserve ~2 lines (top-aligned) so a longer wrapped message doesn't grow the dialog
        self.status.setMinimumHeight(40)
        self.status.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.status)

        btns = QtWidgets.QHBoxLayout()
        self.b_apply = QtWidgets.QPushButton("適用（接続）")
        self.b_apply.clicked.connect(self._apply)
        self.b_disc = QtWidgets.QPushButton("接続解除")
        self.b_disc.setToolTip("BioRadio を切断してダミー入力に戻す（機器を解放）")
        self.b_disc.clicked.connect(self._disconnect)
        b_save = QtWidgets.QPushButton("保存")
        b_save.clicked.connect(self._save)
        b_close = QtWidgets.QPushButton("閉じる")
        b_close.clicked.connect(self.close)
        btns.addWidget(self.b_apply)
        btns.addWidget(self.b_disc)
        btns.addWidget(b_save)
        btns.addStretch(1)
        btns.addWidget(b_close)
        lay.addLayout(btns)

        self.rb_dummy.toggled.connect(lambda: self.box.setEnabled(self.rb_bio.isChecked()))
        self.box.setEnabled(self.rb_bio.isChecked())
        self._set_status(self._state_text(), _OK)
        # size to the content (>= its minimum) instead of a fixed 300 that Qt can't honor
        # (that mismatch is the "QWindowsWindow::setGeometry: Unable to set geometry" warning)
        self.setMinimumWidth(480)
        self.adjustSize()

    # -- helpers -----------------------------------------------------------
    def _state_text(self) -> str:
        src = type(self.engine.source).__name__
        if src == "BioRadioSource":
            return f"現在: BioRadio 接続中（{getattr(self.engine.source, 'sample_rate', '?')} Hz）"
        return "現在: ダミー入力"

    def _set_status(self, msg: str, color: str) -> None:
        self.status.setStyleSheet(f"color:{color};")
        self.status.setText(msg)

    # -- actions -----------------------------------------------------------
    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "BioRadioSDK.dll を選択", self.ed_dll.text(), "DLL (*.dll);;すべて (*)")
        if path:
            self.ed_dll.setText(path)

    def _scan(self) -> None:
        self._set_status("スキャン中…", _WARN)          # immediate feedback (scan blocks a few s)
        self.b_scan.setEnabled(False)
        QtWidgets.QApplication.processEvents()          # flush so the label paints before we block
        try:
            devices = discover(self.ed_dll.text().strip())
        except Exception as e:
            self._set_status(f"スキャン失敗: {_short_err(e)}", _ERR)
            return
        finally:
            self.b_scan.setEnabled(True)
        self.cmb.clear()
        for name, mac in devices:
            self.cmb.addItem(f"{name}  ({mac:012X})", mac)
        if devices:
            self._set_status(f"{len(devices)} 台見つかりました", _OK)
        else:
            self._set_status("デバイスが見つかりません（電源 / Bluetooth ペアリングを確認）", _ERR)

    def _apply(self) -> None:
        a = self.cfg.acquisition
        a.source = "bioradio" if self.rb_bio.isChecked() else "dummy"
        a.dll_path = self.ed_dll.text().strip()
        a.left, a.right = self.sp_left.value(), self.sp_right.value()
        if a.source == "bioradio" and self.cmb.currentData() is not None:
            a.mac_hex = f"{self.cmb.currentData():012X}"   # from the scanned/remembered selection
        # A BioRadio allows only ONE connection: re-applying while it's still held
        # fails with "occupied". Require an explicit disconnect first (button below).
        if a.source == "bioradio" and isinstance(self.engine.source, BioRadioSource):
            self._set_status("既に BioRadio 接続中です。再接続/切替は先に『接続解除』を押してください。", _WARN)
            return
        # Don't attempt a connect with no device chosen — it can only fail.
        if a.source == "bioradio" and self.cmb.currentData() is None:
            self._set_status("デバイスが選択されていません。『スキャン』して選択してください。", _WARN)
            return
        self._set_status("接続中…" if a.source == "bioradio" else "切替中…", _WARN)
        self.b_apply.setEnabled(False)
        QtWidgets.QApplication.processEvents()
        try:
            self.engine.set_source(make_source(self.cfg))
        except Exception as e:
            self._set_status(f"接続失敗: {_short_err(e)}", _ERR)
            return
        finally:
            self.b_apply.setEnabled(True)
        self._persist()                       # remember the setup so next launch reconnects
        self._set_status(self._state_text(), _OK)

    def _disconnect(self) -> None:
        if not isinstance(self.engine.source, BioRadioSource):
            self._set_status("BioRadio は接続されていません（ダミー入力中）。", _WARN)
            return
        self.b_disc.setEnabled(False)
        QtWidgets.QApplication.processEvents()
        try:
            self.engine.set_source(DummySource(self.cfg))   # stops the device, frees it
        except Exception as e:
            self._set_status(f"接続解除失敗: {_short_err(e)}", _ERR)
            return
        finally:
            self.b_disc.setEnabled(True)
        self.rb_dummy.setChecked(True)        # reflect the switch in the UI
        self._set_status("接続解除しました（ダミー入力）。再接続は数秒おいてから。", _OK)

    def _persist(self) -> None:
        """Save the current config (DLL path/device/tuning) so the setup survives a
        relaunch — best-effort, never blocks connecting."""
        try:
            _USER_CFG.parent.mkdir(exist_ok=True)
            self.cfg.save(_USER_CFG)
        except Exception:
            pass

    def _save(self) -> None:
        _USER_CFG.parent.mkdir(exist_ok=True)
        self.cfg.save(_USER_CFG)
        self._set_status(f"保存: {_USER_CFG}", _OK)
