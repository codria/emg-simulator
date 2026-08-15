"""Sound-effect debounce (no audio device touched).

The reach/enter effects are triggered from the GUI tick; a tip jittering on a
target-zone boundary can fire the enter-click's rising edge every frame. Sfx
debounces those so rapid re-triggers can't pile into an audible backlog.
"""

from __future__ import annotations

import time

from emg_sim.ui.sound import Sfx


def test_sfx_debounce_collapses_rapid_triggers():
    s = Sfx(None)                 # no wav → _debounced() is pure timestamp logic, no audio
    s._min_interval = 0.1
    assert s._debounced() is False   # first call: accepted
    assert s._debounced() is True    # immediate re-trigger: collapsed
    assert s._debounced() is True    # still within the window
    time.sleep(0.12)
    assert s._debounced() is False   # window elapsed → accepted again


def test_sfx_play_without_wav_is_silent_noop():
    s = Sfx(None)
    assert s.play() is None       # unavailable → no thread, no crash
