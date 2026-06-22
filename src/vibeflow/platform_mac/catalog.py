"""macOS app catalogs + a thin per-app outcome resolver.

The pure outcome resolver lives in :mod:`vibeflow.core.appmode` and is reused
as-is. What's platform-specific is the **data**: the Windows catalogs hold
``.exe`` names, so this module supplies the Mac equivalents keyed by **bundle id**
(preferred, e.g. ``com.apple.mail``) or **localized app name** (fallback). The
detection side feeds a ``core.appmode.AppIdentity`` whose ``exe`` is the bundle
id or name (lowercased); see :mod:`vibeflow.platform_mac.appdetect`.

``resolve_outcome`` here is a thin wrapper: user rules win (resolved by the core
logic, which already matches a bundle-id rule value against ``AppIdentity.exe``),
then the Mac built-in "leave as spoken" surfaces (terminals + code editors),
else ``DEFAULT`` — mirroring the Windows precedence exactly.
"""

from __future__ import annotations

from ..core.appmode import (  # outcomes + the (pure) rule-matching internals
    AppIdentity,
    CASUAL,
    DEFAULT,
    EMAIL,
    OUTCOMES,
    VERBATIM,
    BY_PROCESS,
    BY_TITLE,
    EMAIL_TITLE_HINTS,
    _rule_matches,
    _SPECIFICITY,
)

# --- "Leave as spoken" surfaces: terminals + code editors --------------------
# Matched against AppIdentity.exe (bundle id when known, else app name), all
# lowercased. We list both the bundle ids and the friendly names so detection
# works whether or not a bundle id was resolvable.
_TERMINAL_IDS = {
    "com.apple.terminal", "com.googlecode.iterm2",
    "dev.warp.warp-stable", "dev.warp.warp",
    "io.alacritty", "org.alacritty", "net.kovidgoyal.kitty",
    "com.github.wez.wezterm", "com.mitchellh.ghostty",
}
_TERMINAL_NAMES = {
    "terminal", "iterm2", "iterm", "warp", "alacritty", "kitty",
    "wezterm", "ghostty",
}
_EDITOR_IDS = {
    "com.microsoft.vscode", "com.microsoft.vscodeinsiders", "com.apple.dt.xcode",
    "com.sublimetext.4", "com.sublimetext.3", "com.sublimetext.2",
    "com.jetbrains.intellij", "com.jetbrains.intellij.ce",
    "com.jetbrains.pycharm", "com.jetbrains.pycharm.ce",
    "com.jetbrains.goland", "com.jetbrains.webstorm", "com.jetbrains.clion",
    "com.jetbrains.rider", "com.jetbrains.datagrip", "com.jetbrains.rubymine",
    "com.jetbrains.phpstorm", "com.google.android.studio",
}
_EDITOR_NAMES = {
    "code", "code - insiders", "visual studio code", "xcode", "sublime text",
    "intellij idea", "pycharm", "goland", "webstorm", "clion", "rider",
    "datagrip", "rubymine", "phpstorm", "android studio",
}
_VERBATIM = _TERMINAL_IDS | _TERMINAL_NAMES | _EDITOR_IDS | _EDITOR_NAMES

# --- Email apps (Starter Pack → email draft) ---------------------------------
_EMAIL_IDS = {
    "com.apple.mail", "com.microsoft.outlook",
    "com.readdle.smartemail-mac", "it.bloop.airmail2", "com.airmailapp.airmail",
}
_EMAIL_NAMES = {"mail", "microsoft outlook", "outlook", "spark", "airmail"}
_EMAIL = _EMAIL_IDS | _EMAIL_NAMES

# --- Chat apps (Starter Pack → casual) ---------------------------------------
_CHAT_IDS = {
    "com.tinyspeck.slackmacgap", "com.microsoft.teams", "com.microsoft.teams2",
    "com.hnc.discord", "net.whatsapp.whatsapp", "desktop.whatsapp",
    "ru.keepcoder.telegram", "org.telegram.desktop",
    "org.whispersystems.signal-desktop", "com.apple.messagesnotificationextension",
    "com.apple.ichat", "com.apple.messages",
}
_CHAT_NAMES = {
    "slack", "microsoft teams", "teams", "discord", "whatsapp",
    "telegram", "signal", "messages",
}
_CHAT = _CHAT_IDS | _CHAT_NAMES


def _mac_builtin_outcome(app: AppIdentity) -> str | None:
    """Built-in verbatim surfaces (terminals + code editors), else ``None``."""
    return VERBATIM if (app and app.exe in _VERBATIM) else None


def resolve_outcome(app: AppIdentity, rules: list[dict] | None) -> str:
    """Resolve the formatting outcome for ``app`` on macOS (pure, safe-by-default).

    Order mirrors :func:`vibeflow.core.appmode.resolve_outcome`: protected →
    verbatim (never happens on macOS), then the most *specific* matching user
    rule, then a Mac built-in verbatim surface, else ``DEFAULT``.
    """
    if app is None:
        return DEFAULT
    if app.protected:  # unused on macOS, but keep the safe contract
        return VERBATIM

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

    return _mac_builtin_outcome(app) or DEFAULT


def app_category(exe: str) -> str | None:
    """'email', 'chat', or ``None`` — used to offer the Starter Pack in context."""
    exe = (exe or "").lower()
    if exe in _EMAIL:
        return "email"
    if exe in _CHAT:
        return "chat"
    return None


def starter_pack_rules() -> list[dict]:
    """One-click sensible rules for macOS: email → email draft, chat → casual.

    Native apps match by bundle id / name (BY_PROCESS); webmail in a browser
    matches by window title (the OS-neutral hints from core). Terminals and code
    editors are already verbatim by built-in default, so they need no rule. Rules
    for apps you don't have simply never match.
    """
    rules = [{"match": {"by": BY_PROCESS, "value": v}, "outcome": EMAIL}
             for v in sorted(_EMAIL)]
    rules += [{"match": {"by": BY_TITLE, "value": t}, "outcome": EMAIL}
              for t in EMAIL_TITLE_HINTS]
    rules += [{"match": {"by": BY_PROCESS, "value": v}, "outcome": CASUAL}
              for v in sorted(_CHAT)]
    return rules
