"""
Update dialog (macOS) — a standalone Tk window (own process, launched via
``VibeFlow --update``). Checks GitHub for a newer VibeFlow, shows the result,
and downloads it with a progress bar.

The bundle **swap-and-restart** must be done by the menu-bar process (it has to
quit so its .app can be replaced), so once the download finishes the dialog
drops a marker file the menu-bar app polls. macOS-only copy; the Windows build
has its own top-level ``update_window.py``. Visuals from the shared ``theme``.
"""
from __future__ import annotations

import json
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import __app_name__, __version__, config as config_mod, theme as T
from . import updater

# Menu-bar app polls for this file (see menubar._check_update_marker).
UPDATE_MARKER = "update_pending.json"


def run(config_path: str | None = None) -> int:
    root = tk.Tk()
    root.title(f"{__app_name__} · Updates")
    root.configure(bg=T.BG)
    try:
        root.geometry("470x330")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", T.BG), fg=kw.pop("fg", T.INK), **kw)

    label(root, "Updates", font=T.font(T.DISPLAY, "bold")).pack(anchor="w", padx=24, pady=(22, 0))
    label(root, f"You're on VibeFlow {__version__}", fg=T.SOFT, font=T.font(T.CAPTION)).pack(anchor="w", padx=24)

    card = T.rounded_card(root, fill="x", padx=20, pady=16)
    icon = label(card, "🔄", bg=T.CARD, font=T.font(T.DISPLAY))
    icon.pack(anchor="w", padx=18, pady=(16, 0))
    status = label(card, "Checking for updates…", bg=T.CARD, fg=T.INK,
                   font=T.font(T.TITLE, "bold"), wraplength=400, justify="left")
    status.pack(anchor="w", padx=18, pady=(2, 2))
    sub = label(card, "", bg=T.CARD, fg=T.SOFT, font=T.font(T.BODY), wraplength=400, justify="left")
    sub.pack(anchor="w", padx=18, pady=(0, 16))

    bar = ttk.Progressbar(root, mode="determinate", maximum=100)

    btns = tk.Frame(root, bg=T.BG)
    btns.pack(side="bottom", fill="x", padx=20, pady=16)
    close_btn = ttk.Button(btns, text="Close", command=root.destroy)
    close_btn.pack(side="right")
    install_btn = T.primary_button(btns, "Install & Restart", lambda: do_install())
    recheck_btn = ttk.Button(btns, text="Check again")

    state: dict = {"info": None}

    def _clear_buttons():
        for b in (install_btn, recheck_btn):
            b.pack_forget()

    def show_up_to_date():
        _clear_buttons()
        icon.config(text="✓", fg=T.OK)
        status.config(text="You're on the latest", fg=T.OK)
        sub.config(text=f"VibeFlow {__version__} — nothing to do. You're all set.")
        recheck_btn.pack(side="right", padx=(0, 8))

    def show_available(info):
        _clear_buttons()
        icon.config(text="⬆", fg=T.BRAND)
        status.config(text=f"Update ready — v{info['version']}", fg=T.INK)
        sub.config(text="Installs in seconds, and keeps all your settings.")
        install_btn.pack(side="right", padx=(0, 8))
        if info.get("page_url"):
            notes = label(card, "See what's new →", bg=T.CARD, fg=T.BRAND,
                          font=T.font(T.CAPTION), cursor="pointinghand")
            notes.pack(anchor="w", padx=18, pady=(0, 12))
            notes.bind("<Button-1>", lambda e: webbrowser.open(info["page_url"]))

    def show_error():
        _clear_buttons()
        icon.config(text="⚠", fg=T.ERR)
        status.config(text="Couldn't check for updates", fg=T.ERR)
        sub.config(text="Check your internet connection and try again.")
        recheck_btn.pack(side="right", padx=(0, 8))

    def do_check():
        icon.config(text="🔄", fg=T.INK)
        status.config(text="Checking for updates…", fg=T.INK)
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
        try:
            install_btn.pack_forget()
        except Exception:
            pass
        close_btn.config(state="disabled")
        icon.config(text="⬇", fg=T.BRAND)
        status.config(text="Downloading update…", fg=T.INK)
        sub.config(text="")
        bar.pack(fill="x", padx=22, pady=(0, 8))
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
                    icon.config(text="⚠", fg=T.ERR)
                    status.config(text="Download didn't finish", fg=T.ERR)
                    sub.config(text="Opening the release page so you can grab it manually…")
                    bar.pack_forget()
                    if info.get("page_url"):
                        webbrowser.open(info["page_url"])
                    install_btn.pack(side="right", padx=(0, 8))
                    close_btn.config(state="normal")
                root.after(0, failed)
                return
            try:
                marker = config_mod.config_dir() / UPDATE_MARKER
                marker.write_text(json.dumps({"zip": path, "version": info["version"]}),
                                  encoding="utf-8")
            except Exception:
                pass

            def done():
                icon.config(text="✓", fg=T.OK)
                status.config(text=f"Installing v{info['version']}…", fg=T.OK)
                sub.config(text="VibeFlow will close and reopen to finish. You can close this window.")
                bar["value"] = 100
                close_btn.config(state="normal", text="Done")
                root.after(2500, root.destroy)
            root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    threading.Thread(target=do_check, daemon=True).start()
    root.mainloop()
    return 0
