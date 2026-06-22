"""Start VibeFlow automatically at login on macOS.

The Mac counterpart to the Windows ``autostart`` (an ``HKCU\\…\\Run`` value).
Here it's a per-user **LaunchAgent**: a small plist in
``~/Library/LaunchAgents/com.vibeflow.VibeFlow.plist`` with ``RunAtLoad`` true,
loaded/unloaded via ``launchctl``. No admin rights needed.

The same public API as the Windows module (``is_enabled`` / ``enable`` /
``disable`` / ``toggle``) so the menu toggle is symmetric across platforms.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LABEL = "com.vibeflow.VibeFlow"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _program_args() -> list[str]:
    """The command launchd should run at login.

    Frozen ``.app`` (M5): launch the bundled executable directly. From source:
    run this repo's Mac entry point with the current interpreter, pinning the
    repo root so it works regardless of the login working directory.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    launcher = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "launch_mac.py"
    return [sys.executable, str(launcher)]


def _plist_text() -> str:
    args = "".join(f"\n    <string>{a}</string>" for a in _program_args())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n"
        f"  <array>{args}\n  </array>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>ProcessType</key>\n"
        "  <string>Interactive</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def is_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return _plist_path().exists()


def enable() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        path = _plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_plist_text(), encoding="utf-8")
        # Best-effort load now so it also starts this session's next login without
        # a reboot. Ignore failures (already loaded / no launchd in a sandbox).
        subprocess.run(
            ["launchctl", "load", "-w", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return True
    except Exception:
        return False


def disable() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        path = _plist_path()
        if path.exists():
            subprocess.run(
                ["launchctl", "unload", "-w", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            os.remove(path)
        return True
    except Exception:
        return False


def toggle() -> bool:
    """Flip auto-start. Returns the new state (True = will start at login)."""
    if is_enabled():
        disable()
        return False
    enable()
    return True
