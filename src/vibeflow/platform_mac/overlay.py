"""On-screen status overlay for macOS.

The Mac counterpart to the Windows ``overlay.py`` — a small floating pill near
the bottom of the screen that shows "Listening…", "Transcribing…", "Inserted",
"Copied — ⌘⇧V to place", etc.

It is a **non-activating** borderless ``NSPanel``: it shows *without ever taking
keyboard focus*, which is essential — if it stole focus it would break the
in-place paste. It also floats above other windows, ignores the mouse, and shows
on every Space.

All methods MUST be called on the main thread (the app drives them from its
``rumps.Timer`` tick). Construction is lazy so importing this module is cheap and
safe in headless/test environments.
"""

from __future__ import annotations

import logging

log = logging.getLogger("vibeflow")

_PAD_X, _PAD_Y = 18.0, 10.0   # padding around the text
_MARGIN_BOTTOM = 120.0        # distance above the screen's bottom edge


class StatusOverlay:
    """A focus-safe floating status pill."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self._panel = None
        self._label = None
        self._visible = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.hide()

    # -- main-thread API ------------------------------------------------
    def show(self, text: str) -> None:
        if not self.enabled or not text:
            return
        try:
            self._ensure_built()
            self._apply_text(text)
            self._panel.orderFrontRegardless()  # show WITHOUT activating/focusing
            self._visible = True
        except Exception:  # pragma: no cover - overlay is best-effort
            log.debug("overlay show failed", exc_info=True)

    def hide(self) -> None:
        if not self._visible or self._panel is None:
            return
        try:
            self._panel.orderOut_(None)
        except Exception:  # pragma: no cover
            pass
        self._visible = False

    # -- construction (lazy, main thread) -------------------------------
    def _ensure_built(self) -> None:
        if self._panel is not None:
            return
        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSFont,
            NSPanel,
            NSTextField,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowCollectionBehaviorStationary,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSMakeRect

        rect = NSMakeRect(0, 0, 240, 44)
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setLevel_(25)  # NSStatusWindowLevel — above normal windows
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorIgnoresCycle
        )

        content = panel.contentView()
        content.setWantsLayer_(True)
        layer = content.layer()
        layer.setCornerRadius_(12.0)
        layer.setBackgroundColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.82).CGColor()
        )

        label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setTextColor_(NSColor.whiteColor())
        label.setFont_(NSFont.systemFontOfSize_(14.0))
        content.addSubview_(label)

        self._panel = panel
        self._label = label

    def _apply_text(self, text: str) -> None:
        from Foundation import NSMakeRect, NSMakePoint

        label = self._label
        panel = self._panel
        label.setStringValue_(text)
        label.sizeToFit()
        tw = label.frame().size.width
        th = label.frame().size.height
        w = tw + 2 * _PAD_X
        h = th + 2 * _PAD_Y

        # Center the label inside the pill.
        label.setFrame_(NSMakeRect(_PAD_X, _PAD_Y, tw, th))

        # Resize the panel and re-center it horizontally near the screen bottom.
        from AppKit import NSScreen

        screen = NSScreen.mainScreen()
        sf = screen.frame() if screen is not None else None
        panel.setContentSize_((w, h))
        if sf is not None:
            x = sf.origin.x + (sf.size.width - w) / 2.0
            y = sf.origin.y + _MARGIN_BOTTOM
            panel.setFrameOrigin_(NSMakePoint(x, y))
