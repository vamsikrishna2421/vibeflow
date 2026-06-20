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
from .text import with_trailing_space

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
    **_legacy,
) -> str:
    """Deliver ``text``: always copy to the clipboard, and also paste into the
    focused field when there is one.

    The transcript is *always* placed on the clipboard — guaranteed delivery, and
    it stays there so you can paste it manually anywhere. If a text field is
    focused, it is also inserted there. Returns :data:`TYPED` (inserted + copied)
    or :data:`COPIED` (clipboard only).
    """
    if not text:
        return COPIED

    payload = with_trailing_space(text, trailing_space)
    copy_to_clipboard(payload)

    target = decide_target(output_mode, focus_state, auto_fallback)
    if target == "type":
        if insertion == "keystroke":
            _type_keystrokes(payload)
        else:
            _send_paste()
        return TYPED
    return COPIED


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
