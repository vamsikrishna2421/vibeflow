"""Frontmost-application identity on macOS.

The Mac replacement for the Win32 ``foreground_hwnd`` / ``target_app`` probes
that live inside :mod:`vibeflow.core.appmode`. Per docs/MACOS_PORT.md §4 this
must **not** go in core — core stays platform-neutral. Instead we build a
``core.appmode.AppIdentity`` from ``NSWorkspace.frontmostApplication()`` here and
let the (pure) core resolver decide the outcome.

On macOS there is no "elevated process" notion, so ``protected`` stays ``False``
(the Windows safety fallback is unused here). The ``exe`` field carries the app's
**bundle id** (e.g. ``com.apple.mail``) when available, falling back to the
localized app name — the Mac catalog (M3) matches on either.

Privacy mirrors core: a window *title* is only read for user ``title_contains``
rules and is never logged.
"""

from __future__ import annotations

from ..core.appmode import AppIdentity


def frontmost_app():
    """``(name, bundle_id, pid)`` for the frontmost app, or ``(None, None, 0)``.

    Never raises. ``pid`` is the stable identity used to re-verify focus didn't
    move between deciding the output and pasting it (the Mac analogue of the
    Windows ``expected_hwnd`` check).
    """
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return (None, None, 0)
        name = app.localizedName()
        bundle = app.bundleIdentifier()
        pid = int(app.processIdentifier() or 0)
        return (str(name) if name else None, str(bundle) if bundle else None, pid)
    except Exception:
        return (None, None, 0)


def frontmost_pid() -> int:
    """PID of the frontmost app (0 if unknown). The Mac ``foreground_hwnd``."""
    return frontmost_app()[2]


def _focused_window_title() -> str:
    """Title of the focused window via Accessibility, or ``""``.

    Used only to evaluate user ``title_contains`` rules (e.g. webmail in a
    browser). Returns empty when Accessibility isn't granted — rules that need a
    title simply don't match, which is safe.
    """
    try:
        from ApplicationServices import (
            AXUIElementCreateSystemWide,
            AXUIElementCopyAttributeValue,
            kAXFocusedApplicationAttribute,
            kAXFocusedWindowAttribute,
            kAXTitleAttribute,
        )

        system = AXUIElementCreateSystemWide()
        err, app = AXUIElementCopyAttributeValue(
            system, kAXFocusedApplicationAttribute, None
        )
        if err != 0 or app is None:
            return ""
        err, window = AXUIElementCopyAttributeValue(
            app, kAXFocusedWindowAttribute, None
        )
        if err != 0 or window is None:
            return ""
        err, title = AXUIElementCopyAttributeValue(window, kAXTitleAttribute, None)
        return str(title) if (err == 0 and title) else ""
    except Exception:
        return ""


def identify() -> tuple[AppIdentity, str, int]:
    """One-shot ``(AppIdentity, display_name, pid)`` for the frontmost app.

    ``display_name`` is the localized app name (for the overlay / notifications);
    the ``AppIdentity`` carries the lowercased bundle id (or name) for matching.
    Fetches everything in a single pass so the app can't change underneath us.
    Never raises.
    """
    name, bundle, pid = frontmost_app()
    title = _focused_window_title()
    exe = (bundle or name or "").lower()
    identity = AppIdentity(exe=exe, window_class="", title=title, protected=False)
    return identity, (name or "this app"), pid


def target_app(pid: int | None = None) -> AppIdentity:
    """Identity of the frontmost app as a ``core.appmode.AppIdentity``.

    ``exe`` holds the bundle id (preferred) or app name, both **lowercased** to
    match the catalog and the core resolver's case-folding. ``window_class`` is
    unused on macOS. Never raises; returns an empty identity on any failure (the
    resolver then yields the safe DEFAULT outcome).
    """
    try:
        name, bundle, _pid = frontmost_app()
        exe = (bundle or name or "").lower()
        title = _focused_window_title()
        return AppIdentity(exe=exe, window_class="", title=title, protected=False)
    except Exception:
        return AppIdentity()
