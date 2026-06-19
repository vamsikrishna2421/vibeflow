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


def detect_focus() -> str:
    """Return :data:`EDITABLE`, :data:`NON_EDITABLE`, or :data:`UNKNOWN`."""
    if sys.platform != "win32":
        return UNKNOWN
    state = _detect_uia()
    if state != UNKNOWN:
        return state
    return _detect_win32()


# ---------------------------------------------------------------------------
# UI Automation
# ---------------------------------------------------------------------------
def _get_uia():
    """Create (and cache) the UI Automation root object, or return None."""
    if "obj" in _uia_cache:
        return _uia_cache["obj"]
    try:
        import comtypes.client

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
