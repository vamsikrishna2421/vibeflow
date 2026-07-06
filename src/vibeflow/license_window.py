"""
Activate window — a standalone Tk dialog (own process, like settings_window.py).
Shows trial / locked / licensed status, lets the user paste a Lemon Squeezy license
key to unlock THIS device for life, and links to buy ($10). Launched via
`VibeFlow.exe --license`.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import config as config_mod
from . import licensing

_BG = "#141020"
_CARD = "#1b1730"
_INK = "#f4f2fb"
_SOFT = "#b7b2d0"
_BRAND = "#8b6dff"
_OK = "#3ed598"
_ERR = "#ff6b6b"


def run(config_path: str | None = None) -> int:
    cfg_dir = config_mod.config_dir()
    status = licensing.evaluate(cfg_dir)

    root = tk.Tk()
    root.title("VibeFlow · Activate")
    root.configure(bg=_BG)
    try:
        root.geometry("470x440")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", _BG), fg=kw.pop("fg", _INK), **kw)

    label(root, "VibeFlow", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22, pady=(20, 2))

    # Status card
    card = tk.Frame(root, bg=_CARD)
    card.pack(fill="x", padx=18, pady=10)
    state_line = label(card, status.badge, bg=_CARD, fg=_BRAND, font=("Segoe UI", 14, "bold"))
    state_line.pack(anchor="w", padx=16, pady=(14, 2))
    detail = {
        "licensed": "This device is licensed. Thank you for buying VibeFlow!",
        "trial": "Every feature is unlocked during your free trial.",
        "locked": "Your free trial has ended. Unlock this device once ($10) to keep using VibeFlow.",
    }.get(status.state, "")
    detail_line = label(card, detail, bg=_CARD, fg=_SOFT, font=("Segoe UI", 10),
                        wraplength=400, justify="left")
    detail_line.pack(anchor="w", padx=16, pady=(0, 14))

    # Paste-key box
    label(root, "Have a license key? Paste it to unlock this device",
          font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(6, 4))
    box = tk.Text(root, height=2, wrap="word", bg=_CARD, fg=_INK, insertbackground=_INK,
                  relief="flat", font=("Consolas", 11))
    box.pack(fill="x", padx=18)

    msg = label(root, "", fg=_SOFT, font=("Segoe UI", 10), wraplength=420, justify="left")
    msg.pack(anchor="w", padx=22, pady=(8, 0))

    activate_btn = None  # set below

    def _finish(ok: bool, text: str, badge: str | None = None) -> None:
        msg.config(text=text, fg=_OK if ok else _ERR)
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
        msg.config(text="Activating this device…", fg=_SOFT)
        threading.Thread(target=_worker, args=(key,), daemon=True).start()

    btns = tk.Frame(root, bg=_BG)
    btns.pack(fill="x", padx=18, pady=14)
    activate_btn = ttk.Button(btns, text="Activate this device", command=on_activate)
    activate_btn.pack(side="left")

    buy = tk.Frame(root, bg=_BG)
    buy.pack(fill="x", padx=18, pady=(0, 6))
    ttk.Button(buy, text="Buy — $10 (one device, lifetime)",
               command=lambda: webbrowser.open(licensing.LS_CHECKOUT_URL)).pack(side="left")

    label(root, "One-time $10 per device — no subscription. After you activate once, "
                "VibeFlow runs fully offline; nothing about your dictation is ever sent anywhere.",
          fg=_SOFT, font=("Segoe UI", 8), wraplength=420, justify="left").pack(
        anchor="w", padx=22, pady=(6, 0))

    root.mainloop()
    return 0
