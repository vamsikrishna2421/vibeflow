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
_CHECKS = [
    ("ai.enabled", "Use AI to clean up & rephrase (needs a model — set it up in the tray)"),
    ("text.strip_fillers", "Remove filler words (um, uh)"),
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
        from tkinter import ttk
    except Exception:
        return 1

    from . import autostart, config as config_mod

    cfg = config_mod.load_config(config_path)

    root = tk.Tk()
    root.title("VibeFlow — Settings")
    # Cap the height to the screen so the bottom buttons are never off-screen on
    # short laptop displays.
    _sh = root.winfo_screenheight()
    root.geometry(f"490x{min(800, max(560, _sh - 90))}")
    root.minsize(480, min(560, max(420, _sh - 140)))
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

    # Microphone — pin a device so Windows switching to a Bluetooth headset can't
    # silently break dictation. Stored by NAME (indices shift when devices change).
    mic_card = card("MICROPHONE")
    try:
        from .audio import input_devices
        _devs = input_devices()
    except Exception:
        _devs = []
    _DEFAULT_MIC = "Default (follow Windows)"
    mic_values = [_DEFAULT_MIC] + [name for _i, name in _devs]
    mic_var = tk.StringVar()
    _cur_dev = str(cfg.get("audio.input_device", "default") or "default").strip()
    if _cur_dev in ("", "default"):
        mic_var.set(_DEFAULT_MIC)
    else:
        _match = next(
            (n for n in mic_values[1:]
             if _cur_dev.lower() in n.lower() or n.lower() in _cur_dev.lower()),
            None,
        )
        mic_var.set(_match or _cur_dev)
    ttk.Combobox(
        mic_card, textvariable=mic_var, values=mic_values, state="readonly",
        font=("Segoe UI", 10),
    ).pack(fill="x", padx=10, pady=(8, 2))
    tk.Label(
        mic_card,
        text="Pick your built-in mic here so connecting Bluetooth headphones "
        "doesn't switch VibeFlow to a mic that picks up no sound.",
        bg=_CARD, fg=_MUTED, font=("Segoe UI", 8), anchor="w",
        wraplength=430, justify="left",
    ).pack(fill="x", padx=10, pady=(0, 8))

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

    tk.Label(root, text="Speech accuracy (Fast/Balanced) and the AI tier are in the "
             "tray menu — they download or reload a model.", bg=_BG, fg=_MUTED,
             anchor="w", wraplength=430, justify="left",
             font=("Segoe UI", 8)).pack(fill="x", padx=18, pady=(10, 0))

    status = tk.Label(root, text="", bg=_BG, fg=_ACCENT, font=("Segoe UI", 9), anchor="w")
    status.pack(fill="x", padx=18, pady=(8, 0))

    def save():
        try:
            cfg.set("output.mode", out_var.get())
            _sel = mic_var.get().strip()
            cfg.set("audio.input_device", "default" if _sel.startswith("Default") else _sel)
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

    def clear_app_rules():
        try:
            cfg.set("text.modes.rules", [])
            cfg.save()
            status.config(text="Cleared your per-app formatting rules ✓", fg=_ACCENT)
        except Exception as exc:  # pragma: no cover - defensive
            status.config(text=f"Couldn't clear rules: {exc}", fg="#FF8A8A")

    def open_log():
        try:
            from .logsetup import log_path

            target = log_path()
            os.startfile(str(target if target.exists() else target.parent))
        except Exception as exc:  # pragma: no cover - defensive
            status.config(text=f"Couldn't open the log: {exc}", fg="#FF8A8A")

    # Utility row (per-app rules + log) sits just above the Save / Close bar.
    util = tk.Frame(root, bg=_BG)
    util.pack(fill="x", padx=14, pady=(4, 0), side="bottom")
    tk.Button(util, text="Clear app rules", command=clear_app_rules).pack(side="left")
    tk.Button(util, text="Open log file", command=open_log).pack(side="left", padx=6)

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
