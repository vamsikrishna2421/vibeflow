"""
Activate window — a standalone Tk dialog (own process, like settings_window.py).
Shows trial / locked / licensed status, lets the user paste a Lemon Squeezy license
key to unlock THIS device for life, and links to buy ($10). Launched via
`VibeFlow.exe --license`. Visuals from the shared ``theme`` module.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import config as config_mod, licensing, theme as T


def run(config_path: str | None = None) -> int:
    cfg_dir = config_mod.config_dir()
    status = licensing.evaluate(cfg_dir)

    root = tk.Tk()
    root.title("VibeFlow · Activate")
    root.configure(bg=T.BG)
    try:
        root.geometry("480x470")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", T.BG), fg=kw.pop("fg", T.INK), **kw)

    label(root, "VibeFlow", font=T.font(T.DISPLAY, "bold")).pack(anchor="w", padx=24, pady=(22, 2))

    # Status card
    card = T.rounded_card(root, fill="x", padx=20, pady=(8, 4))
    state_line = label(card, status.badge, bg=T.CARD, fg=T.BRAND, font=T.font(T.TITLE, "bold"))
    state_line.pack(anchor="w", padx=18, pady=(14, 2))
    detail = {
        "licensed": "This device is licensed. Thank you for buying VibeFlow!",
        "trial": "Every feature is unlocked during your free trial.",
        "locked": "Your trial's over — but your setup, vocabulary, and shortcuts are all "
                  "still here. Unlock this device ($10, one time) to keep going.",
    }.get(status.state, "")
    detail_line = label(card, detail, bg=T.CARD, fg=T.SOFT, font=T.font(T.BODY),
                        wraplength=410, justify="left")
    detail_line.pack(anchor="w", padx=18, pady=(0, 14))

    # Privacy promise — the strongest selling line, promoted out of the fine print.
    label(root, "🔒  Runs fully on your device — your dictation never leaves this computer.",
          fg=T.OK, font=T.font(T.LABEL), wraplength=440, justify="left").pack(
        anchor="w", padx=24, pady=(6, 2))

    # Paste-key box
    label(root, "Have a license key? Paste it to unlock this device",
          fg=T.SOFT, font=T.font(T.BODY)).pack(anchor="w", padx=24, pady=(12, 4))
    box = tk.Text(root, height=2, wrap="word", bg=T.CARD, fg=T.INK, insertbackground=T.INK,
                  relief="flat", font=("Consolas", 11), highlightthickness=1,
                  highlightbackground=T.LINE, highlightcolor=T.BRAND)
    box.pack(fill="x", padx=20)
    label(root, "Looks like  XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
          fg=T.FAINT, font=T.font(T.CAPTION)).pack(anchor="w", padx=24, pady=(3, 0))

    msg = label(root, "", fg=T.SOFT, font=T.font(T.BODY), wraplength=430, justify="left")
    msg.pack(anchor="w", padx=24, pady=(8, 0))

    activate_btn = None  # set below

    def _finish(ok: bool, text: str, badge: str | None = None) -> None:
        msg.config(text=text, fg=T.OK if ok else T.ERR)
        if ok and badge:
            state_line.config(text=badge)
            detail_line.config(text="This device is licensed. Thank you for buying VibeFlow!")
        if activate_btn is not None:
            activate_btn.config(state="normal")

    def _worker(key: str) -> None:
        try:
            new = licensing.activate_license(cfg_dir, key)
            root.after(0, lambda: _finish(True, "✓ Unlocked — this device is licensed for life. Thank you!", new.badge))
        except licensing.ActivationError as exc:
            emsg = str(exc)
            root.after(0, lambda: _finish(False, f"✗ {emsg}"))

    def on_activate():
        key = box.get("1.0", "end").strip()
        if not key:
            _finish(False, "✗ Paste your license key first.")
            return
        if activate_btn is not None:
            activate_btn.config(state="disabled")
        msg.config(text="Activating this device…", fg=T.SOFT)
        threading.Thread(target=_worker, args=(key,), daemon=True).start()

    # Buy is the filled primary (the locked-user path); Activate is the quiet
    # secondary for people who already bought and have a key.
    bar = tk.Frame(root, bg=T.BG)
    bar.pack(side="bottom", fill="x", padx=20, pady=16)
    T.primary_button(bar, "Buy — $10, lifetime", lambda: webbrowser.open(licensing.LS_CHECKOUT_URL),
                     width=190).pack(side="left")
    activate_btn = ttk.Button(bar, text="Activate this device", command=on_activate)
    activate_btn.pack(side="right")

    label(root, "One-time $10 per device — no subscription, ever. One purchase unlocks "
                "this device for life.", bg=T.BG, fg=T.FAINT, font=T.font(T.CAPTION),
          wraplength=430, justify="left").pack(side="bottom", anchor="w", padx=24, pady=(0, 4))

    root.mainloop()
    return 0
