"""VibeFlow **core** — the platform-agnostic "brain".

These modules contain VibeFlow's intelligence and have **no operating-system,
GUI, audio, or speech-engine dependencies** — only the Python standard library
(plus ``urllib`` for talking to a local LLM). That makes them the reusable layer
for every platform (Windows today; macOS / Android / iOS later): only the thin
"hands" — mic capture, the speech engine, text insertion, the hotkey, and the
tray/menu-bar UI — are written per platform.

What lives here:
  * :mod:`~vibeflow.core.appmode`    — per-app formatting outcome resolver
  * :mod:`~vibeflow.core.curate`     — deterministic transcript cleanup / fillers
  * :mod:`~vibeflow.core.text`       — text helpers + snippet expansion
  * :mod:`~vibeflow.core.ai_format`  — local-LLM formatting, tone, persona, teach-back
  * :mod:`~vibeflow.core.vocabulary` — adaptive vocabulary
  * :mod:`~vibeflow.core.persona`    — on-device writing-style profile
  * :mod:`~vibeflow.core.history`    — local, capped dictation history

``vibeflow.config`` stays one level up because it resolves platform-specific
paths (``%APPDATA%`` / XDG), but it is otherwise pure and shared by core too.

Note: :func:`vibeflow.core.appmode.target_app` uses Win32 only *inside* the
function (guarded), so importing this package is safe on any OS — it simply
returns an empty identity where it can't detect the foreground window.
"""

from . import ai_format, appmode, curate, history, persona, text, vocabulary

__all__ = [
    "ai_format",
    "appmode",
    "curate",
    "history",
    "persona",
    "text",
    "vocabulary",
]
