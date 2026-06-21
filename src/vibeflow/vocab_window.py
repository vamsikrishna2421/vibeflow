"""Interactive vocabulary manager — a small, standalone window.

Lists the words VibeFlow has learned with a checkbox each; tick the ones you
want to forget and click **Delete selected**. You can also add a word directly.

It runs as its *own* process (launched from the tray, ``VibeFlow.exe
--vocab-manager``) so it has an independent Tk main loop and never interferes
with the tray icon or the dictation hotkey. The running app notices the edited
``vocabulary.json`` and reloads it automatically (see
:meth:`vibeflow.vocabulary.Vocabulary.reload_if_changed`).
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
    """Crisp text on high-DPI / scaled displays."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def run(vocab_path: str) -> int:
    """Open the manager window for the vocabulary stored at ``vocab_path``."""
    _make_dpi_aware()
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog, ttk
    except Exception:
        return 1

    from .core.vocabulary import Vocabulary

    vocab = Vocabulary(path=vocab_path)

    root = tk.Tk()
    root.title("VibeFlow — My Vocabulary")
    root.geometry("440x560")
    root.configure(bg=_BG)
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

    # --- scrollable checklist -------------------------------------------
    body = tk.Frame(root, bg=_BG)
    body.pack(fill="both", expand=True, padx=10)
    canvas = tk.Canvas(body, bg=_BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    listframe = tk.Frame(canvas, bg=_BG)
    listframe.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=listframe, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_wheel(event):
        canvas.yview_scroll(int(-event.delta / 120), "units")

    canvas.bind_all("<MouseWheel>", _on_wheel)

    vars_by_term: dict = {}

    def rebuild():
        for w in listframe.winfo_children():
            w.destroy()
        vars_by_term.clear()
        terms = vocab.list_terms()
        header.config(
            text=f"{len(terms)} learned word(s). Tick any you want VibeFlow to "
            "forget, then click “Delete selected”."
        )
        if not terms:
            tk.Label(
                listframe,
                text="Nothing learned yet — dictate and correct a few times.",
                bg=_BG,
                fg="#9AA4B2",
                font=("Segoe UI", 9),
            ).pack(anchor="w", padx=6, pady=6)
        for term in terms:
            var = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(
                listframe,
                text=term,
                variable=var,
                bg=_BG,
                fg=_FG,
                selectcolor=_BG,
                activebackground=_BG,
                activeforeground=_ACCENT,
                anchor="w",
                font=("Segoe UI", 10),
                highlightthickness=0,
                bd=0,
            )
            cb.pack(fill="x", anchor="w", padx=6, pady=1)
            vars_by_term[term] = var

    def delete_selected():
        chosen = [t for t, v in vars_by_term.items() if v.get()]
        if not chosen:
            messagebox.showinfo(
                "VibeFlow", "Tick the word(s) you want to forget first.", parent=root
            )
            return
        preview = ", ".join(chosen[:20]) + ("…" if len(chosen) > 20 else "")
        if not messagebox.askyesno(
            "VibeFlow",
            f"Forget {len(chosen)} word(s)?\n\n{preview}",
            parent=root,
        ):
            return
        for term in chosen:
            vocab.remove(term)
        vocab.save()
        rebuild()

    def add_word():
        word = simpledialog.askstring(
            "Add word", "Word to teach VibeFlow:", parent=root
        )
        if word and vocab.add(word.strip(), weight=5):
            vocab.save()
            rebuild()

    def select_all():
        val = not all(v.get() for v in vars_by_term.values()) if vars_by_term else False
        for v in vars_by_term.values():
            v.set(val)

    # --- buttons --------------------------------------------------------
    bar = tk.Frame(root, bg=_BG)
    bar.pack(fill="x", padx=12, pady=12)
    tk.Button(bar, text="Delete selected", command=delete_selected).pack(side="left")
    tk.Button(bar, text="Select all", command=select_all).pack(side="left", padx=6)
    tk.Button(bar, text="Add word…", command=add_word).pack(side="left")
    tk.Button(bar, text="Close", command=root.destroy).pack(side="right")

    rebuild()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    root.mainloop()
    return 0
