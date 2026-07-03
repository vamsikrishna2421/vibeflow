"""
License window — a standalone Tk dialog (own process, like settings_window.py).
Shows current status, lets the user paste/open a license file, and links to buy.
Launched via `python -m vibeflow --license` (or `Mynah.exe --license`).
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from . import config as config_mod
from . import licensing

BUY_PERSONAL_URL = "https://vibeflow.app/buy/personal"
BUY_BUSINESS_URL = "https://vibeflow.app/buy/business"

_BG = "#141020"
_CARD = "#1b1730"
_INK = "#f4f2fb"
_SOFT = "#b7b2d0"
_BRAND = "#8b6dff"


def run(config_path: str | None = None) -> int:
    cfg_dir = config_mod.config_dir()
    status = licensing.evaluate(cfg_dir)

    root = tk.Tk()
    root.title("Mynah · License")
    root.configure(bg=_BG)
    try:
        root.geometry("460x460")
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", _BG), fg=kw.pop("fg", _INK), **kw)

    label(root, "Mynah License", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22, pady=(20, 2))

    # Status card
    card = tk.Frame(root, bg=_CARD)
    card.pack(fill="x", padx=18, pady=10)
    state_line = label(card, status.badge, bg=_CARD, fg=_BRAND, font=("Segoe UI", 14, "bold"))
    state_line.pack(anchor="w", padx=16, pady=(14, 2))
    detail = {
        "licensed": f"Licensed to {status.name or status.email or 'you'}. Thank you!",
        "trial": "Every feature is unlocked during your trial.",
        "expired": "Trial ended — voice-to-text stays free; AI formatting is locked.",
        "free": "Free mode — voice-to-text is free forever; unlock AI with a license.",
    }.get(status.state, "")
    label(card, detail, bg=_CARD, fg=_SOFT, font=("Segoe UI", 10), wraplength=390, justify="left").pack(
        anchor="w", padx=16, pady=(0, 14)
    )

    # Paste box
    label(root, "Paste your license key", font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(6, 4))
    box = tk.Text(root, height=4, wrap="word", bg=_CARD, fg=_INK, insertbackground=_INK,
                  relief="flat", font=("Consolas", 9))
    box.pack(fill="x", padx=18)

    msg = label(root, "", fg=_SOFT, font=("Segoe UI", 10))
    msg.pack(anchor="w", padx=22, pady=(8, 0))

    def apply_text(text: str) -> None:
        new = licensing.install_license(cfg_dir, text)
        if new:
            msg.config(text=f"✓ Activated — {new.badge}", fg="#3ed598")
            state_line.config(text=new.badge)
        else:
            msg.config(text="✗ That doesn't look like a valid Mynah license.", fg="#ff6b6b")

    def on_activate():
        apply_text(box.get("1.0", "end"))

    def on_open_file():
        p = filedialog.askopenfilename(title="Choose your Mynah license file",
                                       filetypes=[("License", "*.key *.txt *.lic"), ("All", "*.*")])
        if p:
            try:
                apply_text(Path(p).read_text(encoding="utf-8"))
            except Exception:
                msg.config(text="✗ Couldn't read that file.", fg="#ff6b6b")

    btns = tk.Frame(root, bg=_BG)
    btns.pack(fill="x", padx=18, pady=14)
    ttk.Button(btns, text="Activate", command=on_activate).pack(side="left")
    ttk.Button(btns, text="Open license file…", command=on_open_file).pack(side="left", padx=8)

    buy = tk.Frame(root, bg=_BG)
    buy.pack(fill="x", padx=18, pady=(0, 6))
    ttk.Button(buy, text="Buy Personal", command=lambda: webbrowser.open(BUY_PERSONAL_URL)).pack(side="left")
    ttk.Button(buy, text="Buy Business (per-seat)", command=lambda: webbrowser.open(BUY_BUSINESS_URL)).pack(
        side="left", padx=8
    )

    label(root, "Fully offline — your license is verified on this device; nothing is sent anywhere.",
          fg=_SOFT, font=("Segoe UI", 8), wraplength=410, justify="left").pack(anchor="w", padx=22, pady=(6, 0))

    root.mainloop()
    return 0
