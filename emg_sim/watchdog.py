"""Tiny always-on watchdog for diagnosing rare freezes.

Silent in normal operation — callers only invoke `warn()` when an operation
blocks pathologically long (well above any normal frame time), so this adds no
noise to a healthy run. Messages go to *both* stderr and a temp log file, so the
report survives even when the app was launched detached (run.bat / `start`).

Used to locate a device-only freeze that static analysis couldn't pin down: it
tells us whether the stall is on the device poll thread (a BT read holding the
GIL), the engine step, the sound, the 3D render, or the main loop being starved.
Remove once the cause is fixed.
"""

from __future__ import annotations

import faulthandler
import sys
import tempfile
import time
from pathlib import Path

_LOG = Path(tempfile.gettempdir()) / "emg_sim_watchdog.log"
_dump_file = None   # kept open for faulthandler's C-thread dumps


def warn(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} [watchdog] {msg}"
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def heartbeat(timeout: float = 8.0) -> None:
    """Reset a deadlock timer, called once per frame. If a frame (or the event-loop
    processing after it) ever exceeds `timeout`, faulthandler's C-level watchdog
    thread dumps EVERY thread's stack to the log — even during a permanent freeze
    and even if the GIL is held, which the per-frame `warn` path can't capture
    (it only logs a gap once the loop recovers). One dump per freeze (repeat=False;
    a healthy frame re-arms it before it can fire)."""
    global _dump_file
    try:
        if _dump_file is None:
            _dump_file = open(_LOG, "a", encoding="utf-8", buffering=1)
            _dump_file.write(
                f"{time.strftime('%H:%M:%S')} [watchdog] freeze-dump armed "
                f"(all thread stacks if a frame exceeds {timeout:.0f}s)\n"
            )
            _dump_file.flush()
        faulthandler.dump_traceback_later(timeout, repeat=False, file=_dump_file)
    except Exception:
        pass


def log_path() -> str:
    return str(_LOG)
