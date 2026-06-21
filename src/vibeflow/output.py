"""Deliver finished transcripts to the right place.

Two destinations:
  * **type** — insert the text where the cursor is (paste or simulated keys),
  * **clipboard** — copy the text so the user can paste it themselves.

The routing decision (:func:`decide_target`) is a pure function so it can be
tested exhaustively. The actual insertion imports ``pyperclip``/``pynput``
lazily, keeping this module import-safe in headless/test environments.
"""

from __future__ import annotations

import time

from .focus_detect import EDITABLE, NON_EDITABLE, UNKNOWN
from .core.text import with_trailing_space

# Delivery results (also used as notification hints).
TYPED = "typed"
COPIED = "clipboard"


def decide_target(output_mode: str, focus_state: str, auto_fallback: str = "clipboard") -> str:
    """Decide whether to ``"type"`` or use the ``"clipboard"``.

    Args:
        output_mode: ``auto`` (decide from focus), ``type`` (always type), or
            ``clipboard`` (always copy).
        focus_state: One of the constants from :mod:`vibeflow.focus_detect`.
        auto_fallback: What to do in ``auto`` mode when focus is ``UNKNOWN`` —
            ``clipboard`` (default, safe) or ``type``.

    Returns:
        ``"type"`` or ``"clipboard"``.
    """
    mode = (output_mode or "auto").lower()
    if mode == "type":
        return "type"
    if mode == "clipboard":
        return "clipboard"

    # auto
    if focus_state == EDITABLE:
        return "type"
    if focus_state == NON_EDITABLE:
        return "clipboard"
    # UNKNOWN
    return "type" if (auto_fallback or "clipboard").lower() == "type" else "clipboard"


def deliver(
    text: str,
    *,
    output_mode: str,
    focus_state: str,
    insertion: str = "paste",
    trailing_space: bool = True,
    auto_fallback: str = "clipboard",
    expected_hwnd: int | None = None,
    **_legacy,
) -> str:
    """Deliver ``text``: always copy to the clipboard, and also paste into the
    focused field when there is one.

    The transcript is *always* placed on the clipboard — guaranteed delivery, and
    it stays there so you can paste it manually anywhere. If a text field is
    focused, it is also inserted there. Returns :data:`TYPED` (inserted + copied)
    or :data:`COPIED` (clipboard only).

    ``expected_hwnd`` is the window the output was *decided* for. If focus moved
    to a different window while we were transcribing/formatting, we do **not**
    type into the wrong app — the text is already on the clipboard to paste
    manually. The check fails open (types) when the foreground can't be read, so
    it never blocks normal use.
    """
    if not text:
        return COPIED

    payload = with_trailing_space(text, trailing_space)
    copy_to_clipboard(payload)

    target = decide_target(output_mode, focus_state, auto_fallback)
    if target == "type":
        if not _foreground_matches(expected_hwnd):
            return COPIED  # focus moved — leave it on the clipboard, don't mis-type
        if insertion == "keystroke":
            _type_keystrokes(payload)
        else:
            _send_paste()
        return TYPED
    return COPIED


def _foreground_matches(expected_hwnd: int | None) -> bool:
    """True if the foreground window is still ``expected_hwnd``.

    Fails **open**: if there is no expectation, or we can't read the current
    foreground window, return True so normal dictation is never blocked. Only a
    confident mismatch (we read a *different* window) returns False.
    """
    if not expected_hwnd:
        return True
    try:
        from .core.appmode import foreground_hwnd

        current = foreground_hwnd()
        return (current == expected_hwnd) if current else True
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Insertion back-ends
# ---------------------------------------------------------------------------
def _send_paste() -> None:
    """Send Ctrl+V to paste whatever is currently on the clipboard.

    Pasting is more reliable than simulating each keystroke for long text and
    Unicode, and it respects the user's keyboard layout / IME.
    """
    from pynput.keyboard import Controller, Key

    time.sleep(0.03)  # let the clipboard settle before pasting
    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")


def copy_to_clipboard(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


def _type_keystrokes(text: str) -> None:
    from pynput.keyboard import Controller

    Controller().type(text)
