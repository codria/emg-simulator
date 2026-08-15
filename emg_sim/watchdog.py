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

import sys
import tempfile
import time
from pathlib import Path

_LOG = Path(tempfile.gettempdir()) / "emg_sim_watchdog.log"


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


def log_path() -> str:
    return str(_LOG)
