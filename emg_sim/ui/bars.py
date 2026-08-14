"""EMG reach bar with target marker (band + delayed fade-in).

The bar shows the reach fraction (0 = inner edge / θ_min, 1 = full reach) the arm
is driving to — a_eff = activation / full_ref — so it matches the arm at any
sat_gain. The target marker is a translucent band at the target's reach fraction;
it fades in only after a delay (config) so the player gets a moment to explore
first. Marker is position-control only (the app passes alpha=0 to hide it).
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

_DISPLAY_MAX = 1.0   # clean 0–1 reach fraction (a_eff is already clipped to [0, 1])


class BarWidget(QtWidgets.QWidget):
    def __init__(self, side: str, role: str, cfg, color=(120, 200, 255)):
        super().__init__()
        self.side = side          # "L" / "R"
        self.role = role          # "向き(θ)" / "伸び(r)"
        self.cfg = cfg
        self.color = color        # channel hue (RGB 0-255): R=cyan, L=yellow
        self.value = 0.0          # activation
        self.target = None        # target activation [0,1] or None
        self.marker_alpha = 0.0
        self.hold_frac = 0.0
        self.setFixedWidth(104)
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

        pad_top, pad_bot = 46, 30
        bx = 30                       # left margin holds the tick labels
        bw = w - bx - 12
        by = pad_top
        bh = h - pad_top - pad_bot

        def y_of(a: float) -> float:
            return by + bh * (1.0 - min(max(a, 0.0), _DISPLAY_MAX) / _DISPLAY_MAX)

        # track
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(45, 48, 58))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bw, bh), 6, 6)

        # fill — single-hue gradient (dark → channel colour)
        r, g, b = self.color
        fill_top = y_of(self.value)
        grad = QtGui.QLinearGradient(0, by + bh, 0, by)
        grad.setColorAt(0.0, QtGui.QColor(int(r * 0.33), int(g * 0.33), int(b * 0.38)))
        grad.setColorAt(1.0, QtGui.QColor(r, g, b))
        p.setBrush(grad)
        p.drawRoundedRect(QtCore.QRectF(bx, fill_top, bw, by + bh - fill_top), 6, 6)

        # scale: ticks at 0/.25/.5/.75/1.0, labels at 0/.5/1.0
        f = p.font()
        f.setPointSize(7)
        f.setBold(False)
        p.setFont(f)
        for a in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = y_of(a)
            major = a in (0.0, 0.5, 1.0)
            p.setPen(QtGui.QPen(QtGui.QColor(180, 185, 195, 170 if major else 90), 1))
            p.drawLine(int(bx - (6 if major else 3)), int(y), int(bx), int(y))
            if major:
                p.setPen(QtGui.QColor(190, 195, 205))
                p.drawText(QtCore.QRectF(0, y - 8, bx - 8, 16),
                           QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                           f"{a:.1f}")

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

        # top: side label + current value (tinted with the channel colour)
        chan = QtGui.QColor(r, g, b)
        p.setPen(chan)
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, 2, w, 18), QtCore.Qt.AlignmentFlag.AlignCenter, self.side)
        f.setPointSize(12)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, 22, w, 20), QtCore.Qt.AlignmentFlag.AlignCenter,
                   f"{self.value:.2f}")

        # bottom: role
        p.setPen(QtGui.QColor(220, 220, 228))
        f.setPointSize(9)
        f.setBold(False)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, h - pad_bot + 4, w, 22),
                   QtCore.Qt.AlignmentFlag.AlignCenter, self.role)
