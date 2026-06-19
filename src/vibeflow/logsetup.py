"""Logging and stdout/stderr setup.

A windowed (no-console) build has ``sys.stdout``/``sys.stderr`` set to ``None``.
That (a) can crash libraries that write progress/warnings, and (b) leaves us no
way to see errors. This module routes output to a log file in the app-data
folder (``%APPDATA%\\VibeFlow\\vibeflow.log``) and wires up the logging module.
In a normal console it just makes output UTF-8 / error-tolerant.
"""

from __future__ import annotations

import logging
import sys

_done = False


class _Null:
    """A stream that silently discards writes (last-resort fallback)."""

    def write(self, *_args, **_kwargs):
        return 0

    def flush(self):
        pass


def log_path():
    from .config import config_dir

    return config_dir() / "vibeflow.log"


def setup() -> None:
    """Idempotently configure streams + logging. Safe to call once at startup."""
    global _done
    if _done:
        return
    _done = True

    have_console = sys.stdout is not None and sys.stderr is not None

    path = None
    try:
        from .config import config_dir

        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "vibeflow.log"
    except Exception:
        path = None

    if have_console:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                try:
                    stream.reconfigure(errors="replace")
                except Exception:
                    pass
    else:
        # Windowed build: send stdout/stderr to the log file so writes never
        # crash and we capture library diagnostics.
        if path is not None:
            try:
                handle = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
                if sys.stdout is None:
                    sys.stdout = handle
                if sys.stderr is None:
                    sys.stderr = handle
            except Exception:
                pass
        if sys.stdout is None:
            sys.stdout = _Null()
        if sys.stderr is None:
            sys.stderr = _Null()

    handlers = []
    if path is not None:
        try:
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except Exception:
            pass
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=handlers or None,
        )
    except Exception:
        pass

    try:
        from . import __app_name__, __version__

        logging.getLogger("vibeflow").info(
            "%s %s starting (frozen=%s, console=%s)",
            __app_name__,
            __version__,
            getattr(sys, "frozen", False),
            have_console,
        )
    except Exception:
        pass
