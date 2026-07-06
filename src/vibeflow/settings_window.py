"""VibeFlow Settings — one window where every common option lives and **stays
open** until you close it (the tray's right-click menu is a native Windows menu
that always closes after a single click; this panel solves that).

Runs as its own process (``VibeFlow.exe --settings``) so it has an independent Tk
main loop and never blocks the tray icon or the dictation hotkey. It edits
``config.yaml``; the running app watches that file and reloads + re-applies the
changes within a second or two (no restart needed for these settings). Speech
accuracy and the AI tier stay in the tray because they download/reload models.
"""

from __future__ import annotations

import os
import sys

_BG = "#0E1730"
_CARD = "#16213E"
_FG = "#F2F4F8"
_MUTED = "#9AA4B2"
_ACCENT = "#5B8DEF"

# (config key, label) — plain on/off settings.
# NB: filler removal is now always-on (deterministic), so it no longer belongs here.
_CHECKS = [
    ("text.modes.enabled", "Adapt formatting to each app (terminals stay as spoken)"),
    ("text.persona", "Match my writing style (Personalized AI)"),
    ("text.teach_back", "Learn from my edits"),
    ("text.history.enabled", "Save dictation history (local, opt-in)"),
    ("feedback.overlay", "Show on-screen status"),
    ("feedback.sounds", "Play start / stop sounds"),
    ("text.debug_log", "Detailed logging (troubleshooting)"),
]
_OUTPUTS = [("Auto — type, else clipboard", "auto"), ("Always type", "type"),
            ("Always copy to clipboard", "clipboard")]


def _icon_path() -> str | None:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(__file__)
    cand = os.path.join(base, "resources", "logos", "vibeflow.ico")
    return cand if os.path.exists(cand) else None


def _make_dpi_aware() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def run(config_path: str | None = None) -> int:
    _make_dpi_aware()
    try:
        import tkinter as tk
    except Exception:
        return 1

    from . import autostart, config as config_mod

    cfg = config_mod.load_config(config_path)

    root = tk.Tk()
    root.title("VibeFlow — Settings")
    root.geometry("470x720")
    root.configure(bg=_BG)
    ico = _icon_path()
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    def card(title):
        tk.Label(root, text=title, bg=_BG, fg=_MUTED, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        f = tk.Frame(root, bg=_CARD)
        f.pack(fill="x", padx=14, pady=(0, 2))
        return f

    def radio(parent, var, options):
        for label, value in options:
            tk.Radiobutton(
                parent, text=label, variable=var, value=value, bg=_CARD, fg=_FG,
                selectcolor=_CARD, activebackground=_CARD, activeforeground=_ACCENT,
                anchor="w", font=("Segoe UI", 10), highlightthickness=0, bd=0,
            ).pack(fill="x", anchor="w", padx=10, pady=1)

    tk.Label(root, text="Settings", bg=_BG, fg=_FG, font=("Segoe UI", 16, "bold"),
             anchor="w").pack(fill="x", padx=18, pady=(16, 0))
    tk.Label(root, text="Flip as many as you like — this window stays open. Changes "
             "apply within a second or two.", bg=_BG, fg=_MUTED, anchor="w",
             font=("Segoe UI", 9), wraplength=430, justify="left").pack(
                 fill="x", padx=18, pady=(0, 2))

    # Output
    out_var = tk.StringVar(value=str(cfg.get("output.mode", "auto") or "auto"))
    radio(card("WHERE DICTATED TEXT GOES"), out_var, _OUTPUTS)

    # Checkboxes
    cardf = card("FORMATTING, LEARNING & FEEDBACK")
    check_vars = {}
    for key, label in _CHECKS:
        var = tk.BooleanVar(value=bool(cfg.get(key, False)))
        check_vars[key] = var
        tk.Checkbutton(
            cardf, text=label, variable=var, bg=_CARD, fg=_FG, selectcolor=_CARD,
            activebackground=_CARD, activeforeground=_ACCENT, anchor="w",
            wraplength=410, justify="left", font=("Segoe UI", 10),
            highlightthickness=0, bd=0,
        ).pack(fill="x", anchor="w", padx=10, pady=1)
    # Autostart is a registry setting, not config — handle it specially.
    autostart_var = tk.BooleanVar(value=bool(_safe(autostart.is_enabled)))
    tk.Checkbutton(
        cardf, text="Start VibeFlow when I sign in to Windows", variable=autostart_var,
        bg=_CARD, fg=_FG, selectcolor=_CARD, activebackground=_CARD,
        activeforeground=_ACCENT, anchor="w", font=("Segoe UI", 10),
        highlightthickness=0, bd=0,
    ).pack(fill="x", anchor="w", padx=10, pady=1)

    tk.Label(root, text="Speech accuracy and the AI tier (Off/Fast/Balanced/Best/"
             "Offline) live in the tray menu — they download or reload a model. "
             "Filler words (um, uh) are always cleaned up automatically.",
             bg=_BG, fg=_MUTED, anchor="w", wraplength=430, justify="left",
             font=("Segoe UI", 8)).pack(fill="x", padx=18, pady=(10, 0))

    status = tk.Label(root, text="", bg=_BG, fg=_ACCENT, font=("Segoe UI", 9), anchor="w")
    status.pack(fill="x", padx=18, pady=(8, 0))

    def save():
        try:
            cfg.set("output.mode", out_var.get())
            for key, var in check_vars.items():
                cfg.set(key, bool(var.get()))
            cfg.save()
            # Autostart (registry) — only touch it if it changed.
            want = bool(autostart_var.get())
            if want != bool(_safe(autostart.is_enabled)):
                _safe(autostart.enable if want else autostart.disable)
            status.config(text="Saved ✓  — applied to VibeFlow.")
        except Exception as exc:  # pragma: no cover - defensive
            status.config(text=f"Could not save: {exc}", fg="#FF8A8A")

    bar = tk.Frame(root, bg=_BG)
    bar.pack(fill="x", padx=14, pady=14, side="bottom")
    tk.Button(bar, text="Save & apply", command=save,
              font=("Segoe UI", 10, "bold")).pack(side="left")
    tk.Button(bar, text="Close", command=root.destroy).pack(side="right")

    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    root.mainloop()
    return 0


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
