"""Interactive "Personalized AI" manager — a small, standalone window.

Lets you see and manage the writing profile Mynah learns from your dictation:

* view and **edit** the distilled profile (it's injected into AI formatting),
* **Regenerate** it on demand from your recent dictation,
* see and **delete** the stored dictation samples (full transparency/privacy),
* **Forget everything**.

Runs as its own process (``Mynah.exe --persona-manager``) so it has an
independent Tk loop. The running app reloads ``persona.json`` when it changes
(:meth:`vibeflow.persona.Persona.reload_if_changed`).
"""

from __future__ import annotations

import os
import sys
import threading

_BG = "#0E1730"
_FG = "#F2F4F8"
_MUTED = "#9AA4B2"
_ACCENT = "#5B8DEF"


def _icon_path():
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


def run(persona_path: str) -> int:
    _make_dpi_aware()
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return 1

    global _BG, _FG, _MUTED, _ACCENT
    from . import winteme

    _pal = winteme.palette()  # Match Windows light/dark
    _BG, _FG, _MUTED, _ACCENT = _pal["bg"], _pal["fg"], _pal["muted"], _pal["accent"]

    from . import config as config_mod
    from .core import ai_format
    from .core.persona import Persona

    persona = Persona(path=persona_path)
    cfg = config_mod.load_config()

    root = tk.Tk()
    root.title("Mynah — Personalized AI")
    root.geometry("560x640")
    root.minsize(520, 480)  # keep the bottom buttons on-screen
    root.configure(bg=_BG)
    winteme.style_ttk(root, _pal)
    ico = _icon_path()
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    tk.Label(
        root,
        text="Your writing profile",
        bg=_BG,
        fg=_FG,
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x", padx=14, pady=(14, 0))
    tk.Label(
        root,
        text="Mynah learned this from your dictation; it nudges AI formatting "
        "to sound like you. You can edit it.",
        bg=_BG,
        fg=_MUTED,
        font=("Segoe UI", 9),
        anchor="w",
        justify="left",
        wraplength=500,
    ).pack(fill="x", padx=14)

    profile_box = tk.Text(
        root,
        height=7,
        wrap="word",
        bg=_pal["field"],
        fg=_FG,
        insertbackground=_FG,
        relief="flat",
        font=("Segoe UI", 10),
        padx=8,
        pady=6,
    )
    profile_box.pack(fill="x", padx=14, pady=8)
    _placeholder = "(No profile yet — keep dictating, or click “Regenerate now”.)"
    profile_box.insert("1.0", persona.profile_text() or _placeholder)

    status = tk.Label(root, text="", bg=_BG, fg=_ACCENT, font=("Segoe UI", 9), anchor="w")
    status.pack(fill="x", padx=14)

    def save_profile():
        txt = profile_box.get("1.0", "end").strip()
        if txt == _placeholder:
            txt = ""
        persona.reload_if_changed()
        persona.set_profile(txt)
        persona.save()
        status.config(text="Profile saved.")

    def regenerate():
        if len(persona.sample_texts()) < 3:
            messagebox.showinfo(
                "Mynah",
                "Not enough dictation yet to build a profile. Keep using Mynah "
                "and try again.",
                parent=root,
            )
            return
        regen_btn.config(state="disabled", text="Regenerating…")
        status.config(text="Asking the local model to summarise your style…")

        def work():
            profile = ai_format.build_persona_profile(persona.sample_texts(), cfg)

            def done():
                regen_btn.config(state="normal", text="Regenerate now")
                if profile:
                    persona.reload_if_changed()
                    persona.set_profile(profile)
                    persona.save()
                    profile_box.delete("1.0", "end")
                    profile_box.insert("1.0", profile)
                    status.config(text="Profile regenerated from your dictation.")
                else:
                    status.config(text="")
                    messagebox.showwarning(
                        "Mynah",
                        "Couldn't regenerate — a local AI model needs to be set up "
                        "(tray → AI formatting).",
                        parent=root,
                    )

            root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    row = tk.Frame(root, bg=_BG)
    row.pack(fill="x", padx=12, pady=(2, 8))
    tk.Button(row, text="Save profile", command=save_profile).pack(side="left")
    regen_btn = tk.Button(row, text="Regenerate now", command=regenerate)
    regen_btn.pack(side="left", padx=6)

    # --- samples -------------------------------------------------------
    tk.Label(
        root,
        text="Stored dictation samples (local only)",
        bg=_BG,
        fg=_FG,
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x", padx=14, pady=(8, 0))

    # Packed AFTER the button bar (below) so the bar stays pinned to the bottom
    # and the sample list fills the space above it.
    body = tk.Frame(root, bg=_BG)
    canvas = tk.Canvas(body, bg=_BG, highlightthickness=0)
    sb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    listframe = tk.Frame(canvas, bg=_BG)
    listframe.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=listframe, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    sample_vars: list = []

    def rebuild_samples():
        for w in listframe.winfo_children():
            w.destroy()
        sample_vars.clear()
        texts = persona.sample_texts()
        sample_header.config(text=f"{len(texts)} sample(s). Tick any to delete.")
        for i, s in enumerate(texts):
            var = tk.BooleanVar(value=False)
            preview = (s[:70] + "…") if len(s) > 70 else s
            tk.Checkbutton(
                listframe,
                text=preview,
                variable=var,
                bg=_BG,
                fg=_FG,
                selectcolor=_BG,
                activebackground=_BG,
                activeforeground=_ACCENT,
                anchor="w",
                font=("Segoe UI", 9),
                highlightthickness=0,
                bd=0,
            ).pack(fill="x", anchor="w", padx=6, pady=1)
            sample_vars.append((i, var))

    sample_header = tk.Label(root, text="", bg=_BG, fg=_MUTED, font=("Segoe UI", 9), anchor="w")
    # (packed below the list buttons so it reads naturally)

    def delete_selected():
        chosen = {i for i, v in sample_vars if v.get()}
        if not chosen:
            messagebox.showinfo("Mynah", "Tick the sample(s) to delete first.", parent=root)
            return
        persona.reload_if_changed()
        persona.samples = [s for i, s in enumerate(persona.samples) if i not in chosen]
        persona.save()
        rebuild_samples()

    def forget_all():
        if messagebox.askyesno(
            "Mynah",
            "Forget your writing profile AND all stored samples? This can't be undone.",
            parent=root,
        ):
            persona.clear()
            persona.save()
            profile_box.delete("1.0", "end")
            profile_box.insert("1.0", _placeholder)
            status.config(text="Cleared.")
            rebuild_samples()

    # Reserve the button bar (and its header) at the BOTTOM before the list
    # expands, so the buttons are never pushed off-screen.
    bar = tk.Frame(root, bg=_BG)
    bar.pack(side="bottom", fill="x", padx=12, pady=10)
    tk.Button(bar, text="Delete selected", command=delete_selected).pack(side="left")
    tk.Button(bar, text="Forget everything", command=forget_all).pack(side="left", padx=6)
    tk.Button(bar, text="Close", command=root.destroy).pack(side="right")
    sample_header.pack(side="bottom", fill="x", padx=14, pady=(0, 2))
    body.pack(side="top", fill="both", expand=True, padx=10, pady=(4, 0))

    rebuild_samples()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    root.mainloop()
    return 0
