"""Detect whether the currently focused UI element accepts typed text.

This answers one question for the output router: "If I send keystrokes right
now, will they land in a text field?" The answer decides whether VibeFlow types
the transcript in place or falls back to the clipboard.

Strategy on Windows (most reliable first):
  1. UI Automation (``comtypes`` + ``UIAutomationCore``) — works for modern
     apps including browsers, Electron, and UWP, which don't expose classic
     child windows.
  2. Win32 ``GetGUIThreadInfo`` class-name / caret heuristic — a lightweight
     fallback when UI Automation is unavailable.
  3. ``UNKNOWN`` — when nothing conclusive is found, the caller decides what to
     do (VibeFlow defaults to the clipboard, which is the safe choice).

Every code path is wrapped so detection can *never* crash the app; the worst
case is a return of ``UNKNOWN``.
"""

from __future__ import annotations

import sys

# Focus states returned by :func:`detect_focus`.
EDITABLE = "editable"
NON_EDITABLE = "non_editable"
UNKNOWN = "unknown"

# UI Automation ControlType ids we treat as text-editable.
_UIA_EDIT = 50004
_UIA_DOCUMENT = 50030
# Pattern ids.
_UIA_VALUE_PATTERN = 10002
_UIA_TEXT_PATTERN = 10014

_uia_cache: dict = {}

# Window classes for terminals/consoles. These accept pasted input (Ctrl+V) but
# do NOT expose an editable UI Automation text field, so UIA reports them as
# non-editable and dictation wrongly fell back to clipboard-only. We detect them
# by window class and treat them as typeable.
_TERMINAL_CLASSES = (
    "cascadia_hosting_window_class",  # Windows Terminal
    "consolewindowclass",             # classic console host (cmd, PowerShell, conhost)
    "pseudoconsolewindow",            # pseudo-console
    "windowsterminal",
)


def _class_is_terminal(cls: str) -> bool:
    cls = (cls or "").lower()
    return any(k in cls for k in _TERMINAL_CLASSES)


def _foreground_is_terminal() -> bool:
    """True if the foreground window is a terminal/console."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return _class_is_terminal(buf.value or "")
    except Exception:
        return False


def detect_focus() -> str:
    """Return :data:`EDITABLE`, :data:`NON_EDITABLE`, or :data:`UNKNOWN`."""
    if sys.platform != "win32":
        return UNKNOWN
    # Terminals accept pasted input but don't expose an editable UIA field, so
    # check for them first and treat them as typeable.
    if _foreground_is_terminal():
        return EDITABLE
    state = _detect_uia()
    if state != UNKNOWN:
        return state
    return _detect_win32()


# ---------------------------------------------------------------------------
# UI Automation
# ---------------------------------------------------------------------------
def _prepare_comtypes_gen() -> None:
    """Point comtypes code generation at a writable folder.

    In a packaged (PyInstaller) build the app directory is read-only, so comtypes
    cannot write the generated UI Automation wrapper there — which silently broke
    focus detection and made everything fall back to the clipboard. Writing the
    wrapper into the per-user app-data folder fixes that.
    """
    try:
        import os
        import sys

        import comtypes.client
        import comtypes.gen
        from .config import config_dir

        gen = str(config_dir() / "comtypes_gen")
        os.makedirs(gen, exist_ok=True)
        comtypes.client.gen_dir = gen
        if gen not in comtypes.gen.__path__:
            comtypes.gen.__path__.insert(0, gen)
        if gen not in sys.path:
            sys.path.insert(0, gen)
    except Exception:
        pass


def _get_uia():
    """Create (and cache) the UI Automation root object, or return None."""
    if "obj" in _uia_cache:
        return _uia_cache["obj"]
    try:
        import comtypes.client

        _prepare_comtypes_gen()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA  # type: ignore

        obj = comtypes.client.CreateObject(
            UIA.CUIAutomation, interface=UIA.IUIAutomation
        )
        _uia_cache["obj"] = obj
        _uia_cache["UIA"] = UIA
        return obj
    except Exception:
        _uia_cache["obj"] = None
        return None


def _detect_uia() -> str:
    uia = _get_uia()
    if uia is None:
        return UNKNOWN
    UIA = _uia_cache.get("UIA")
    try:
        element = uia.GetFocusedElement()
        if element is None:
            return UNKNOWN

        try:
            control_type = element.CurrentControlType
        except Exception:
            control_type = None

        if control_type in (_UIA_EDIT, _UIA_DOCUMENT):
            return NON_EDITABLE if _is_readonly(element, UIA) else EDITABLE

        # Content-editable regions (rich web editors, some chat boxes) expose a
        # writable Value or Text pattern even though the control type differs.
        if _supports_editable_pattern(element, UIA):
            return EDITABLE

        return NON_EDITABLE
    except Exception:
        return UNKNOWN


def _is_readonly(element, UIA) -> bool:
    try:
        pattern = element.GetCurrentPattern(_UIA_VALUE_PATTERN)
        if not pattern:
            return False
        value = pattern.QueryInterface(UIA.IUIAutomationValuePattern)
        return bool(value.CurrentIsReadOnly)
    except Exception:
        return False


def _supports_editable_pattern(element, UIA) -> bool:
    try:
        pattern = element.GetCurrentPattern(_UIA_VALUE_PATTERN)
        if pattern:
            value = pattern.QueryInterface(UIA.IUIAutomationValuePattern)
            if not bool(value.CurrentIsReadOnly):
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Win32 fallback
# ---------------------------------------------------------------------------
def _detect_win32() -> str:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT),
            ]

        foreground = user32.GetForegroundWindow()
        if not foreground:
            return UNKNOWN

        pid = wintypes.DWORD()
        thread_id = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))

        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return UNKNOWN

        hwnd = info.hwndFocus or info.hwndCaret
        if hwnd:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            cls = (buf.value or "").lower()
            if any(k in cls for k in ("edit", "text", "richedit", "scintilla", "memo")):
                return EDITABLE

        # A visible caret strongly implies a text-editing context.
        if info.hwndCaret:
            return EDITABLE

        return UNKNOWN
    except Exception:
        return UNKNOWN
