"""Application entry point.

    python -m emg_sim.app                 # interactive
    python -m emg_sim.app --auto          # start in attract/demo mode
    python -m emg_sim.app --screenshot out.png [--frames 240]
"""

from __future__ import annotations

import argparse
import sys

from PySide6 import QtWidgets

from .config import Config
from .engine import Engine
from .ui.main_window import MainWindow


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EMG robot-arm reaching game (MVP)")
    ap.add_argument("--config", help="path to a Config JSON")
    ap.add_argument("--screenshot", metavar="PNG", help="render N frames, save a PNG, exit")
    ap.add_argument("--frames", type=int, default=240)
    ap.add_argument("--auto", action="store_true", help="start in attract/demo mode")
    args = ap.parse_args(argv)

    cfg = Config.load(args.config) if args.config else Config()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

    eng = Engine(cfg)
    if args.auto or args.screenshot:
        eng.set_attract(True)

    win = MainWindow(eng, cfg)
    win.resize(1180, 700)
    win.show()

    if args.screenshot:
        win._timer.stop()  # step deterministically for a reproducible frame
        for _ in range(args.frames):
            win.tick(1 / 60)
            app.processEvents()
        app.processEvents()
        win.grab().save(args.screenshot)
        print("saved screenshot:", args.screenshot)
        return 0

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
