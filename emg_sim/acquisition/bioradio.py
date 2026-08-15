"""Real BioRadio acquisition via the GLNeuroTech .NET SDK (pythonnet).

Grounded in the official Python example shipped with the SDK (392-0076 Rev A,
pythonnet 3.0.5) and verified on a dev box **without** a device attached:

  * `BioRadioSDK.dll` is AnyCPU / .NET Framework 4.5 (`arch=MSIL`) — it loads in
    64-bit Python under the `netfx` runtime, so no separate 32-bit process.
  * load → `BioRadioDeviceManager()` → `DiscoverBluetoothDevices()` all succeed
    with no hardware (discovery just returns an empty list).

The EMG channels are the device's **BioPotential** signal group; we take the
first two (left = 0, right = 1). `GetScaledValueArray()` returns the samples (in
volts) accumulated since the previous call and drains the SDK's buffer — exactly
the `InputSource.read(dt)` contract ("a real device ignores dt and drains its
buffer"), so we poll it directly per frame (same as the vendor example, which
polls from its main loop). If live testing shows the poll stalling the Qt loop,
move the poll to a worker thread + queue *inside this class* — nothing else
changes, that's the point of the `InputSource` seam.

Still hardware-only (can't be checked here): live streaming, firmware-1.0 match,
and that the two EMG channels are actually programmed on the device — configure
them in BioCapture (or via the SDK's SetConfiguration) beforehand, otherwise the
BioPotential group is empty.

The `pythonnet` import is deferred to `start()` so this module imports fine
without pythonnet (Windows-only dep) — tests and non-device machines are safe.
"""

from __future__ import annotations

import os
import threading
import time

import numpy as np

from .source import InputSource

_BIORADIO_NS = "GLNeuroTech.Devices.BioRadio"
_V_TO_MV = 1000.0   # GetScaledValueArray is volts; the app works in millivolts


def _ensure_clr():
    """Import `clr`, selecting the .NET Framework runtime first (must precede the
    very first `import clr` in the process)."""
    import sys

    if "clr" not in sys.modules:
        from pythonnet import load

        load("netfx")  # BioRadioSDK.dll targets .NET Framework 4.5
    import clr

    return clr


def discover(dll_path: str) -> list[tuple[str, int]]:
    """Scan for BioRadio devices; return `[(device_id, mac_id_int), ...]`.

    Handy for picking a device before constructing a `BioRadioSource`.
    """
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(f"BioRadioSDK.dll not found: {dll_path}")
    clr = _ensure_clr()
    clr.AddReference(dll_path)
    from GLNeuroTech.Devices.BioRadio import BioRadioDeviceManager  # type: ignore

    mgr = BioRadioDeviceManager()
    found = mgr.DiscoverBluetoothDevices()
    return [(str(found[i].DeviceId), int(str(found[i].MacId), 16))
            for i in range(found.Length)]


