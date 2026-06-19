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
    restore_clipboard: bool = True,
    trailing_space: bool = True,
    auto_fallback: str = "clipboard",
) -> str:
    """Route ``text`` to the cursor or the clipboard and report what happened.

    Returns :data:`TYPED` or :data:`COPIED`.
    """
    if not text:
        return COPIED

    target = decide_target(output_mode, focus_state, auto_fallback)
    if target == "type":
        payload = with_trailing_space(text, trailing_space)
        insert_text(payload, method=insertion, restore_clipboard=restore_clipboard)
        return TYPED

    copy_to_clipboard(text)
    return COPIED


# ---------------------------------------------------------------------------
# Insertion back-ends
# ---------------------------------------------------------------------------
def insert_text(text: str, *, method: str = "paste", restore_clipboard: bool = True) -> None:
    """Insert ``text`` at the current cursor position."""
    if method == "keystroke":
        _type_keystrokes(text)
    else:
        _paste_via_clipboard(text, restore=restore_clipboard)


def copy_to_clipboard(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


def _paste_via_clipboard(text: str, *, restore: bool = True) -> None:
    """Put text on the clipboard and send Ctrl+V, optionally restoring after.

    Pasting is far more reliable than simulating keystrokes for long text and
    Unicode, and it preserves the user's keyboard layout/IME behaviour.
    """
    import pyperclip
    from pynput.keyboard import Controller, Key

    previous = None
    if restore:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(text)
    time.sleep(0.03)  # let the clipboard settle before pasting

    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")

    if restore and previous is not None:
        # Give the target app a moment to read the clipboard before we restore.
        time.sleep(0.2)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass


def _type_keystrokes(text: str) -> None:
    from pynput.keyboard import Controller

    Controller().type(text)
