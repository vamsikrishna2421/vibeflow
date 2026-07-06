"""On-screen status overlay (HUD).

Shows a small, always-on-top pill near the bottom of the screen while dictating
("Listening…", "Transcribing…", "Completed successfully", "Copied to
clipboard"), so the user doesn't have to watch the tray icon.

Critical property: the overlay must **never steal keyboard focus**, otherwise
the text field we paste into would lose focus. It is created as a non-activating
(``WS_EX_NOACTIVATE``), click-through (``WS_EX_TRANSPARENT``), tool window and is
shown without activation.

Implementation: a tkinter window runs on its own dedicated thread (the tray owns
the main thread). All Tk calls happen on that thread; other threads communicate
via a queue. ``tkinter`` is imported lazily so the rest of the app — and the
test-suite — never depends on it, and a missing/broken Tk degrades to a no-op.
"""

from __future__ import annotations

import queue
import threading

# state -> (dot colour, default text, auto-hide ms or None, pulse?)
# The leading emoji mirrors the macOS overlay (🎙 listening, ✍️ transcribing, …) —
# a friendly, instantly-readable state cue.
_STATES = {
    "listening": ("#E23A3A", "🎙 VibeFlow · Listening…", None, True),
    "transcribing": ("#F0A52A", "✍️ VibeFlow · Transcribing…", None, False),
    "done": ("#39B36A", "✓ VibeFlow · Done", 1900, False),
    "clipboard": ("#5B8DEF", "📋 VibeFlow · Copied to clipboard", 2800, False),
    "working": ("#F0A52A", "⚙️ VibeFlow · Working…", None, True),   # stays until replaced
    "learned": ("#39B36A", "🧠 VibeFlow · Learned", 4200, False),   # green, lingers to read
    "info": ("#9AA4B2", "VibeFlow", 2200, False),
    "error": ("#E23A3A", "VibeFlow", 3500, False),
}

_BG = "#0E1730"
_FG = "#F2F4F8"


