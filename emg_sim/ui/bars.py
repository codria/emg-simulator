"""EMG activation bar with target marker (band + delayed fade-in).

The bar shows the normalized activation actually used for control (§5.5). The
target marker is a translucent band at the activation the current target needs;
it fades in only after a delay (config) so the player gets a moment to explore
first. Marker is position-control only (the app passes alpha=0 to hide it).
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

_DISPLAY_MAX = 1.15  # bar top = a bit above 1.0 so soft-sat over-range shows


class BarWidget(QtWidgets.QWidget):
    def __init__(self, side: str, role: str, cfg):
        super().__init__()
        self.side = side          # "L" / "R"
        self.role = role          # "向き(θ)" / "伸び(r)"
        self.cfg = cfg
        self.value = 0.0          # activation
        self.target = None        # target activation [0,1] or None
        self.marker_alpha = 0.0
        self.hold_frac = 0.0
        self.setFixedWidth(88)
        self.setMinimumHeight(240)

    def set_state(self, value, target, marker_alpha, hold_frac=0.0) -> None:
        self.value = float(value)
        self.target = None if target is None else float(target)
        self.marker_alpha = float(marker_alpha)
        self.hold_frac = float(hold_frac)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        pad_top, pad_bot, pad_x = 34, 30, 20
        bx, by = pad_x, pad_top
        bw, bh = w - 2 * pad_x, h - pad_top - pad_bot

        def y_of(a: float) -> float:
            return by + bh * (1.0 - min(max(a, 0.0), _DISPLAY_MAX) / _DISPLAY_MAX)

        # track
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(45, 48, 58))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bw, bh), 6, 6)

        # fill
        fill_top = y_of(self.value)
        grad = QtGui.QLinearGradient(0, by + bh, 0, by)
        grad.setColorAt(0.0, QtGui.QColor(70, 150, 240))
        grad.setColorAt(0.75, QtGui.QColor(120, 200, 255))
        grad.setColorAt(1.0, QtGui.QColor(255, 170, 90))
        p.setBrush(grad)
        p.drawRoundedRect(QtCore.QRectF(bx, fill_top, bw, by + bh - fill_top), 6, 6)

        # 1.0 reference line
        p.setPen(QtGui.QPen(QtGui.QColor(200, 200, 210, 140), 1, QtCore.Qt.PenStyle.DashLine))
        y1 = y_of(1.0)
        p.drawLine(int(bx), int(y1), int(bx + bw), int(y1))

        # target marker band (delayed fade-in)
        if self.target is not None and self.marker_alpha > 0.01:
            band = max(0.03, self.cfg.game.reach_dist /
                       max(1e-6, self.cfg.control.r_max - self.cfg.control.r_min))
            yc = y_of(self.target)
            hh = bh * band / _DISPLAY_MAX
            a = int(200 * self.marker_alpha)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(120, 255, 150, int(70 * self.marker_alpha)))
            p.drawRect(QtCore.QRectF(bx, yc - hh / 2, bw, hh))
            p.setPen(QtGui.QPen(QtGui.QColor(150, 255, 170, a), 2))
            p.drawLine(int(bx), int(yc), int(bx + bw), int(yc))

        # labels
        p.setPen(QtGui.QColor(230, 230, 235))
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, 4, w, 22), QtCore.Qt.AlignmentFlag.AlignCenter, self.side)
        f.setPointSize(9)
        f.setBold(False)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, h - pad_bot + 4, w, 22),
                   QtCore.Qt.AlignmentFlag.AlignCenter, self.role)
