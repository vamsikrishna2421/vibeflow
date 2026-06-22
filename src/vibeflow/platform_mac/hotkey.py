"""macOS keyboard hotkeys — push-to-talk + the contextual delivery key, in ONE
pynput listener.

Design notes (each rule here was learned the hard way):

* **One listener only.** Two concurrent pynput ``Listener``s each run a
  ``CGEventTap`` on their own ``CFRunLoop`` thread; running two at once makes
  HIToolbox abort ("Text Input Sources … called in two threads concurrently").
  So push-to-talk and the delivery hotkey share this single listener.

* **Callbacks never block the tap thread.** ``on_press`` / ``on_release`` /
  ``darwin_intercept`` run on the event-tap's run-loop thread. macOS *disables a
  tap whose callback is slow* (``kCGEventTapDisabledByTimeout``); if we opened the
  microphone synchronously there, the tap would die and the key-*release* would
  never arrive — leaving push-to-talk stuck "listening". So every user callback
  is dispatched on a short-lived worker thread and the tap callback returns
  immediately.

* **Belt-and-suspenders stop.** Push-to-talk start/stop is driven by
  ``on_press`` / ``on_release`` (which fire reliably for the trigger key), and
  ``darwin_intercept`` adds a *backstop*: if the trigger is a modifier and its
  flag is no longer set while we still think it's held, stop. So even a missed
  release (e.g. swallowed by a system modal) self-corrects on the next event.

The delivery hotkey (**Cmd+Shift+V**) is swallowed only while armed.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

from ..hotkey import _matches, parse_hold_combo

log = logging.getLogger("vibeflow")

_VK_V = 9  # kVK_ANSI_V — the 'v' key's macOS virtual keycode

# Device-specific modifier bits (IOKit NX_DEVICE*KEYMASK), present in CGEvent
# flags — these distinguish left vs right modifier keys.
_DEVICE_FLAG = {
    "ctrl_l": 0x00000001, "ctrl_r": 0x00002000,
    "shift_l": 0x00000002, "shift_r": 0x00000004,
    "cmd_l": 0x00000008, "cmd_r": 0x00000010,
    "alt_l": 0x00000020, "alt_r": 0x00000040,
}
_ANY_FLAG = {"cmd": 0x00100000, "shift": 0x00020000,
             "ctrl": 0x00040000, "alt": 0x00080000}
_CMD_MASK = 0x00100000
_SHIFT_MASK = 0x00020000


def _flag_mask_for(key: str):
    """CGEvent flag bit for a single modifier PTT key, or ``None`` if not one."""
    k = (key or "").strip().lower()
    return _DEVICE_FLAG.get(k) or _ANY_FLAG.get(k)


class MacHotkeys:
    """Single-listener push-to-talk + Cmd+Shift+V delivery hotkey for macOS."""

    def __init__(
        self,
        *,
        push_to_talk_key: str = "cmd_r",
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        deliver_is_armed: Callable[[], bool],
        deliver_on_fire: Callable[[], None],
    ) -> None:
        self.push_to_talk_key = push_to_talk_key
        self.on_start = on_start
        self.on_stop = on_stop
        self.deliver_is_armed = deliver_is_armed
        self.deliver_on_fire = deliver_on_fire
        self._listener = None
        self._ptt_down = False

    def start(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from pynput import keyboard
            from Quartz import (
                CGEventGetFlags,
                CGEventGetIntegerValueField,
                kCGEventKeyDown,
                kCGKeyboardEventKeycode,
            )
        except Exception:
            return

        targets = parse_hold_combo(self.push_to_talk_key)
        ptt_mask = _flag_mask_for(self.push_to_talk_key)
        held: set = set()

        def begin():
            if not self._ptt_down:
                self._ptt_down = True
                log.info("ptt: start")
                self._dispatch(self.on_start)

        def end(reason: str):
            if self._ptt_down:
                self._ptt_down = False
                log.info("ptt: stop (%s)", reason)
                self._dispatch(self.on_stop)

        def on_press(key):
            matched = {t for t in targets if _matches(key, t)}
            if not matched:
                return
            held.update(matched)
            if targets and all(t in held for t in targets):
                begin()

        def on_release(key):
            released = False
            for t in targets:
                if _matches(key, t):
                    held.discard(t)
                    released = True
            if released:
                end("release")

        def darwin_intercept(event_type, event):
            try:
                flags = CGEventGetFlags(event)
                # Delivery hotkey: swallow Cmd+Shift+V keydown only while armed.
                if event_type == kCGEventKeyDown:
                    keycode = CGEventGetIntegerValueField(
                        event, kCGKeyboardEventKeycode
                    )
                    if (
                        keycode == _VK_V
                        and bool(flags & _CMD_MASK)
                        and bool(flags & _SHIFT_MASK)
                        and bool(self.deliver_is_armed())
                    ):
                        self._dispatch(self.deliver_on_fire)
                        return None
                # Backstop: trigger modifier no longer held → ensure we stopped.
                if ptt_mask is not None and self._ptt_down and not (flags & ptt_mask):
                    held.clear()
                    end("backstop")
            except Exception:
                pass
            return event

        try:
            self._listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
                darwin_intercept=darwin_intercept,
            )
            self._listener.start()
            log.info("hotkey listener started (ptt=%s mask=%s)",
                     self.push_to_talk_key, ptt_mask)
        except Exception:
            self._listener = None

    def reset(self) -> None:
        """Clear push-to-talk state (e.g. if recording was stopped another way)."""
        self._ptt_down = False

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    @staticmethod
    def _dispatch(callback: Callable[[], None]) -> None:
        """Run a user callback OFF the event-tap thread so the tap never stalls."""
        def run():
            try:
                callback()
            except Exception:
                import traceback
                traceback.print_exc()

        threading.Thread(target=run, daemon=True).start()
