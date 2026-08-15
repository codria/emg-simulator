"""Main window: composes the 3D scene, EMG bars and waveform panel, runs the
per-frame loop (engine.step), and wires manual input (keyboard + sliders).

Layout (per the display decisions):
    [ left bar ] [ 3D scene ] [ waveforms (top=R, bottom=L) + drive sliders ] [ right bar ]

Controls (development / dummy input):
    hold F / J  → flex left / right arm      B → capture baseline (力を抜いて)
    sliders     → set left / right drive      R → reset session   D → toggle attract/demo
"""

from __future__ import annotations

import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .. import watchdog
from . import theme
from .scene3d import Scene3D
from .bars import BarWidget
from .waveform import WaveformPlot
from .sound import Sfx

_RAMP_PER_SEC = 3.0
_KEY_LEFT = "F"
_KEY_RIGHT = "J"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, engine, cfg):
        super().__init__()
        self.engine = engine
        self.cfg = cfg
        self.setWindowTitle("EMG ロボットアーム 到達ゲーム — Created by Maeda")

        self._keys: set[str] = set()
        self._key_drive = np.zeros(2)
        self._target_age = 0.0

        left_is_theta = cfg.control.left_axis == "theta"
        self.bar_left = BarWidget("Left", "向き θ" if left_is_theta else "伸び r", cfg, theme.L_COLOR)
        self.bar_right = BarWidget("Right", "伸び r" if left_is_theta else "向き θ", cfg, theme.R_COLOR)
        self.scene = Scene3D(cfg)
        self.wave_left = WaveformPlot("Left Arm EMG", theme.L_COLOR, cfg)
        self.wave_right = WaveformPlot("Right Arm EMG", theme.R_COLOR, cfg)
        # real WAV if present (exhibit machine), else a synthesized fresh-clone fallback
        self.sfx = Sfx(cfg.ui.sfx_reach, cfg.ui.sfx_volume, synth="reach") if cfg.ui.sfx_enabled else Sfx(None)
        self.sfx_enter = Sfx(cfg.ui.sfx_enter, cfg.ui.sfx_volume, synth="enter") if cfg.ui.sfx_enabled else Sfx(None)
        self._prev_hold_frac = 0.0     # rising edge of hold_frac = tip entered the zone

        self.sl_left = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.sl_right = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        for s in (self.sl_left, self.sl_right):
            s.setRange(0, 100)
            s.valueChanged.connect(lambda _v: self.engine.notify_user_input())

        self._build_layout()

        self.status = QtWidgets.QLabel()
        self.statusBar().addWidget(self.status)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        # App-wide key handling so F/J/B/R/D/S work no matter which child widget
        # (slider, GL view, waveform plot) currently holds focus.
        QtWidgets.QApplication.instance().installEventFilter(self)

        self._elapsed = QtCore.QElapsedTimer()
        self._elapsed.start()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(16)

    def _build_layout(self) -> None:
        # Two rows to keep each arm's widgets together (less eye travel):
        #   row 1: [ left bar | 3D | right bar ]
        #   row 2: [ left graph | drive | right graph ]
        # The two rows have independent column widths (they don't align) so the
        # window stays compact.
        central = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)

        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self.bar_left)
        row1.addWidget(self.scene, 1)
        row1.addWidget(self.bar_right)

        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self.wave_left, 1)
        srow = QtWidgets.QHBoxLayout()
        srow.addWidget(QtWidgets.QLabel("L"))
        srow.addWidget(self.sl_left)
        srow.addWidget(self.sl_right)
        srow.addWidget(QtWidgets.QLabel("R"))
        sbox = QtWidgets.QGroupBox("drive (dummy)")
        sbox.setLayout(srow)
        sbox.setFixedWidth(150)
        row2.addWidget(sbox)
        row2.addWidget(self.wave_right, 1)

        outer.addLayout(row1, 3)
        outer.addLayout(row2, 2)
        self.setCentralWidget(central)

    # -- loop --------------------------------------------------------------
    def _on_timer(self) -> None:
        # When a dialog (Settings/Connection) or another app holds focus, ease the
        # render rate right down so the shared UI thread stays responsive to that
        # window instead of freezing under the 60 fps 3D repaint. The arm keeps
        # animating (slower), so tuning still shows its effect live.
        watchdog.heartbeat()          # re-arm the deadlock dump; catches a permanent freeze
        want = 16 if self.isActiveWindow() else 55
        if self._timer.interval() != want:
            self._timer.setInterval(want)
        now = time.perf_counter()
        gap = now - getattr(self, "_wd_last", now)   # time since the previous frame ran
        self._wd_last = now
        dt = min(self._elapsed.restart() / 1000.0, 0.1)
        t0 = time.perf_counter()
        try:
            self.tick(dt)
        except Exception as exc:
            # A live exhibit must never die on one bad frame: log (rate-limited) and
            # keep looping. The next frame re-renders from the engine's current state.
            self._on_tick_error(exc)
        body = time.perf_counter() - t0
        # watchdog: only fires on a pathological stall (>1 s, never in a healthy run).
        # gap >> body → the main loop was starved (e.g. the poll thread held the GIL);
        # body large → a phase on this thread blocked — the split says which.
        if gap > 1.0 or body > 1.0:
            watchdog.warn(f"slow loop: gap={gap:.1f}s body={body:.2f}s "
                 f"(step={getattr(self, '_wd_step', 0.0):.2f} "
                 f"sfx={getattr(self, '_wd_sfx', 0.0):.2f} "
                 f"render={getattr(self, '_wd_refresh', 0.0):.2f}) "
                 f"buf={self._buf_len()} src={type(self.engine.source).__name__}")

    def _buf_len(self) -> int:
        """Approx queued-sample count of the current source (BioRadio), for the watchdog."""
        b = getattr(self.engine.source, "_buf", None)
        try:
            return min(len(b[0]), len(b[1])) if b else -1
        except Exception:
            return -1

    def _on_tick_error(self, exc: Exception) -> None:
        """A frame raised. Log the first occurrence with a traceback, then rate-limit
        (once per ~5 s) so a persistent error can't flood the log — the loop lives on."""
        import traceback
        n = getattr(self, "_tick_err_n", 0) + 1
        self._tick_err_n = n
        now = time.perf_counter()
        if n == 1 or now - getattr(self, "_tick_err_last", -1e9) > 5.0:
            self._tick_err_last = now
            watchdog.warn(f"tick error #{n} (loop continues): {exc!r}\n{traceback.format_exc()}")

    def tick(self, dt: float) -> None:
        if not self.engine.attract:
            for ch, key in enumerate((_KEY_LEFT, _KEY_RIGHT)):
                if key in self._keys:
                    self._key_drive[ch] = min(1.0, self._key_drive[ch] + _RAMP_PER_SEC * dt)
                else:
                    self._key_drive[ch] = max(0.0, self._key_drive[ch] - _RAMP_PER_SEC * dt)
            sl = np.array([self.sl_left.value() / 100.0, self.sl_right.value() / 100.0])
            drive = np.clip(np.maximum(sl, self._key_drive), 0.0, 1.0)
            if hasattr(self.engine.source, "set_drive"):
                self.engine.source.set_drive(drive[0], drive[1])

        t_step = time.perf_counter()
        ev = self.engine.step(dt)
        self._wd_step = time.perf_counter() - t_step
        t_sfx = time.perf_counter()
        hit = ev in ("reached", "round_complete")
        if hit:
            self._target_age = 0.0
            self.sfx.play()
        else:
            self._target_age += dt
        # rising edge of hold_frac (0 → >0) = the tip just entered the target zone
        hf = self.engine.game.hold_frac
        if hf > 1e-6 and self._prev_hold_frac <= 1e-6:
            self.sfx_enter.play()
        self._prev_hold_frac = hf
        self._wd_sfx = time.perf_counter() - t_sfx
        t_ref = time.perf_counter()
        self._refresh(dt, hit)
        self._wd_refresh = time.perf_counter() - t_ref

    def _refresh(self, dt: float = 0.0, hit_flash: bool = False) -> None:
        eng, cfg = self.engine, self.cfg
        # green wedge = the game's reach target (fixed until reached). hold_frac drives
        # the in-zone "charge"; hit_flash pops the completion flash at the old target.
        self.scene.update_state(eng.control.arm, eng.game.target_xyz, eng.tip,
                                eng.game.hold_frac, hit_flash, dt)
        self.wave_left.update_state(eng.waveform(0), eng.amp_history(0),
                                    eng.norm.baseline[0], eng.norm.scale[0], eng.norm.peak[0])
        self.wave_right.update_state(eng.waveform(1), eng.amp_history(1),
                                     eng.norm.baseline[1], eng.norm.scale[1], eng.norm.peak[1])

        # Bars show the REACH FRACTION a_eff = activation / full_ref (0 = r_min/θ_min,
        # 1 = r_max/θ_max) — i.e. what the arm actually drives to, so a full drive
        # fills the bar to ~1 at any sat_gain. (Raw activation caps below 1 at low
        # sat_gain and then looks like it disagrees with the arm.) Marker = the
        # target's fraction; matching the fill to the marker puts the arm on target.
        full = eng.control.full_ref()
        a_eff = np.clip(eng.activation / full, 0.0, 1.0)
        r_t, th_t = eng.game.target_rt
        m_r = (r_t - cfg.control.r_min) / max(1e-6, cfg.control.r_max - cfg.control.r_min)
        m_th = (th_t - cfg.control.theta_min) / max(1e-6, cfg.control.theta_max - cfg.control.theta_min)
        # The target is an (r,θ) box (fan wedge), so each bar band is EXACTLY the
        # target's extent on that axis — full width = 2·tolerance, no r_t-dependent
        # arc approximation. Band, 3D wedge, and hit test are now one and the same.
        band_r = 2 * cfg.game.reach_r / max(1e-6, cfg.control.r_max - cfg.control.r_min)
        band_th = 2 * np.radians(cfg.game.reach_theta_deg) / \
            max(1e-6, cfg.control.theta_max - cfg.control.theta_min)
        if cfg.ui.marker_enabled and not eng.attract:
            alpha = float(np.clip((self._target_age - cfg.ui.marker_delay_sec) / 1.0, 0.0, 1.0))
        else:
            alpha = 0.0
        hold = eng.game.hold_frac
        if cfg.control.left_axis == "theta":
            self.bar_left.set_state(a_eff[0], m_th, alpha, hold, band_th)
            self.bar_right.set_state(a_eff[1], m_r, alpha, hold, band_r)
        else:
            self.bar_left.set_state(a_eff[0], m_r, alpha, hold, band_r)
            self.bar_right.set_state(a_eff[1], m_th, alpha, hold, band_th)

        g = eng.game
        parts = [f"到達 {g.reached}/{cfg.game.targets_per_round}", f"時間 {g.round_time:4.1f}s"]
        if g.last_round_time is not None:
            parts.append(f"前回 {g.last_round_time:4.1f}s")
        if eng.norm.capturing:
            parts.append("● ベースライン取得中 (力を抜いて)")
        if eng.attract:
            parts.append("● ATTRACT / デモ (何か操作で解除)")
        else:
            parts.append("F/J=力む  B=較正  R=リセット  P=姿勢戻し  D=デモ  S=設定  C=接続")
        self.status.setText("     ".join(parts))

    # -- input -------------------------------------------------------------
    # Keys handled globally (see eventFilter). Use key codes, not text(), so IME
    # / focused widgets can't swallow or rewrite them.
    _KEYMAP = {
        QtCore.Qt.Key.Key_F: "F",
        QtCore.Qt.Key.Key_J: "J",
        QtCore.Qt.Key.Key_B: "B",
        QtCore.Qt.Key.Key_R: "R",
        QtCore.Qt.Key.Key_D: "D",
        QtCore.Qt.Key.Key_S: "S",
        QtCore.Qt.Key.Key_C: "C",
        QtCore.Qt.Key.Key_P: "P",
    }

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if t in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            k = self._KEYMAP.get(event.key())
            if k is not None:
                self._handle_key(k, t == QtCore.QEvent.Type.KeyPress, event.isAutoRepeat())
                return True  # consume so the focused widget doesn't also react
        return super().eventFilter(obj, event)

    def _handle_key(self, k: str, pressed: bool, autorepeat: bool) -> None:
        if autorepeat:
            return
        if not pressed:
            self._keys.discard(k)
            return
        if k in ("F", "J"):
            self._keys.add(k)
            self.engine.notify_user_input()
        elif k == "B":
            self._start_baseline()  # notifies internally
        elif k == "R":
            self.engine.reset_session()
            self.engine.notify_user_input()
        elif k == "D":
            self.engine.set_attract(not self.engine.attract)
        elif k == "S":
            self._open_settings()
            self.engine.notify_user_input()
        elif k == "C":
            self._open_connection()
            self.engine.notify_user_input()
        elif k == "P":
            self.engine.reset_pose()      # re-home the arm (recover a flipped pose)

    def _start_baseline(self) -> None:
        self.engine.start_baseline()
        QtCore.QTimer.singleShot(
            int(self.cfg.normalize.baseline_sec * 1000), self.engine.finish_baseline
        )

    def _open_settings(self) -> None:
        if getattr(self, "_settings", None) is None:
            from .settings import SettingsDialog
            self._settings = SettingsDialog(self.engine, self.cfg, self)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _open_connection(self) -> None:
        if getattr(self, "_connection", None) is None:
            from .connection import ConnectionDialog
            self._connection = ConnectionDialog(self.engine, self.cfg, self)
        self._connection.show()
        self._connection.raise_()
        self._connection.activateWindow()
