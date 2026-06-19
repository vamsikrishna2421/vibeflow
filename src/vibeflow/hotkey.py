"""Global hotkey handling.

Two trigger styles, matching how tools like Wispr Flow behave:

  * **toggle** — tap a combo (default ``Ctrl+Win``) to start, tap again to
    stop and transcribe.
  * **push_to_talk** — hold a single key (default right Ctrl) while you speak,
    release to transcribe.

The string-parsing helpers (:func:`to_pynput_combo`, :func:`normalize_key_name`)
are pure and unit-tested. ``pynput`` is imported lazily inside :meth:`start`.
"""

from __future__ import annotations

import re
from typing import Callable

# Friendly aliases → canonical pynput key names.
_ALIASES = {
    "control": "ctrl", "ctl": "ctrl",
    "option": "alt", "opt": "alt",
    "windows": "cmd", "win": "cmd", "super": "cmd", "meta": "cmd",
    "return": "enter", "ret": "enter",
    "escape": "esc",
    "pgup": "page_up", "pageup": "page_up",
    "pgdn": "page_down", "pagedown": "page_down",
    "del": "delete", "ins": "insert",
    "bksp": "backspace", "bs": "backspace",
    "spacebar": "space", "space_bar": "space",
    "capslock": "caps_lock",
    "rctrl": "ctrl_r", "lctrl": "ctrl_l",
    "ralt": "alt_r", "lalt": "alt_l",
    "rshift": "shift_r", "lshift": "shift_l",
    "right_ctrl": "ctrl_r", "left_ctrl": "ctrl_l",
    "right_alt": "alt_r", "left_alt": "alt_l",
    "right_shift": "shift_r", "left_shift": "shift_l",
}

_MODIFIER_FAMILIES = ("ctrl", "alt", "shift", "cmd")


def canonical_token(token: str) -> str:
    """Normalise a single key token to its canonical pynput name."""
    t = token.strip().lower().replace("-", "_")
    t = re.sub(r"\s+", "_", t)
    return _ALIASES.get(t, t)


def to_pynput_combo(combo: str) -> str:
    """Convert e.g. ``"ctrl+alt+space"`` to pynput's ``"<ctrl>+<alt>+<space>"``.

    Single characters are left bare (``a``); everything else is treated as a
    named key and wrapped in angle brackets.
    """
    if not combo or not combo.strip():
        raise ValueError("Hotkey combo is empty")

    parts = []
    for raw in combo.split("+"):
        token = canonical_token(raw)
        if not token:
            continue
        parts.append(token if len(token) == 1 else f"<{token}>")

    if not parts:
        raise ValueError(f"Could not parse hotkey combo: {combo!r}")
    return "+".join(parts)


def normalize_key_name(name: str) -> str:
    """Canonical name for a single push-to-talk key (no angle brackets)."""
    if not name or not name.strip():
        raise ValueError("Push-to-talk key is empty")
    return canonical_token(name)


def _event_key_name(key) -> str:
    """Best-effort canonical name for a pynput key event."""
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    name = getattr(key, "name", None)
    if name:
        return name.lower()
    return str(key).lower().replace("key.", "")


def _matches(key, target: str) -> bool:
    name = _event_key_name(key)
    if name == target:
        return True
    # Allow a generic "ctrl"/"alt"/"shift"/"cmd" to match either side.
    if target in _MODIFIER_FAMILIES and name.startswith(target):
        return True
    return False


class HotkeyManager:
    """Listens for the configured trigger and calls back start/stop."""

    def __init__(
        self,
        *,
        mode: str = "toggle",
        toggle_combo: str = "ctrl+win",
        push_to_talk_key: str = "ctrl_r",
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        self.mode = (mode or "toggle").lower()
        self.toggle_combo = toggle_combo
        self.push_to_talk_key = push_to_talk_key
        self.on_start = on_start
        self.on_stop = on_stop
        self._listeners: list = []
        self._ptt_down = False
        self._toggle_on = False

    def start(self) -> None:
        from pynput import keyboard

        if self.mode == "push_to_talk":
            self._start_push_to_talk(keyboard)
        else:
            self._start_toggle(keyboard)

    def _start_toggle(self, keyboard) -> None:
        combo = to_pynput_combo(self.toggle_combo)
        listener = keyboard.GlobalHotKeys({combo: self._on_toggle})
        listener.start()
        self._listeners.append(listener)

    def _start_push_to_talk(self, keyboard) -> None:
        target = normalize_key_name(self.push_to_talk_key)

        def on_press(key):
            if _matches(key, target) and not self._ptt_down:
                self._ptt_down = True
                self._safe(self.on_start)

        def on_release(key):
            if _matches(key, target) and self._ptt_down:
                self._ptt_down = False
                self._safe(self.on_stop)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        self._listeners.append(listener)

    def _on_toggle(self) -> None:
        if not self._toggle_on:
            self._toggle_on = True
            self._safe(self.on_start)
        else:
            self._toggle_on = False
            self._safe(self.on_stop)

    def reset_toggle(self) -> None:
        """Clear toggle state (e.g. if recording was stopped another way)."""
        self._toggle_on = False
        self._ptt_down = False

    def stop(self) -> None:
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._listeners = []

    @staticmethod
    def _safe(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            # Never let a callback error kill the listener thread.
            import traceback

            traceback.print_exc()
