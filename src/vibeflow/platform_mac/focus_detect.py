"""Detect whether the focused macOS UI element accepts typed text.

The Mac counterpart to the Windows :mod:`vibeflow.focus_detect`. It answers the
same single question for the output router — "if I paste right now, will the text
land in a text field?" — and returns the **same** ``EDITABLE`` /
``NON_EDITABLE`` / ``UNKNOWN`` constants, so :func:`vibeflow.output.decide_target`
works unchanged.

Strategy (Accessibility API via PyObjC):
  1. ``AXUIElementCreateSystemWide()`` → ``kAXFocusedUIElementAttribute`` to get
     the focused element, then its ``kAXRoleAttribute``. Text roles
     (``AXTextField`` / ``AXTextArea`` / ``AXComboBox``) are editable unless the
     value attribute is explicitly not settable (read-only).
  2. Anything else whose ``kAXValueAttribute`` is settable (content-editable web
     regions, some chat composers) is also treated as editable.
  3. ``UNKNOWN`` when Accessibility permission isn't granted or nothing
     conclusive is found — the caller falls back to the clipboard (the safe
     choice), exactly as on Windows.

Every path is wrapped so detection can never crash the app; the worst case is
``UNKNOWN``. Reading the focused element requires the **Accessibility**
permission (System Settings → Privacy & Security → Accessibility).
"""

from __future__ import annotations

# Reuse the exact focus-state constants the output router compares against, so
# Mac and Windows share one vocabulary.
from ..focus_detect import EDITABLE, NON_EDITABLE, UNKNOWN  # noqa: F401

_AX_SUCCESS = 0  # kAXErrorSuccess

# Roles that mean "a text-editing context". A focused element with one of these
# roles is treated as editable outright: many Mac text areas report
# ``kAXValueAttribute`` as *not* settable even when they accept typing, so a
# settable check would wrongly reject them (e.g. TextEdit, Mail, web fields).
_EDITABLE_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}


def ax_trusted() -> bool:
    """True if VibeFlow has the Accessibility permission (can read the focus)."""
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def request_accessibility(prompt: bool = True) -> bool:
    """Return whether Accessibility is granted; optionally show the system prompt.

    With ``prompt=True`` macOS pops its "grant Accessibility" dialog the first
    time (and deep-links to the right pane). Used by first-run guidance (M4).
    """
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        options = {kAXTrustedCheckOptionPrompt: bool(prompt)}
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        return ax_trusted()


def detect_focus() -> str:
    """Return :data:`EDITABLE`, :data:`NON_EDITABLE`, or :data:`UNKNOWN`."""
    if not ax_trusted():
        return UNKNOWN
    try:
        from ApplicationServices import kAXRoleAttribute, kAXValueAttribute

        element = _focused_element()
        if element is None:
            return UNKNOWN

        role = str(_copy_attr(element, kAXRoleAttribute) or "")
        if role in _EDITABLE_ROLES:
            return EDITABLE  # trust the role (see _EDITABLE_ROLES note)

        # Other roles (rich web editors, custom views) only count as editable if
        # they positively expose a writable value.
        if _is_settable(element, kAXValueAttribute) is True:
            return EDITABLE
        return NON_EDITABLE
    except Exception:
        return UNKNOWN


def _focused_element():
    """The focused UI element, trying the system-wide query first, then the
    frontmost application's own AX element.

    The system-wide ``kAXFocusedUIElementAttribute`` intermittently returns
    nothing when queried off the main thread; asking the frontmost app directly
    (via its pid) is a reliable fallback that recovers those cases.
    """
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCreateSystemWide,
        kAXFocusedUIElementAttribute,
    )

    element = _copy_attr(AXUIElementCreateSystemWide(), kAXFocusedUIElementAttribute)
    if element is not None:
        return element

    try:
        from . import appdetect

        pid = appdetect.frontmost_pid()
        if pid:
            app_el = AXUIElementCreateApplication(pid)
            return _copy_attr(app_el, kAXFocusedUIElementAttribute)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Thin AX helpers (each returns None / None-ish on any failure)
# ---------------------------------------------------------------------------
def _copy_attr(element, attribute):
    """Value of an AX attribute, or ``None`` if it can't be read."""
    try:
        from ApplicationServices import AXUIElementCopyAttributeValue

        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
        return value if err == _AX_SUCCESS else None
    except Exception:
        return None


def _is_settable(element, attribute):
    """``True``/``False`` if the attribute is (not) settable, ``None`` if unknown."""
    try:
        from ApplicationServices import AXUIElementIsAttributeSettable

        err, settable = AXUIElementIsAttributeSettable(element, attribute, None)
        return bool(settable) if err == _AX_SUCCESS else None
    except Exception:
        return None