class StatusOverlay:
    """Thread-safe on-screen status HUD. All public methods are non-blocking."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self._queue: "queue.Queue" = queue.Queue()
        self._thread = None
        self._started = False
        self._available = True
        self._win_hwnd = 0  # exposed for tests/verification

    # -- public API (callable from any thread) -------------------------
    def start(self) -> None:
        if not self.enabled or self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, name="vf-overlay", daemon=True)
        self._thread.start()

    def show(self, state: str, text: str | None = None) -> None:
        if not (self.enabled and self._started and self._available):
            return
        self._queue.put(("show", state, text))

    def level(self, value: float) -> None:
        """Feed a live input level (0..1) to animate the meter while listening.
        No-op unless the overlay is up; safe to call from the audio thread."""
        if not (self.enabled and self._started and self._available):
            return
        try:
            self._queue.put(("level", float(value), None))
        except Exception:
            pass

    def hide(self) -> None:
        if self._started:
            self._queue.put(("hide", None, None))

    def set_enabled(self, value: bool) -> None:
        self.enabled = bool(value)
        if not value:
            self.hide()
        elif not self._started:
            self.start()

    def stop(self) -> None:
        if self._started:
            self._queue.put(("quit", None, None))

    # -- Tk thread -----------------------------------------------------
    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            self._available = False
            self._log_unavailable("tkinter import failed")
            return
        try:
            self._tk = tk
            self._root = tk.Tk()
            self._root.withdraw()
            self._hide_id = None
            self._current = None
            self._pulse_on = False
            self._build()
            self._root.after(40, self._poll)
            self._root.mainloop()
        except Exception:
            self._available = False
            self._log_unavailable("tk init failed")

    @staticmethod
    def _log_unavailable(reason: str) -> None:
        try:
            import logging

            logging.getLogger("vibeflow").warning("overlay disabled: %s", reason)
        except Exception:
            pass

    def _build(self) -> None:
        tk = self._tk
        root = self._root
        root.overrideredirect(True)
        try:
            root.attributes("-topmost", True)
            root.attributes("-alpha", 0.94)
        except Exception:
            pass
        root.configure(bg=_BG)
        frame = tk.Frame(root, bg=_BG, padx=18, pady=11)
        frame.pack()
        self._canvas = tk.Canvas(frame, width=70, height=16, bg=_BG, highlightthickness=0)
        self._canvas.pack(side="left", padx=(0, 11))
        self._dot = self._canvas.create_oval(2, 2, 14, 14, fill="#E23A3A", outline="")
        # A small live level meter to the right of the dot (shown while listening).
        # Idle bars are painted in the background colour so they're invisible until
        # audio drives them — so non-listening states look exactly as before.
        self._bars = []
        for i in range(5):
            x = 24 + i * 9
            self._bars.append(
                self._canvas.create_rectangle(x, 7, x + 5, 9, fill=_BG, outline="")
            )
        self._label = tk.Label(
            frame, text="VibeFlow", fg=_FG, bg=_BG, font=("Segoe UI", 11)
        )
        self._label.pack(side="left")
        root.update_idletasks()
        self._apply_win_styles()

    def _poll(self) -> None:
        try:
            while True:
                cmd, state, text = self._queue.get_nowait()
                if cmd == "show":
                    self._apply(state, text)
                elif cmd == "level":
                    self._apply_level(state)  # 'state' carries the level value
                elif cmd == "hide":
                    self._cancel_hide()
                    self._do_hide()
                elif cmd == "quit":
                    try:
                        self._root.withdraw()
                        self._root.quit()
                    except Exception:
                        pass
                    return
        except queue.Empty:
            pass
        try:
            self._root.after(40, self._poll)
        except Exception:
            pass

    def _apply(self, state: str, text: str | None) -> None:
        color, default_text, auto_ms, pulse = _STATES.get(state, _STATES["info"])
        self._current = state
        try:
            self._canvas.itemconfig(self._dot, fill=color)
            self._label.config(text=text or default_text)
        except Exception:
            return
        if state != "listening":
            self._reset_bars()
        self._cancel_hide()
        self._position_and_show()
        if pulse:
            self._pulse_on = True
            self._root.after(450, self._pulse)
        else:
            self._pulse_on = False
        if auto_ms:
            self._hide_id = self._root.after(auto_ms, self._do_hide)

    def _apply_level(self, value) -> None:
        """Animate the meter bars from a 0..1 level. Only while listening."""
        if self._current != "listening":
            return
        try:
            v = 0.0 if value is None else max(0.0, min(1.0, float(value) * 6.0))  # boost quiet speech
            for i, bar in enumerate(self._bars):
                mag = v * (0.55 + 0.45 * ((i % 3) / 2.0))  # per-bar variation → reads like a meter
                h = 2 + int(mag * 12)
                x0, _, x1, _ = self._canvas.coords(bar)
                self._canvas.coords(bar, x0, 8 - h / 2, x1, 8 + h / 2)
                self._canvas.itemconfig(bar, fill="#E23A3A" if mag > 0.06 else _BG)
        except Exception:
            pass

    def _reset_bars(self) -> None:
        try:
            for i, bar in enumerate(getattr(self, "_bars", [])):
                x = 24 + i * 9
                self._canvas.coords(bar, x, 7, x + 5, 9)
                self._canvas.itemconfig(bar, fill=_BG)
        except Exception:
            pass

    def _pulse(self) -> None:
        if not self._pulse_on or self._current != "listening":
            return
        self._pulse_state = not getattr(self, "_pulse_state", False)
        color = "#E23A3A" if self._pulse_state else "#7C2020"
        try:
            self._canvas.itemconfig(self._dot, fill=color)
            self._root.after(450, self._pulse)
        except Exception:
            pass

    def _do_hide(self) -> None:
        self._current = None
        self._pulse_on = False
        self._reset_bars()
        try:
            self._root.withdraw()
        except Exception:
            pass

    def _cancel_hide(self) -> None:
        if self._hide_id is not None:
            try:
                self._root.after_cancel(self._hide_id)
            except Exception:
                pass
            self._hide_id = None

    def _position_and_show(self) -> None:
        root = self._root
        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, int(sh * 0.85) - h)
        try:
            root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        self._show_no_activate()

    # -- Win32: show without stealing focus ----------------------------
    def _show_no_activate(self) -> None:
        root = self._root
        try:
            root.deiconify()
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = self._win_hwnd or self._resolve_hwnd()
            HWND_TOPMOST = wintypes.HWND(-1)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(
                wintypes.HWND(hwnd), HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def _resolve_hwnd(self) -> int:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        wid = self._root.winfo_id()
        GA_ROOT = 2
        handle = user32.GetAncestor(wintypes.HWND(wid), GA_ROOT)
        return int(handle) if handle else int(wid)

    def _apply_win_styles(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = self._resolve_hwnd()
            self._win_hwnd = hwnd

            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000

            try:
                get_long = user32.GetWindowLongPtrW
                set_long = user32.SetWindowLongPtrW
            except AttributeError:  # 32-bit Python
                get_long = user32.GetWindowLongW
                set_long = user32.SetWindowLongW
            get_long.restype = ctypes.c_longlong
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            set_long.restype = ctypes.c_longlong
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]

            style = get_long(wintypes.HWND(hwnd), GWL_EXSTYLE)
            style |= (
                WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED
            )
            set_long(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
        except Exception:
            pass
