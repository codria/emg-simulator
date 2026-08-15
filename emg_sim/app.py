"""Application entry point.

    python -m emg_sim.app                 # interactive
    python -m emg_sim.app --auto          # start in attract/demo mode
    python -m emg_sim.app --screenshot out.png [--frames 240]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6 import QtGui, QtWidgets

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
    ap.add_argument("--light", action="store_true",
                    help="lightweight mode for weak / integrated-GPU machines: "
                         "no waveforms and no MSAA (the biggest per-frame costs)")
    args = ap.parse_args(argv)

    if args.config:
        cfg = Config.load_or_default(args.config)
    else:
        # Restore the last saved setup (DLL path, device, tuning) so it persists across
        # launches without retyping — the Connection/Settings dialogs write this file.
        _user = Path("config") / "user.json"
        cfg = Config.load_or_default(str(_user)) if _user.exists() else Config()

    # CLI selects the launch source; the in-app Connection dialog (C key) can switch
    # at runtime. With --bioradio the CLI wins; without it we keep whatever the config
    # restored — dummy by default, or a saved BioRadio setup so the exhibit
    # auto-reconnects to the same device on launch (falling back to dummy below if it
    # can't start).
    if args.bioradio:
        cfg.acquisition.source = "bioradio"
        cfg.acquisition.dll_path = args.bioradio
        if args.mac:
            cfg.acquisition.mac_hex = args.mac
        if args.device:
            cfg.acquisition.device = args.device

    if args.light:                          # weak-machine overrides (biggest per-frame costs)
        cfg.ui.show_waveform = False
        cfg.ui.msaa = 0

    if args.list_devices:
        if not cfg.acquisition.dll_path:
            ap.error("--list-devices requires --bioradio <DLL>")
        from .acquisition import discover
        for name, mac in discover(cfg.acquisition.dll_path):
            print(f"{mac:012X}\t{name}")
        return 0

    from .acquisition import make_source
    source = make_source(cfg)

    fmt = QtGui.QSurfaceFormat()
    if cfg.ui.msaa > 0:                   # MSAA for the 3D scene (0 = off, for weak GPUs)
        fmt.setSamples(cfg.ui.msaa)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

    eng = Engine(cfg, source=source)
    if args.auto or args.screenshot:
        eng.set_attract(True)

    try:
        eng.start_source()               # connect + adopt the device's real rate
    except Exception as e:
        # A saved device that isn't on (e.g. launching away from the exhibit) fails
        # here — that's fine, we fall back to dummy. Collapse the pythonnet/.NET
        # exception to one line (its full stack trace looks alarming but isn't a bug).
        msg = str(e).splitlines()[0].split(" ---> ")[0].strip() or repr(e)
        print(f"BioRadio auto-connect failed ({msg}); starting on dummy input. Turn the "
              f"device on and reconnect from the Connection (C) dialog.", file=sys.stderr)
        from .acquisition import DummySource
        try:
            eng.set_source(DummySource(cfg, mode="auto" if eng.attract else "manual"))
        except Exception as e2:
            print(f"dummy fallback also failed: {e2}", file=sys.stderr)
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
