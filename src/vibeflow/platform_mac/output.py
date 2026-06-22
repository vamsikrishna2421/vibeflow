"""Deliver finished transcripts on macOS.

The Mac counterpart to :mod:`vibeflow.output`. Same design — **always copy to
the clipboard**, and *also* paste into the focused field when one is editable —
but the Mac "hands":

  * paste is **Cmd+V** (not Ctrl+V),
  * the "focus didn't move" re-verify compares the frontmost **app pid**
    (``NSWorkspace``) instead of a Win32 ``hwnd``.

The pure routing decision is reused as-is from :func:`vibeflow.output.decide_target`
(it only depends on the shared focus-state constants). ``pyperclip`` / ``pynput``
are imported lazily so this module stays import-safe in headless tests.
"""

from __future__ import annotations

import time

from ..output import COPIED, TYPED, copy_to_clipboard, decide_target
from ..core.text import with_trailing_space
from . import appdetect


def deliver(
    text: str,
    *,
    output_mode: str,
    focus_state: str,
    insertion: str = "paste",
    trailing_space: bool = True,
    auto_fallback: str = "clipboard",
    expected_pid: int | None = None,
) -> str:
    """Deliver ``text``: always copy, and also paste it when a field is focused.

    Returns :data:`TYPED` (inserted + copied) or :data:`COPIED` (clipboard only).
    ``expected_pid`` is the frontmost app the output was *decided* for; if focus
    moved to a different app while transcribing/formatting we leave the text on
    the clipboard rather than paste into the wrong app. The check fails **open**
    (pastes) when the frontmost app can't be read, so it never blocks normal use.
    """
    if not text:
        return COPIED

    payload = with_trailing_space(text, trailing_space)
    copy_to_clipboard(payload)

    target = decide_target(output_mode, focus_state, auto_fallback)
    if target == "type":
        if not _frontmost_matches(expected_pid):
            return COPIED  # focus moved — leave it on the clipboard, don't mis-paste
        if insertion == "keystroke":
            _type_keystrokes(payload)
        else:
            _send_paste()
        return TYPED
    return COPIED


def _frontmost_matches(expected_pid: int | None) -> bool:
    """True if the frontmost app is still ``expected_pid`` (fails open)."""
    if not expected_pid:
        return True
    try:
        current = appdetect.frontmost_pid()
        return (current == expected_pid) if current else True
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Insertion back-ends
# ---------------------------------------------------------------------------
_KEYCODE_V = 9  # kVK_ANSI_V


def _send_paste() -> None:
    """Send Cmd+V by posting the key events directly via Quartz (keycode-based).

    We deliberately do NOT use pynput here: pynput types the ``'v'`` *character*,
    which it maps to a keycode through the keyboard-layout (Text Services Manager)
    API — and TSM is **main-thread-only**. The paste runs on the background
    pipeline thread, so that path hard-crashes (SIGTRAP via
    ``dispatch_assert_queue``) under the hardened-runtime build. Posting the 'v'
    *keycode* with the Command flag needs no layout lookup and is thread-safe.
    """
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        CGEventSourceCreate,
        kCGEventFlagMaskCommand,
        kCGEventSourceStateHIDSystemState,
        kCGHIDEventTap,
    )

    time.sleep(0.03)  # let the clipboard settle before pasting
    src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    down = CGEventCreateKeyboardEvent(src, _KEYCODE_V, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    up = CGEventCreateKeyboardEvent(src, _KEYCODE_V, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)


def _type_keystrokes(text: str) -> None:
    # NOTE: pynput's typing uses the layout/TSM API (main-thread-only), which can
    # crash from the background pipeline thread — so the default insertion is
    # "paste" (above). Keystroke mode remains available but is best avoided on Mac.
    from pynput.keyboard import Controller

    Controller().type(text)
