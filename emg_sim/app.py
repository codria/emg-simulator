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
    ap.add_argument("--bioradio", metavar="DLL",
                    help="use a real BioRadio via this BioRadioSDK.dll (default: dummy input)")
    ap.add_argument("--mac", help="BioRadio MAC as hex (with --bioradio); default: first found")
    ap.add_argument("--device", help="BioRadio device name to match (with --bioradio)")
    ap.add_argument("--list-devices", action="store_true",
                    help="with --bioradio: scan, print devices, exit")
    args = ap.parse_args(argv)

    cfg = Config.load(args.config) if args.config else Config()

    if args.list_devices:
        if not args.bioradio:
            ap.error("--list-devices requires --bioradio <DLL>")
        from .acquisition import discover
        for name, mac in discover(args.bioradio):
            print(f"{mac:012X}\t{name}")
        return 0

    source = None
    if args.bioradio:
        from .acquisition import BioRadioSource
        source = BioRadioSource(args.bioradio,
                                mac_id=int(args.mac, 16) if args.mac else None,
                                device_id=args.device)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

    eng = Engine(cfg, source=source)
    if args.auto or args.screenshot:
        eng.set_attract(True)

    try:
        eng.source.start()               # no-op for dummy; connects a real BioRadio
    except Exception as e:
        print(f"acquisition start failed: {e}", file=sys.stderr)
        return 2
    app.aboutToQuit.connect(eng.source.stop)

    win = MainWindow(eng, cfg)
    win.resize(1200, 780)
    win.show()

    if args.screenshot:
        win._timer.stop()  # step deterministically for a reproducible frame
        for _ in range(args.frames):
            win.tick(1 / 60)
            app.processEvents()
        app.processEvents()
        win.grab().save(args.screenshot)
        print("saved screenshot:", args.screenshot)
        eng.source.stop()
        return 0

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
