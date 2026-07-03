"""Manage AI models — a small, standalone window to free disk space.

Lists the local LLM models Ollama has installed (with sizes), and lets you remove
the ones you don't need — no terminal, no reinstalling anything. It talks to the
live Ollama server (GET /api/tags, DELETE /api/delete), so it always reflects the
real store, and it labels which models Mynah added vs. ones you installed
yourself (removing one of yours asks for an extra confirmation).

Runs as its own process (``Mynah.exe --models-manager``) so it has an
independent Tk loop and never blocks the tray icon or the dictation hotkey.
"""

from __future__ import annotations

import os
import sys

_BG = "#0E1730"
_FG = "#F2F4F8"
_ACCENT = "#5B8DEF"


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


def _fmt_size(num_bytes: int) -> str:
    n = float(num_bytes or 0)
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e3:.0f} KB"


def _base_name(name: str) -> str:
    return (name or "").split(":")[0]


def run(config_path: str | None = None) -> int:
    _make_dpi_aware()
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return 1

    global _BG, _FG, _ACCENT
    from . import ai_setup, config as config_mod, winteme

    _pal = winteme.palette()  # Match Windows light/dark
    _BG, _FG, _ACCENT = _pal["bg"], _pal["fg"], _pal["accent"]

    cfg = config_mod.load_config(config_path)
    pulled = {str(m).strip() for m in (cfg.get("ai.pulled_models", []) or [])}
    pulled |= {_base_name(m) for m in pulled}

    root = tk.Tk()
    root.title("Mynah — AI models")
    root.geometry("560x520")
    root.minsize(520, 420)
    root.configure(bg=_BG)
    winteme.style_ttk(root, _pal)
    ico = _icon_path()
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    header = tk.Label(
        root, text="", bg=_BG, fg=_FG, font=("Segoe UI", 10), justify="left", anchor="w"
    )
    header.pack(fill="x", padx=14, pady=(14, 8))

    body = tk.Frame(root, bg=_BG)
    canvas = tk.Canvas(body, bg=_BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    listframe = tk.Frame(canvas, bg=_BG)
    listframe.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=listframe, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    vars_by_name: dict = {}

    def rebuild():
        for w in listframe.winfo_children():
            w.destroy()
        vars_by_name.clear()
        if not ai_setup.server_up():
            header.config(
                text="The local AI isn't running. Turn on AI formatting or "
                "adaptive learning from the tray first."
            )
            return
        models = ai_setup.model_list()
        total = sum(m["size"] for m in models)
        header.config(
            text=f"{len(models)} model(s), {_fmt_size(total)} total. Tick any you "
            "want to remove, then click “Remove selected”."
        )
        if not models:
            tk.Label(
                listframe, text="No models installed yet.", bg=_BG, fg=_pal["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", padx=6, pady=6)
            return
        for m in sorted(models, key=lambda x: -x["size"]):
            name = m["name"]
            mine = name in pulled or _base_name(name) in pulled
            label = f"{name}   ·   {_fmt_size(m['size'])}"
            if not mine:
                label += "   (not added by Mynah)"
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                listframe, text=label, variable=var, bg=_BG, fg=_FG, selectcolor=_BG,
                activebackground=_BG, activeforeground=_ACCENT, anchor="w",
                font=("Segoe UI", 10), highlightthickness=0, bd=0,
            ).pack(fill="x", anchor="w", padx=6, pady=1)
            vars_by_name[name] = (var, mine)

    def remove_selected():
        chosen = [n for n, (v, _mine) in vars_by_name.items() if v.get()]
        if not chosen:
            messagebox.showinfo("Mynah", "Tick the model(s) to remove first.", parent=root)
            return
        foreign = [n for n in chosen if not vars_by_name[n][1]]
        msg = "Remove these model(s)?\n\n" + "\n".join(chosen)
        if foreign:
            msg += (
                "\n\nNote: "
                + ", ".join(foreign)
                + " were not added by Mynah — removing them frees space but "
                "they'll be gone for any other app that uses Ollama too."
            )
        if not messagebox.askyesno("Mynah", msg, parent=root):
            return
        failed = [n for n in chosen if not ai_setup.delete_model(n)]
        if failed:
            messagebox.showwarning(
                "Mynah", "Couldn't remove: " + ", ".join(failed), parent=root
            )
        rebuild()

    # Button bar pinned to the bottom (packed before the list so it never clips).
    bar = tk.Frame(root, bg=_BG)
    bar.pack(side="bottom", fill="x", padx=12, pady=12)
    tk.Button(bar, text="Remove selected", command=remove_selected).pack(side="left")
    tk.Button(bar, text="Refresh", command=lambda: rebuild()).pack(side="left", padx=6)
    tk.Button(bar, text="Close", command=root.destroy).pack(side="right")

    body.pack(side="top", fill="both", expand=True, padx=10)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    rebuild()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    root.mainloop()
    return 0