class BioRadioSource(InputSource):
    """`InputSource` backed by a real BioRadio over Bluetooth.

    Parameters
    ----------
    dll_path   : full path to `BioRadioSDK.dll` (from the free GLNeuroTech SDK).
    mac_id     : 64-bit MAC as int; if None, connect to the first device found
                 (optionally filtered by `device_id`).
    device_id  : device name to match during discovery (used when mac_id is None).
    left/right : which BioPotential channel indices map to left / right arm.
    """

    def __init__(self, dll_path: str, *, mac_id: int | None = None,
                 device_id: str | None = None, left: int = 0, right: int = 1):
        self.dll_path = dll_path
        self.mac_id = mac_id
        self.device_id = device_id
        self._left, self._right = left, right
        self._mgr = None
        self._dev = None
        self._bp = None  # BioPotentialSignals group
        # the device is polled on a background thread (so the Qt loop never blocks on
        # a pythonnet/BT call); read() just drains this lock-protected queue.
        self._lock = threading.Lock()
        self._buf = None            # [left_samples, right_samples], filled by the poll
        self._poll = None           # background poll thread
        self._stop = None           # Event that tells it to exit
        self._warned_backlog = False   # watchdog: only warn once per stall

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if not os.path.isfile(self.dll_path):
            raise FileNotFoundError(f"BioRadioSDK.dll not found: {self.dll_path}")
        clr = _ensure_clr()
        clr.AddReference(self.dll_path)
        from GLNeuroTech.Devices.BioRadio import BioRadioDeviceManager  # type: ignore

        self._mgr = BioRadioDeviceManager()

        mac = self.mac_id
        if mac is None:
            found = self._mgr.DiscoverBluetoothDevices()
            if found.Length < 1:
                raise RuntimeError(
                    "no BioRadio found — check the device is on, charged and "
                    "Bluetooth-paired (needs a 2.1+ adapter).")
            idx = 0
            if self.device_id is not None:
                names = [str(found[i].DeviceId) for i in range(found.Length)]
                if self.device_id not in names:
                    raise RuntimeError(f"device '{self.device_id}' not among {names}")
                idx = names.index(self.device_id)
            mac = int(str(found[idx].MacId), 16)

        self._dev = self._mgr.GetBluetoothDevice(mac)
        self._bp = self._dev.BioPotentialSignals
        need = max(self._left, self._right) + 1
        if self._bp.Count < need:
            raise RuntimeError(
                f"device exposes {self._bp.Count} BioPotential (EMG) channel(s); "
                f"need >= {need}. Program the EMG channels in BioCapture first.")

        # sample rate comes from the device's own configuration, not a guess
        self.sample_rate = int(self._bp.SamplesPerSecond)
        self._dev.StartAcquisition()

        self._buf = [[], []]
        self._stop = threading.Event()
        self._poll = threading.Thread(target=self._poll_loop, name="bioradio-poll", daemon=True)
        self._poll.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()                 # stop the poll thread before touching .NET
        if self._poll is not None:
            self._poll.join(timeout=1.0)
        self._poll = self._stop = None
        try:
            if self._dev is not None:
                self._dev.StopAcquisition()
                self._dev.Disconnect()
        finally:
            self._mgr = self._dev = self._bp = None
            with self._lock:
                self._buf = None

    # -- read --------------------------------------------------------------
    def _pump(self) -> None:
        """One poll: move whatever the device has buffered into our queue. Runs on the
        background thread (and is called directly by the read() unit tests)."""
        t0 = time.perf_counter()
        left = list(self._bp[self._left].GetScaledValueArray())
        right = list(self._bp[self._right].GetScaledValueArray())
        dur = time.perf_counter() - t0
        if dur > 1.0:            # a BT/.NET read that blocked the poll thread (holds the GIL)
            from ..watchdog import warn
            warn(f"slow device pump: {dur:.1f}s for {len(left)}+{len(right)} samples "
                 f"(BT read blocked; while it holds the GIL the UI freezes with it)")
        if left or right:
            with self._lock:
                self._buf[0].extend(left)
                self._buf[1].extend(right)
                n = min(len(self._buf[0]), len(self._buf[1]))
            sr = getattr(self, "sample_rate", 0) or 1000
            if n > 5 * sr and not self._warned_backlog:
                from ..watchdog import warn
                warn(f"read() not draining: {n} samples (~{n / sr:.1f}s) queued "
                     f"— the Qt loop isn't calling read() (main thread stuck elsewhere)")
                self._warned_backlog = True
            elif n < sr and self._warned_backlog:
                self._warned_backlog = False   # re-arm after the backlog drains

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._pump()
            except Exception:
                break                       # device stopped / gone
            self._stop.wait(0.005)          # ~200 Hz poll; ample for a 1–2 kHz stream

    def read(self, dt: float) -> np.ndarray:
        """Return the samples queued since the last call → `(k, 2)` in millivolts. No
        device / pythonnet call here, so the Qt render loop never stalls on the poll.
        Same signal group → the two channels track; a mismatched tail is left buffered."""
        if self._buf is None:
            return np.zeros((0, 2))
        with self._lock:
            k = min(len(self._buf[0]), len(self._buf[1]))
            if k == 0:
                return np.zeros((0, 2))
            left = self._buf[0][:k]
            right = self._buf[1][:k]
            del self._buf[0][:k]
            del self._buf[1][:k]
        out = np.empty((k, 2))
        out[:, 0] = left
        out[:, 1] = right
        out *= _V_TO_MV                      # volts → millivolts
        return out
