"""Single-instance guard for macOS.

The shared :mod:`vibeflow.single_instance` is a Windows mutex (a no-op
elsewhere), so the Mac app uses an advisory **lock file** in ``config_dir()``.
``open``-launching a ``.app`` already coalesces to one instance via
LaunchServices, but running from source (or leftover dev processes) can stack
several copies that each grab the hotkey and fight over the clipboard — this
prevents that.

``acquire()`` returns an opaque handle to keep alive for the process lifetime,
or ``None`` if another instance already holds the lock.
"""

from __future__ import annotations

from .. import config as config_mod

_LOCK_NAME = "vibeflow.lock"


def acquire():
    """Take the single-instance lock, or return ``None`` if already held."""
    try:
        import fcntl

        path = config_mod.config_dir() / _LOCK_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None  # another instance holds it
        handle.write(str(_pid()))
        handle.flush()
        return handle  # caller keeps this alive; closing/exiting releases it
    except Exception:
        # If anything goes wrong, fail open (don't block the app from starting).
        return object()


def _pid() -> int:
    import os

    return os.getpid()
