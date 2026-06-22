"""macOS privacy-permission checks + deep-links.

macOS gates the three capabilities VibeFlow needs behind System Settings →
Privacy & Security (docs/MACOS_PORT.md §6):

  * **Microphone** — to record,
  * **Accessibility** — to read the focused element and inject Cmd+V,
  * **Input Monitoring** — for the global push-to-talk listener.

This module reports which are granted and opens the exact settings pane for a
missing one (via the ``x-apple.systempreferences:`` URL scheme). It never
*forces* anything — first-run UX uses it to guide the user, and every check is
best-effort (an unknown state is reported as "granted" so we never nag wrongly).
"""

from __future__ import annotations

import subprocess

# Deep-link URLs for the individual Privacy panes.
_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_"
PANE_MICROPHONE = _PANE + "Microphone"
PANE_ACCESSIBILITY = _PANE + "Accessibility"
PANE_INPUT_MONITORING = _PANE + "ListenEvent"


def accessibility_ok() -> bool:
    """True if the Accessibility permission is granted (focus read + keystrokes)."""
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return True  # can't tell → don't nag


def microphone_ok() -> bool:
    """Best-effort: True unless the OS reports the mic as explicitly denied.

    Uses AVFoundation's authorization status when available. ``NotDetermined``
    (0) counts as OK — the first ``Recorder.start()`` triggers the system prompt,
    which is the right moment to ask.
    """
    try:
        from AVFoundation import (
            AVCaptureDevice,
            AVMediaTypeAudio,
            AVAuthorizationStatusDenied,
            AVAuthorizationStatusRestricted,
        )

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        return status not in (AVAuthorizationStatusDenied, AVAuthorizationStatusRestricted)
    except Exception:
        return True  # framework/symbol unavailable → don't nag


def input_monitoring_ok() -> bool:
    """True if Input Monitoring (key-event listening) is granted.

    Uses ``IOHIDCheckAccess`` when available; falls back to the Accessibility
    state, which in practice is granted alongside Input Monitoring for a global
    keyboard listener. Unknown → OK (don't nag).
    """
    try:
        from Quartz import IOHIDCheckAccess, kIOHIDRequestTypeListenEvent

        # 0 == kIOHIDAccessTypeGranted
        return int(IOHIDCheckAccess(kIOHIDRequestTypeListenEvent)) == 0
    except Exception:
        return accessibility_ok()


def missing() -> list[str]:
    """Names of the *required* permissions still needing a grant (in setup order).

    Only **Microphone** and **Accessibility** are required: Accessibility covers
    both the global push-to-talk listener and the Cmd+V paste (pynput's event tap
    + key posting). Input Monitoring is not listed — it's a redundant fallback on
    current macOS and asking for it just adds a step. See :func:`input_monitoring_ok`.
    """
    out = []
    if not microphone_ok():
        out.append("Microphone")
    if not accessibility_ok():
        out.append("Accessibility")
    return out


def open_pane(permission: str) -> None:
    """Open System Settings at the pane for ``permission`` (best-effort)."""
    url = {
        "Microphone": PANE_MICROPHONE,
        "Accessibility": PANE_ACCESSIBILITY,
        "Input Monitoring": PANE_INPUT_MONITORING,
    }.get(permission)
    if not url:
        return
    try:
        subprocess.Popen(["open", url])
    except Exception:
        pass


def request_microphone() -> None:
    """Trigger the microphone permission prompt up front (best-effort).

    Doing this at launch — rather than on the first push-to-talk — means the
    system prompt never appears *mid-dictation* (where it would swallow the
    hotkey's key-release and leave recording stuck), and it registers VibeFlow in
    the Microphone list immediately. The completion handler is a no-op; the
    actual grant is read later via :func:`microphone_ok`.
    """
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        def _done(_granted) -> None:
            pass

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio, _done
        )
    except Exception:
        pass


def prompt_accessibility() -> bool:
    """Trigger the system Accessibility prompt (first run). Returns granted-now."""
    try:
        from .focus_detect import request_accessibility

        return request_accessibility(prompt=True)
    except Exception:
        return accessibility_ok()
