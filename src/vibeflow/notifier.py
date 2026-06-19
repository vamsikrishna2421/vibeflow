"""Lightweight audio feedback (short beeps).

Uses the standard-library ``winsound`` on Windows; degrades to a silent no-op
elsewhere. Tray pop-up notifications are handled separately by the tray icon in
:mod:`vibeflow.app`.
"""

from __future__ import annotations

import sys

START = "start"
STOP = "stop"
ERROR = "error"


def play(kind: str, enabled: bool = True) -> None:
    """Play a short cue. ``kind`` is one of START/STOP/ERROR."""
    if not enabled:
        return
    if sys.platform != "win32":
        return
    try:
        import winsound

        if kind == START:
            winsound.Beep(880, 90)      # rising "listening" cue
        elif kind == STOP:
            winsound.Beep(523, 90)      # falling "done" cue
        elif kind == ERROR:
            winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception:
        pass
