"""
Update dialog (macOS) — a standalone Tk window (own process, launched via
``VibeFlow --update``). Checks GitHub for a newer VibeFlow, shows the result,
and downloads it with a progress bar.

The actual bundle **swap-and-restart** must be done by the menu-bar process
(it has to quit so its .app can be replaced), so once the download finishes the
dialog drops a marker file that the menu-bar app polls and acts on. This is the
macOS-only copy — the Windows build has its own top-level ``update_window.py``.
"""
from __future__ import annotations

import json
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import __app_name__, __version__, config as config_mod
from . import updater

# Menu-bar app polls for this file (see menubar._check_update_marker).
UPDATE_MARKER = "update_pending.json"

_BG = "#141020"
_CARD = "#1b1730"
_INK = "#f4f2fb"
_SOFT = "#b7b2d0"
_BRAND = "#8b6dff"
_OK = "#3ed598"
_ERR = "#ff6b6b"


def run(config_path: str | None = None) -> int:
    root = tk.Tk()
    root.title(f"{__app_name__} · Updates")
    root.configure(bg=_BG)
    try:
        root.geometry("470x330")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", _BG), fg=kw.pop("fg", _INK), **kw)

    label(root, "VibeFlow Updates", font=("Helvetica Neue", 18, "bold")).pack(anchor="w", padx=22, pady=(20, 0))
    label(root, f"You're on version {__version__}", fg=_SOFT, font=("Helvetica Neue", 11)).pack(anchor="w", padx=22)

    card = tk.Frame(root, bg=_CARD)
    card.pack(fill="x", padx=18, pady=14)
    icon = label(card, "🔄", bg=_CARD, font=("Helvetica Neue", 22))
    icon.pack(anchor="w", padx=16, pady=(16, 0))
    status = label(card, "Checking for updates…", bg=_CARD, fg=_INK,
                   font=("Helvetica Neue", 14, "bold"), wraplength=410, justify="left")
    status.pack(anchor="w", padx=16, pady=(2, 2))
    sub = label(card, "", bg=_CARD, fg=_SOFT, font=("Helvetica Neue", 12), wraplength=410, justify="left")
    sub.pack(anchor="w", padx=16, pady=(0, 14))

    bar = ttk.Progressbar(root, mode="determinate", maximum=100)

    btns = tk.Frame(root, bg=_BG)
    btns.pack(side="bottom", fill="x", padx=18, pady=16)
    close_btn = ttk.Button(btns, text="Close", command=root.destroy)
    close_btn.pack(side="right")
    install_btn = ttk.Button(btns, text="Install & Restart")
    recheck_btn = ttk.Button(btns, text="Check again")

    state: dict = {"info": None}

    def _clear_buttons():
        for b in (install_btn, recheck_btn):
            b.pack_forget()

    def show_up_to_date():
        _clear_buttons()
        icon.config(text="✓", fg=_OK)
        status.config(text="You're up to date", fg=_OK)
        sub.config(text=f"VibeFlow {__version__} is the latest version.")
        recheck_btn.pack(side="right", padx=(0, 8))

    def show_available(info):
        _clear_buttons()
        icon.config(text="⬆", fg=_BRAND)
        status.config(text=f"Update available — v{info['version']}", fg=_INK)
        sub.config(text="A newer version of VibeFlow is ready to install.")
        install_btn.pack(side="right", padx=(0, 8))
        if info.get("page_url"):
            notes = label(card, "View what's new →", bg=_CARD, fg=_BRAND,
                          font=("Helvetica Neue", 11, "underline"), cursor="pointinghand")
            notes.pack(anchor="w", padx=16, pady=(0, 12))
            notes.bind("<Button-1>", lambda e: webbrowser.open(info["page_url"]))

    def show_error():
        _clear_buttons()
        icon.config(text="⚠", fg=_ERR)
        status.config(text="Couldn't check for updates", fg=_ERR)
        sub.config(text="Check your internet connection and try again.")
        recheck_btn.pack(side="right", padx=(0, 8))

    def do_check():
        icon.config(text="🔄", fg=_INK)
        status.config(text="Checking for updates…", fg=_INK)
        sub.config(text="")
        _clear_buttons()
        try:
            info = updater.check()
        except Exception:
            info = None

        def apply():
            if info is None:
                show_error()
            elif info.get("newer") and info.get("zip_url"):
                state["info"] = info
                show_available(info)
            else:
                show_up_to_date()

        root.after(0, apply)

    recheck_btn.config(command=lambda: threading.Thread(target=do_check, daemon=True).start())

    def do_install():
        info = state.get("info")
        if not info or not info.get("zip_url"):
            return
        install_btn.config(state="disabled")
        close_btn.config(state="disabled")
        icon.config(text="⬇", fg=_BRAND)
        status.config(text="Downloading update…", fg=_INK)
        sub.config(text="")
        bar.pack(fill="x", padx=20, pady=(0, 8))
        bar["value"] = 0

        def prog(msg: str):
            m = re.search(r"(\d+)%", msg or "")
            if m:
                root.after(0, lambda: bar.configure(value=int(m.group(1))))
            root.after(0, lambda: sub.config(text=msg or ""))

        def work():
            path = updater.download_zip(info["zip_url"], progress=prog)
            if not path:
                def failed():
                    icon.config(text="⚠", fg=_ERR)
                    status.config(text="Download failed", fg=_ERR)
                    sub.config(text="Opening the release page so you can grab it manually…")
                    bar.pack_forget()
                    if info.get("page_url"):
                        webbrowser.open(info["page_url"])
                    install_btn.config(state="normal")
                    close_btn.config(state="normal")
                root.after(0, failed)
                return
            # Hand the swap-and-restart to the menu-bar process (it must quit).
            try:
                marker = config_mod.config_dir() / UPDATE_MARKER
                marker.write_text(json.dumps({"zip": path, "version": info["version"]}),
                                  encoding="utf-8")
            except Exception:
                pass

            def done():
                icon.config(text="✓", fg=_OK)
                status.config(text=f"Installing v{info['version']}…", fg=_OK)
                sub.config(text="VibeFlow will close and reopen to finish. You can close this window.")
                bar["value"] = 100
                close_btn.config(state="normal", text="Done")
                root.after(2500, root.destroy)
            root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    install_btn.config(command=do_install)

    threading.Thread(target=do_check, daemon=True).start()
    root.mainloop()
    return 0
