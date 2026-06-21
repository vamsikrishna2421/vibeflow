"""Per-app formatting — identify the destination app and resolve its outcome.

VibeFlow can format a dictation differently depending on *where* it lands: a
shell command in a terminal should stay exactly as spoken, an email should be
cleaned up and made professional, a chat message kept casual. This module has
two halves:

  * :func:`target_app` — a thin, crash-proof Win32 probe that returns the
    foreground window's identity (executable, window class, friendly name) so a
    rule can match it. If the foreground process cannot be queried — which on
    Windows means it is running at a higher integrity level than VibeFlow, e.g.
    an *administrator* terminal — the identity is marked ``protected`` so the
    resolver falls back to verbatim. Reformatting a command we can't even
    identify is the unsafe choice.

  * :func:`resolve_outcome` — a **pure** function (app identity + the user's
    rules -> an outcome) so it can be unit-tested exhaustively, mirroring
    :func:`vibeflow.output.decide_target`.

Privacy: a window *title* is only read to evaluate user-authored
``title_contains`` rules, and is **never** logged. Callers must keep it that way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Outcomes a rule can select. ``DEFAULT`` means "do exactly what VibeFlow does
# today" (light clean-up + filler removal + persona) — the global behaviour.
VERBATIM = "verbatim"          # "Leave as spoken" — raw transcript, no AI/fillers
PROFESSIONAL = "professional"  # AI, formal tone, voice-preserving
CASUAL = "casual"              # AI, casual tone, voice-preserving
DEFAULT = "default"            # today's global clean-up

OUTCOMES = (VERBATIM, PROFESSIONAL, CASUAL, DEFAULT)

# Match kinds, ranked by specificity (more specific wins when several rules
# match). A user's explicit title/class rule should beat a broad process rule.
BY_TITLE = "title_contains"
BY_CLASS = "window_class"
BY_PROCESS = "process"
_SPECIFICITY = {BY_TITLE: 3, BY_CLASS: 2, BY_PROCESS: 1}

# Built-in "leave as spoken" surfaces (lowest priority — any user rule overrides
# them). Terminals: dictating commands/symbols must stay verbatim. Editors: the
# user chose verbatim-by-default for code editors to protect dictated code; a
# one-tap "re-insert with clean-up" handles the prose case.
_TERMINAL_CLASS_HINTS = (
    "cascadia_hosting_window_class", "consolewindowclass",
    "pseudoconsolewindow", "windowsterminal",
)
_TERMINAL_EXES = (
    "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
    "windowsterminal.exe", "wt.exe", "wsl.exe", "bash.exe", "alacritty.exe",
    "wezterm-gui.exe", "wezterm.exe", "mintty.exe",
)
_EDITOR_EXES = (
    "code.exe", "code - insiders.exe", "devenv.exe", "idea64.exe",
    "pycharm64.exe", "goland64.exe", "rider64.exe", "webstorm64.exe",
    "clion64.exe", "sublime_text.exe", "notepad++.exe",
)

# Catalogs used by the (Phase 2) Starter Pack to suggest sensible rules.
EMAIL_EXES = ("outlook.exe", "hxmail.exe", "thunderbird.exe", "em client.exe")
CHAT_EXES = (
    "slack.exe", "teams.exe", "ms-teams.exe", "discord.exe",
    "whatsapp.exe", "telegram.exe", "signal.exe",
)

# Friendly display names for apps we recognise (used by the overlay and picker;
# falls back to a title-cased exe stem otherwise).
_FRIENDLY = {
    "code.exe": "VS Code", "devenv.exe": "Visual Studio", "idea64.exe": "IntelliJ",
    "pycharm64.exe": "PyCharm", "windowsterminal.exe": "Windows Terminal",
    "wt.exe": "Windows Terminal", "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell",
    "outlook.exe": "Outlook", "slack.exe": "Slack", "teams.exe": "Teams",
    "ms-teams.exe": "Teams", "discord.exe": "Discord", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "msedge.exe": "Edge", "chrome.exe": "Chrome",
    "firefox.exe": "Firefox", "notepad++.exe": "Notepad++",
    "sublime_text.exe": "Sublime Text",
}


def friendly_name(exe: str) -> str:
    """Human-readable app name for an executable basename."""
    exe = (exe or "").lower()
    if exe in _FRIENDLY:
        return _FRIENDLY[exe]
    stem = exe[:-4] if exe.endswith(".exe") else exe
    return stem.replace("_", " ").replace("-", " ").title() if stem else "this app"


@dataclass(frozen=True)
class AppIdentity:
    """Identity of the window a dictation is destined for."""
    exe: str = ""            # lowercased basename, e.g. "code.exe"
    window_class: str = ""   # lowercased window class
    title: str = ""          # window title — for title rules ONLY; never log it
    protected: bool = False  # True => couldn't query the process (elevated) => verbatim

    @property
    def friendly(self) -> str:
        return friendly_name(self.exe)


def _builtin_outcome(app: AppIdentity) -> str | None:
    """Built-in verbatim surfaces (terminals + code editors), else ``None``."""
    cls = app.window_class
    if any(h in cls for h in _TERMINAL_CLASS_HINTS):
        return VERBATIM
    if app.exe in _TERMINAL_EXES or app.exe in _EDITOR_EXES:
        return VERBATIM
    return None


def _rule_matches(match: dict, app: AppIdentity) -> bool:
    by = (match or {}).get("by")
    value = ((match or {}).get("value") or "").strip().lower()
    if not value:
        return False
    if by == BY_PROCESS:
        exe = value if value.endswith(".exe") else value + ".exe"
        return app.exe == exe or app.exe == value
    if by == BY_CLASS:
        return value in app.window_class
    if by == BY_TITLE:
        return value in (app.title or "").lower()
    return False


def resolve_outcome(app: AppIdentity, rules: list[dict] | None) -> str:
    """Resolve the formatting outcome for ``app`` (pure; safe-by-default).

    Order: protected/elevated -> VERBATIM; then the most *specific* matching
    user rule; then a built-in verbatim surface (terminal/editor); else DEFAULT.
    """
    if app is None:
        return DEFAULT
    if app.protected:
        return VERBATIM  # can't identify it -> never AI-rewrite (e.g. admin terminal)

    best_rank = 0
    best_outcome: str | None = None
    for rule in rules or []:
        match = rule.get("match") if isinstance(rule, dict) else None
        outcome = rule.get("outcome") if isinstance(rule, dict) else None
        if outcome not in OUTCOMES or not _rule_matches(match or {}, app):
            continue
        rank = _SPECIFICITY.get((match or {}).get("by"), 0)
        if rank > best_rank:  # ties keep the earlier rule (first match wins)
            best_rank, best_outcome = rank, outcome
    if best_outcome is not None:
        return best_outcome

    return _builtin_outcome(app) or DEFAULT


def shadowed_by(new_match: dict, rules: list[dict] | None) -> dict | None:
    """Return an existing rule that would match *before* ``new_match`` (i.e. is
    equal or more specific), so the Manage UI can warn about a dead rule."""
    new_rank = _SPECIFICITY.get((new_match or {}).get("by"), 0)
    for rule in rules or []:
        m = rule.get("match") if isinstance(rule, dict) else None
        if not m:
            continue
        if _SPECIFICITY.get(m.get("by"), 0) >= new_rank and \
                (m.get("value") or "").strip().lower() == ((new_match or {}).get("value") or "").strip().lower() and \
                m.get("by") == (new_match or {}).get("by"):
            return rule
    return None


# ---------------------------------------------------------------------------
# Win32 detection (crash-proof; returns a best-effort AppIdentity)
# ---------------------------------------------------------------------------
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_hwnd() -> int:
    """Current foreground window handle (0 if none / non-Windows). Never raises."""
    import sys
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        return int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def target_app(hwnd: int | None = None) -> AppIdentity:
    """Identify the foreground window (or ``hwnd`` if given).

    Never raises. If the process can't be queried (higher integrity level than
    VibeFlow), the result is marked ``protected`` so the resolver picks verbatim.
    """
    import sys
    if sys.platform != "win32":
        return AppIdentity()
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = hwnd or user32.GetForegroundWindow()
        if not hwnd:
            return AppIdentity()  # no target -> DEFAULT (not protected)

        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        window_class = (cls_buf.value or "").lower()

        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value or ""  # for title_contains rules only; never log

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return AppIdentity(window_class=window_class, title=title)

        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            # Access denied => elevated/higher-integrity target => protected.
            return AppIdentity(window_class=window_class, title=title, protected=True)
        try:
            size = wintypes.DWORD(1024)
            path_buf = ctypes.create_unicode_buffer(1024)
            ok = kernel32.QueryFullProcessImageNameW(
                handle, 0, path_buf, ctypes.byref(size)
            )
        finally:
            kernel32.CloseHandle(handle)
        if not ok or not path_buf.value:
            return AppIdentity(window_class=window_class, title=title, protected=True)

        exe = os.path.basename(path_buf.value).lower()
        return AppIdentity(exe=exe, window_class=window_class, title=title)
    except Exception:
        # Unknown failure -> don't force verbatim on a normal app; DEFAULT is safe.
        return AppIdentity()
