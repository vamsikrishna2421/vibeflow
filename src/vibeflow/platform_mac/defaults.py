"""macOS-specific config defaults.

The shared :mod:`vibeflow.config` ships Windows-oriented defaults (``ctrl+win``
push-to-talk, ``ctrl+shift+v`` delivery). Rather than fork ``config.py`` — it is
shared cross-platform and must stay Windows-correct — the Mac app overlays a few
Mac-friendly defaults *at load time*, but only where the user hasn't chosen
something else.

Convention (per docs/MACOS_PORT.md §3): Windows Ctrl ↔ macOS Cmd. Push-to-talk
defaults to holding **Right Cmd**; paste is **Cmd+V**; the delivery hotkey is
**Cmd+Shift+V**.
"""

from __future__ import annotations

from .. import config as config_mod

# Windows defaults we transparently remap to their Mac equivalents when the user
# is still on the shipped default (i.e. hasn't customised the key themselves).
_WIN_PTT_DEFAULT = "ctrl+win"
_MAC_PTT_DEFAULT = "cmd_r"  # hold Right Command to talk
_MAC_DELIVER_DEFAULT = "cmd+shift+v"

_WIN_MAX_SECONDS = 120      # the shipped single-recording cap
_MAC_MAX_SECONDS = 600      # Mac default: allow up to 10-minute dictations


def apply_mac_defaults(cfg: config_mod.Config) -> config_mod.Config:
    """Mutate ``cfg`` in place so untouched Windows defaults become Mac defaults.

    Only keys still holding the shipped Windows default are changed, so a user's
    explicit choice (from the YAML file) is always preserved. The config is *not*
    saved here — these are runtime defaults; they persist only if the user later
    changes a setting that triggers a save.
    """
    ptt = str(cfg.get("hotkey.push_to_talk_key", _WIN_PTT_DEFAULT))
    if ptt.strip().lower() == _WIN_PTT_DEFAULT:
        cfg.set("hotkey.push_to_talk_key", _MAC_PTT_DEFAULT)

    toggle = str(cfg.get("hotkey.toggle_combo", _WIN_PTT_DEFAULT))
    if toggle.strip().lower() == _WIN_PTT_DEFAULT:
        cfg.set("hotkey.toggle_combo", _MAC_PTT_DEFAULT)

    deliver = str(cfg.get("text.modes.deliver_hotkey", "ctrl+shift+v"))
    if deliver.strip().lower() == "ctrl+shift+v":
        cfg.set("text.modes.deliver_hotkey", _MAC_DELIVER_DEFAULT)

    # When focus can't be determined, prefer pasting into the frontmost app over
    # silently parking on the clipboard — the transcript is always copied too, so
    # this only changes the ambiguous case. (Windows defaults to "clipboard".)
    if str(cfg.get("output.auto_fallback", "clipboard")).strip().lower() == "clipboard":
        cfg.set("output.auto_fallback", "type")

    # The model menu now offers only small/medium (medium recommended). Migrate any
    # earlier choice that's no longer selectable (base, large, turbo, …) to medium
    # so existing users aren't left on a model that's gone from the UI.
    if str(cfg.get("model.size", "medium")).strip().lower() not in ("small", "medium"):
        cfg.set("model.size", "medium")

    # Allow longer single dictations on Mac (10 min). This is the auto-stop safety
    # cap, not a product limit; only bump it when the user is still on the shipped
    # 120s default so an explicit choice is preserved.
    try:
        if int(cfg.get("audio.max_seconds", 120) or 120) == _WIN_MAX_SECONDS:
            cfg.set("audio.max_seconds", _MAC_MAX_SECONDS)
    except (TypeError, ValueError):
        pass

    return cfg


def load_mac_config(path=None):
    """Load the shared config and overlay the Mac defaults."""
    return apply_mac_defaults(config_mod.load_config(path))
