"""Start VibeFlow automatically when the user signs in to Windows.

Implemented with the per-user ``HKCU\\...\\Run`` registry value, which needs no
administrator rights. The installer sets the same value, so the tray toggle and
the installer stay consistent (the value name is the single source of truth).
"""

from __future__ import annotations

import os
import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "VibeFlow"


def _command() -> str:
    """The command Windows should run at login."""
    if getattr(sys, "frozen", False):
        # Packaged VibeFlow.exe — just run it.
        return f'"{sys.executable}"'
    # Running from source / pip install: prefer the windowless interpreter.
    exe = sys.executable
    pythonw = exe.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = exe
    return f'"{pythonw}" -m vibeflow'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        return True
    except FileNotFoundError:
        return True  # already not set
    except OSError:
        return False


def toggle() -> bool:
    """Flip auto-start. Returns the new state (True = will start with Windows)."""
    if is_enabled():
        disable()
        return False
    enable()
    return True
