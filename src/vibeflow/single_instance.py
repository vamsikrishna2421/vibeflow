"""Guarantee only one Mynah runs at a time.

On Windows this uses a named mutex held for the lifetime of the process — the
OS releases it automatically if the app exits or crashes, so the lock can never
get "stuck". A second launch finds the mutex already exists, shows a friendly
dialog, and exits. A POSIX file-lock fallback is provided for completeness.
"""

from __future__ import annotations

import sys

# A stable, app-specific name. "Local\\" scopes it to the current login session,
# which is what we want for a per-user desktop app.
_MUTEX_NAME = "Local\\VibeFlow_SingleInstance_Mutex_v1"
_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Acquire/hold a process-wide single-instance lock."""

    def __init__(self, name: str = _MUTEX_NAME) -> None:
        self._name = name
        self._handle = None
        self._fp = None
        self.already_running = False

    def acquire(self) -> bool:
        """Return True if we got the lock, False if another instance holds it."""
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def _acquire_windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._handle = kernel32.CreateMutexW(None, True, self._name)
        last_error = kernel32.GetLastError()
        if not self._handle:
            # Could not create the mutex at all: fail open so the user is never
            # locked out of their own app.
            return True
        if last_error == _ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return True

    def _acquire_posix(self) -> bool:  # pragma: no cover - non-Windows
        import atexit
        import os
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "vibeflow.single.lock")
        try:
            import fcntl

            self._fp = open(path, "w")
            try:
                fcntl.flock(self._fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.already_running = True
                return False
            atexit.register(self.release)
            return True
        except Exception:
            return True

    def release(self) -> None:
        if self._handle is not None and sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.kernel32.ReleaseMutex(self._handle)
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        if self._fp is not None:  # pragma: no cover - non-Windows
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None


def notify_already_running() -> None:
    """Tell the user (via a small dialog) that Mynah is already running."""
    message = (
        "Mynah is already running.\n\n"
        "Look for the Mynah icon in the system tray (near the clock — click "
        "the up-arrow ↑ to show hidden icons)."
    )
    if sys.platform != "win32":
        print(message)
        return
    try:
        import ctypes

        MB_OK = 0x0
        MB_ICONINFORMATION = 0x40
        MB_TOPMOST = 0x40000
        ctypes.windll.user32.MessageBoxW(
            None, message, "Mynah", MB_OK | MB_ICONINFORMATION | MB_TOPMOST
        )
    except Exception:
        pass
