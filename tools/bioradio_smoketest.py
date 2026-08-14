"""On-site bring-up smoketest for a real BioRadio.

Run this on the exhibit PC with the device powered on and Bluetooth-paired to
confirm the acquisition path end-to-end before wiring it into the app:

    python tools/bioradio_smoketest.py <path/to/BioRadioSDK.dll> [--seconds 5] [--mac HEX] [--device NAME]

It discovers devices, connects, streams for a few seconds and prints per-channel
stats (configured sample rate, samples actually received, effective rate, value
range). Prerequisite: the two EMG (BioPotential) channels must be programmed on
the device in BioCapture first — otherwise there are no channels to read.

With no device attached it just prints "no devices" and exits 0, which still
exercises the discover path (and the DLL load).

Get the free SDK from:
  https://www.glneurotech.com/products/bioradio/support/software-downloads/
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

# allow running as a plain script (python tools/bioradio_smoketest.py ...)
sys.path.insert(0, ".")
from emg_sim.acquisition import BioRadioSource, discover  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BioRadio acquisition smoketest")
    ap.add_argument("dll", help="path to BioRadioSDK.dll")
    ap.add_argument("--seconds", type=float, default=5.0, help="stream duration")
    ap.add_argument("--mac", help="MAC as hex (default: first device found)")
    ap.add_argument("--device", help="device name to match")
    a = ap.parse_args(argv)

    print("scanning for BioRadio devices...")
    devices = discover(a.dll)
    print(f"  found {len(devices)}: " + (", ".join(f"{n} ({m:012X})" for n, m in devices) or "-"))
    if not devices and a.mac is None:
        print("no devices — power on + Bluetooth-pair the BioRadio (2.1+ adapter), then retry.")
        return 0

    src = BioRadioSource(a.dll,
                         mac_id=int(a.mac, 16) if a.mac else None,
                         device_id=a.device)
    src.start()
    print(f"connected. configured sample_rate = {src.sample_rate} Hz. streaming {a.seconds:.0f} s...")

    n = 0
    lo = np.array([np.inf, np.inf])
    hi = np.array([-np.inf, -np.inf])
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < a.seconds:
            time.sleep(0.05)
            chunk = src.read(0.05)
            if chunk.size:
                n += chunk.shape[0]
                lo = np.minimum(lo, chunk.min(axis=0))
                hi = np.maximum(hi, chunk.max(axis=0))
    finally:
        src.stop()

    dur = time.monotonic() - t0
    print(f"  received {n} samples/ch in {dur:.1f}s  (~{n / dur:.0f} Hz effective)")
    if n:
        print(f"  L range [{lo[0]:+.4g}, {hi[0]:+.4g}] V     R range [{lo[1]:+.4g}, {hi[1]:+.4g}] V")
        print("OK — acquisition works. Wire it in with:  python -m emg_sim.app --bioradio <dll> [--mac ...]")
    else:
        print("connected but received 0 samples — are the EMG channels programmed in BioCapture?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
