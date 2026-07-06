"""
Unified "VibeFlow" window (WINDOWS) — Tier-2 IA: one window with a left sidebar
instead of a scatter of separate dialogs. Launched via ``VibeFlow.exe --main``.

**Iteration 1 (build-in-the-loop).** This is ADDITIVE and low-risk: the General
pane hosts the everyday preferences inline; the richer editors (Vocabulary,
Personalization, Models, License, Updates) are opened from here as their existing
standalone windows for now, so nothing regresses while we migrate panes into the
shell over later iterations. Expect to iterate on this against a real build.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

from . import __app_name__, __version__, config as config_mod, theme as T

# (key, sidebar label). "general" is inline; the rest launch their own window
# via the CLI flag in _LAUNCH until they're migrated into panes.
_NAV = [
    ("general", "General"),
    ("vocab", "Vocabulary"),
    ("persona", "Personalization"),
    ("models", "AI Models"),
    ("license", "License"),
    ("updates", "Updates"),
]
_LAUNCH = {
    "vocab": "--vocab-manager",
    "persona": "--persona-manager",
    "models": "--models-manager",
    "license": "--license",
    "updates": "--update",
}
_BLURB = {
    "vocab": "Teach VibeFlow the names, jargon and spellings you use, so they come out right.",
    "persona": "Personalized AI quietly learns your writing style — all on this device.",
    "models": "Manage downloaded speech / AI models and free up disk space.",
    "license": "See your license status, activate this device, or buy VibeFlow.",
    "updates": "Check for a newer VibeFlow and install it.",
}


def _launch(flag: str) -> None:
    try:
        args = ([sys.executable, flag] if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "vibeflow", flag])
        import subprocess
        subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def run(config_path: str | None = None) -> int:
    cfg = config_mod.load_config(config_path)
    root = tk.Tk()
    root.title(__app_name__)
    root.configure(bg=T.BG)
    try:
        root.geometry("760x520")
        root.minsize(680, 460)
    except Exception:
        pass

    # ---- layout: sidebar | content -------------------------------------
    side = tk.Frame(root, bg=T.CARD, width=200)
    side.pack(side="left", fill="y")
    side.pack_propagate(False)
    content = tk.Frame(root, bg=T.BG)
    content.pack(side="left", fill="both", expand=True)

    tk.Label(side, text="VibeFlow", bg=T.CARD, fg=T.INK,
             font=T.font(T.TITLE, "bold")).pack(anchor="w", padx=20, pady=(22, 2))
    tk.Label(side, text=f"v{__version__}", bg=T.CARD, fg=T.FAINT,
             font=T.font(T.CAPTION)).pack(anchor="w", padx=20, pady=(0, 16))

    panes: dict = {}
    nav_items: dict = {}
    state = {"active": None}

    def select(key: str) -> None:
        for k, lbl in nav_items.items():
            on = k == key
            lbl.config(bg=T.CARD_HI if on else T.CARD, fg=T.BRAND if on else T.SOFT)
        for k, p in panes.items():
            (p.pack(fill="both", expand=True) if k == key else p.pack_forget())
        state["active"] = key

    for key, text in _NAV:
        item = tk.Label(side, text=text, bg=T.CARD, fg=T.SOFT, font=T.font(T.BODY),
                        anchor="w", padx=20, pady=9, cursor="hand2")
        item.pack(fill="x")
        item.bind("<Button-1>", lambda e, k=key: select(k))
        nav_items[key] = item

    # ---- General pane (inline) -----------------------------------------
    def _pane() -> tk.Frame:
        return tk.Frame(content, bg=T.BG)

    gen = _pane()
    panes["general"] = gen
    tk.Label(gen, text="General", bg=T.BG, fg=T.INK, font=T.font(T.DISPLAY, "bold")).pack(anchor="w", padx=28, pady=(24, 4))

    out_var = tk.StringVar(value=str(cfg.get("output.mode", "auto") or "auto"))
    tk.Label(gen, text="WHERE DICTATED TEXT GOES", bg=T.BG, fg=T.FAINT,
             font=T.font(T.CAPTION, "bold")).pack(anchor="w", padx=28, pady=(10, 4))
    for lbl, val in [("Auto — type, else clipboard", "auto"), ("Always type", "type"),
                     ("Always copy to clipboard", "clipboard")]:
        tk.Radiobutton(gen, text=lbl, variable=out_var, value=val, bg=T.BG, fg=T.INK,
                       selectcolor=T.CARD, activebackground=T.BG, activeforeground=T.BRAND,
                       anchor="w", font=T.font(T.BODY), highlightthickness=0, bd=0).pack(anchor="w", padx=28)

    tk.Label(gen, text="BEHAVIOUR", bg=T.BG, fg=T.FAINT,
             font=T.font(T.CAPTION, "bold")).pack(anchor="w", padx=28, pady=(16, 4))
    checks = [
        ("text.modes.enabled", "Adapt formatting to each app (terminals stay as spoken)"),
        ("text.history.enabled", "Save dictation history (local, opt-in)"),
        ("feedback.overlay", "Show the on-screen status HUD"),
        ("feedback.sounds", "Play start / stop sounds"),
    ]
    check_vars = {}
    for key, lbl in checks:
        v = tk.BooleanVar(value=bool(cfg.get(key, False)))
        check_vars[key] = v
        tk.Checkbutton(gen, text=lbl, variable=v, bg=T.BG, fg=T.INK, selectcolor=T.CARD,
                       activebackground=T.BG, activeforeground=T.BRAND, anchor="w",
                       font=T.font(T.BODY), highlightthickness=0, bd=0).pack(anchor="w", padx=28)

    status = tk.Label(gen, text="", bg=T.BG, fg=T.OK, font=T.font(T.CAPTION))
    status.pack(anchor="w", padx=28, pady=(14, 0))

    def save():
        try:
            cfg.set("output.mode", out_var.get())
            for k, v in check_vars.items():
                cfg.set(k, bool(v.get()))
            cfg.save()
            status.config(text="Saved ✓ — applied to VibeFlow.", fg=T.OK)
        except Exception as exc:
            status.config(text=f"Couldn't save: {exc}", fg=T.ERR)

    T.primary_button(gen, "Save & apply", save, width=150).pack(anchor="w", padx=28, pady=(16, 0))
    tk.Label(gen, text="Speech accuracy and the AI tier live in the tray menu (they "
             "download / reload a model). Filler words are always cleaned up.",
             bg=T.BG, fg=T.FAINT, font=T.font(T.CAPTION), wraplength=440,
             justify="left").pack(anchor="w", padx=28, pady=(18, 0))

    # ---- launcher panes (open the existing window for now) --------------
    for key in ("vocab", "persona", "models", "license", "updates"):
        p = _pane()
        panes[key] = p
        title = dict(_NAV)[key]
        tk.Label(p, text=title, bg=T.BG, fg=T.INK, font=T.font(T.DISPLAY, "bold")).pack(anchor="w", padx=28, pady=(24, 6))
        tk.Label(p, text=_BLURB[key], bg=T.BG, fg=T.SOFT, font=T.font(T.BODY),
                 wraplength=440, justify="left").pack(anchor="w", padx=28, pady=(0, 18))
        T.primary_button(p, f"Open {title} →", lambda k=key: _launch(_LAUNCH[k]), width=210).pack(anchor="w", padx=28)

    select("general")
    root.mainloop()
    return 0
