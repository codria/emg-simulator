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
_MAX_BUF_SEC = 2.0  # cap on the poll->read queue: under a main-loop stall, drop the
#                     oldest samples past this instead of growing an unbounded backlog


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
        self._buf_cap = 10 ** 9        # max samples/channel; real value set in start() from sr
        self._warned_backlog = False   # watchdog: only warn once per stall
        self._warned_nonfinite = False

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
        # bound the poll->read queue now that we know the real rate: a main-loop stall
        # (or slow inter-channel drift over a long session) can't grow it without limit.
        self._buf_cap = max(64, int(round(_MAX_BUF_SEC * self.sample_rate)))
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
        if not (left or right):
            return
        cap = self._buf_cap
        dropped = 0
        with self._lock:
            self._buf[0].extend(left)
            self._buf[1].extend(right)
            for ch in (0, 1):
                over = len(self._buf[ch]) - cap
                if over > 0:
                    del self._buf[ch][:over]     # drop oldest → bounded + stays real-time
                    dropped = max(dropped, over)
        if dropped and not self._warned_backlog:
            from ..watchdog import warn
            warn(f"input backlog capped at {cap} samples/ch (~{_MAX_BUF_SEC:.0f}s): the main "
                 f"loop stalled — dropping oldest EMG to stay real-time (dropped {dropped})")
            self._warned_backlog = True
        elif not dropped and self._warned_backlog:
            self._warned_backlog = False         # re-arm once we're back under the cap

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._pump()
            except Exception as e:
                if not self._stop.is_set():  # unexpected (not a normal stop) → note it
                    from ..watchdog import warn
                    warn(f"BioRadio poll thread stopped: {e!r} — stream ended (read() now "
                         f"returns empty; reconnect from the C dialog)")
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
        if not np.isfinite(out).all():       # a BT/electrode dropout can yield NaN/Inf; one
            np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)  # bad sample would
            if not self._warned_nonfinite:                                   # poison the baseline
                from ..watchdog import warn
                warn("non-finite device samples (NaN/Inf) sanitized to 0 — check electrode/BT link")
                self._warned_nonfinite = True
        return out
