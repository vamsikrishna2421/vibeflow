"""
Update dialog (WINDOWS) — a standalone Tk window (own process, like
license_window.py). Checks GitHub for a newer VibeFlow, shows the result
clearly, and downloads + installs on one click. Launched via
``VibeFlow.exe --update``.

This is the Windows-only copy on purpose — the Mac build has its own
``platform_mac/update_window.py`` so a change to one can't break the other.
"""
from __future__ import annotations

import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import __app_name__, __version__, update_check

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

    label(root, "VibeFlow Updates", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22, pady=(20, 0))
    label(root, f"You're on version {__version__}", fg=_SOFT, font=("Segoe UI", 9)).pack(anchor="w", padx=22)

    # Status card
    card = tk.Frame(root, bg=_CARD)
    card.pack(fill="x", padx=18, pady=14)
    icon = label(card, "🔄", bg=_CARD, font=("Segoe UI", 22))
    icon.pack(anchor="w", padx=16, pady=(16, 0))
    status = label(card, "Checking for updates…", bg=_CARD, fg=_INK,
                   font=("Segoe UI", 13, "bold"), wraplength=410, justify="left")
    status.pack(anchor="w", padx=16, pady=(2, 2))
    sub = label(card, "", bg=_CARD, fg=_SOFT, font=("Segoe UI", 10), wraplength=410, justify="left")
    sub.pack(anchor="w", padx=16, pady=(0, 14))

    bar = ttk.Progressbar(root, mode="determinate", maximum=100)  # packed only while downloading

    btns = tk.Frame(root, bg=_BG)
    btns.pack(side="bottom", fill="x", padx=18, pady=16)
    close_btn = ttk.Button(btns, text="Close", command=root.destroy)
    close_btn.pack(side="right")
    install_btn = ttk.Button(btns, text="Install && Restart")   # shown only when an update exists
    recheck_btn = ttk.Button(btns, text="Check again")          # shown when up-to-date / error

    state: dict = {"info": None}

    # ---- result renderers -------------------------------------------------
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
                          font=("Segoe UI", 9, "underline"), cursor="hand2")
            notes.pack(anchor="w", padx=16, pady=(0, 12))
            notes.bind("<Button-1>", lambda e: webbrowser.open(info["page_url"]))

    def show_error():
        _clear_buttons()
        icon.config(text="⚠", fg=_ERR)
        status.config(text="Couldn't check for updates", fg=_ERR)
        sub.config(text="Check your internet connection and try again.")
        recheck_btn.pack(side="right", padx=(0, 8))

    # ---- check ------------------------------------------------------------
    def do_check():
        icon.config(text="🔄", fg=_INK)
        status.config(text="Checking for updates…", fg=_INK)
        sub.config(text="")
        _clear_buttons()
        try:
            info = update_check.check()
        except Exception:
            info = None

        def apply():
            if info is None:
                show_error()
            elif info.get("newer") and info.get("installer_url"):
                state["info"] = info
                show_available(info)
            elif info.get("newer"):
                # newer tag exists but the installer asset isn't uploaded yet
                state["info"] = info
                show_available(info)
            else:
                show_up_to_date()

        root.after(0, apply)

    recheck_btn.config(command=lambda: threading.Thread(target=do_check, daemon=True).start())

    # ---- install ----------------------------------------------------------
    def do_install():
        info = state.get("info")
        if not info:
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
            url = info.get("installer_url")
            path = update_check.download_installer(url, progress=prog) if url else None
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
            root.after(0, lambda: (status.config(text=f"Installing v{info['version']}…", fg=_OK),
                                   sub.config(text="VibeFlow will close and reopen to finish.")))
            update_check.run_installer(path)  # taskkills + installs + relaunches VibeFlow

        threading.Thread(target=work, daemon=True).start()

    install_btn.config(command=do_install)

    threading.Thread(target=do_check, daemon=True).start()
    root.mainloop()
    return 0
