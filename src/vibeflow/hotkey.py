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

import os
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


def parse_hold_combo(combo: str) -> list:
    """Canonical key targets for a push-to-talk hold combo.

    ``"ctrl+win"`` -> ``["ctrl", "cmd"]`` (every key must be held at once). A
    single key like ``"ctrl_r"`` yields a one-element list.
    """
    if not combo or not combo.strip():
        return []
    return [canonical_token(part) for part in combo.split("+") if part.strip()]


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


# Virtual-key codes for the modifier families (Windows). The Windows key has a
# left and a right variant.
_VK_MODIFIERS = {
    "ctrl": (0x11,),   # VK_CONTROL
    "alt": (0x12,),    # VK_MENU
    "shift": (0x10,),  # VK_SHIFT
    "cmd": (0x5B, 0x5C),  # VK_LWIN, VK_RWIN
}


def _os_modifier_down(target: str):
    """Is this modifier *physically* pressed right now, per the OS?

    Returns True/False on Windows for a known modifier family, or ``None`` when
    we can't tell (non-Windows, a non-modifier key, or the API is unavailable) —
    in which case callers fall back to the event-tracked ``held`` set.

    This is the authority for triggering push-to-talk: pynput can miss a
    key-release (the Windows key often swallows its own release when it opens the
    Start menu), leaving a modifier "stuck" in the tracked set and mis-firing on
    the next plain Ctrl press (e.g. Ctrl+C). Asking the OS avoids that entirely.
    """
    if os.name != "nt":
        return None
    vks = _VK_MODIFIERS.get(target)
    if not vks:
        return None
    try:
        import ctypes

        get_state = ctypes.windll.user32.GetAsyncKeyState
        return any(bool(get_state(vk) & 0x8000) for vk in vks)
    except Exception:
        return None


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
        targets = parse_hold_combo(self.push_to_talk_key)
        held = set()

        def all_targets_down(just) -> bool:
            """Are ALL target keys held? The just-pressed key counts as down;
            every other target is checked against the OS (authoritative), with
            the tracked ``held`` set as a fallback when the OS can't tell."""
            if not targets:
                return False
            for target in targets:
                if target in just:
                    continue  # the key whose press we're handling — definitely down
                state = _os_modifier_down(target)
                if state is None:          # non-Windows / non-modifier: use tracking
                    if target not in held:
                        return False
                elif not state:            # OS says it's physically up
                    return False
            return True

        def on_press(key):
            matched = {t for t in targets if _matches(key, t)}
            if not matched:
                return
            held.update(matched)
            if not self._ptt_down and all_targets_down(matched):
                self._ptt_down = True
                self._safe(self.on_start)

        def on_release(key):
            released = False
            for target in targets:
                if _matches(key, target):
                    held.discard(target)
                    released = True
            if released and self._ptt_down:
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


# Virtual-key codes (Windows) used by the delivery hotkey.
_VK_V = 0x56
_VK_CTRL = 0x11
_VK_SHIFT = 0x10
_WM_KEYDOWN = (0x0100, 0x0104)  # WM_KEYDOWN, WM_SYSKEYDOWN


class DeliveryHotkey:
    """Contextual **Ctrl+Shift+V** "deliver here" hotkey (Windows only).

    It does nothing — and is completely invisible — unless ``is_armed()`` is
    true, which the app sets for a short window only when a dictation is waiting
    on the clipboard (you spoke with no text field focused). While armed,
    pressing Ctrl+Shift+V is **swallowed** (so the app's normal "paste without
    formatting" does not *also* fire and double-insert) and ``on_fire`` runs to
    deliver the dictation formatted for the focused app. When not armed, the key
    passes straight through and behaves exactly as it always has.

    Everything is wrapped so a hook error can never break the user's typing.
    """

    def __init__(self, *, is_armed: Callable[[], bool], on_fire: Callable[[], None]):
        self.is_armed = is_armed
        self.on_fire = on_fire
        self._listener = None

    def start(self) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            from pynput import keyboard
        except Exception:
            return
        get_state = ctypes.windll.user32.GetAsyncKeyState

        def combo_active() -> bool:
            try:
                return (
                    bool(get_state(_VK_CTRL) & 0x8000)
                    and bool(get_state(_VK_SHIFT) & 0x8000)
                    and bool(self.is_armed())
                )
            except Exception:
                return False

        def win32_filter(msg, data):
            # Suppress ONLY the Ctrl+Shift+V keydown, and only while armed.
            try:
                if (
                    msg in _WM_KEYDOWN
                    and getattr(data, "vkCode", None) == _VK_V
                    and combo_active()
                ):
                    self._listener.suppress_event()
            except Exception:
                pass

        def on_press(key):
            try:
                if getattr(key, "vk", None) == _VK_V and combo_active():
                    self._safe(self.on_fire)
            except Exception:
                pass

        try:
            self._listener = keyboard.Listener(
                on_press=on_press, win32_event_filter=win32_filter
            )
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    @staticmethod
    def _safe(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            import traceback

            traceback.print_exc()
