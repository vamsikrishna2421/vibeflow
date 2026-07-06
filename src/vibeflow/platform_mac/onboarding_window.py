"""
First-run onboarding (macOS) — a one-time welcome window (own process, via
``VibeFlow --onboarding``). Greets, shows how to dictate, and runs a **live
microphone check** so a blocked/muted mic (the classic macOS permission trap) is
caught here instead of surfacing later as a mystifying "no speech".
macOS-only copy; the Windows build has its own ``onboarding_window.py``.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from .. import __app_name__, __version__, config as config_mod
from . import permissions

_BG = "#141020"
_CARD = "#1b1730"
_INK = "#f4f2fb"
_SOFT = "#b7b2d0"
_BRAND = "#8b6dff"
_OK = "#3ed598"
_ERR = "#ff6b6b"


def _hotkey_label(cfg) -> str:
    if str(cfg.get("hotkey.mode", "push_to_talk")) == "push_to_talk":
        return f"hold {cfg.get('hotkey.push_to_talk_key', 'right option')}"
    return f"press {cfg.get('hotkey.toggle_combo', 'ctrl+space')}"


def run(config_path: str | None = None) -> int:
    cfg = config_mod.load_config(config_path)
    root = tk.Tk()
    root.title(f"Welcome to {__app_name__}")
    root.configure(bg=_BG)
    try:
        root.geometry("500x460")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", _BG), fg=kw.pop("fg", _INK), **kw)

    label(root, "Welcome to VibeFlow", font=("Helvetica Neue", 22, "bold")).pack(anchor="w", padx=26, pady=(24, 2))
    label(root, "Premium voice-to-text that types wherever you are — fully on-device.",
          fg=_SOFT, font=("Helvetica Neue", 12), wraplength=450, justify="left").pack(anchor="w", padx=26)

    s1 = tk.Frame(root, bg=_CARD)
    s1.pack(fill="x", padx=22, pady=(18, 8))
    label(s1, "1 · How to dictate", bg=_CARD, fg=_BRAND, font=("Helvetica Neue", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    label(s1, f"{_hotkey_label(cfg).capitalize()} and just speak. Your words appear "
              "instantly wherever your cursor is — Mail, Slack, notes, anywhere.",
          bg=_CARD, fg=_INK, font=("Helvetica Neue", 12), wraplength=430, justify="left").pack(anchor="w", padx=16, pady=(0, 14))

    s2 = tk.Frame(root, bg=_CARD)
    s2.pack(fill="x", padx=22, pady=8)
    label(s2, "2 · Check your microphone", bg=_CARD, fg=_BRAND, font=("Helvetica Neue", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    mic_status = label(s2, "Let's make sure VibeFlow can hear you.", bg=_CARD, fg=_INK,
                       font=("Helvetica Neue", 12), wraplength=430, justify="left")
    mic_status.pack(anchor="w", padx=16, pady=(0, 8))
    mic_row = tk.Frame(s2, bg=_CARD)
    mic_row.pack(anchor="w", padx=16, pady=(0, 14))
    test_btn = ttk.Button(mic_row, text="🎤 Test my microphone")
    test_btn.pack(side="left")
    settings_link = label(s2, "Open Microphone settings →", bg=_CARD, fg=_SOFT,
                          font=("Helvetica Neue", 10, "underline"), cursor="pointinghand")
    settings_link.bind("<Button-1>", lambda e: _open_mic_settings())

    def mic_test():
        test_btn.config(state="disabled")
        mic_status.config(text="Listening for 1.5s — say a few words…", fg=_INK)
        settings_link.pack_forget()

        def work():
            try:
                import time
                from ..audio import Recorder, peak_level
                rec = Recorder(sample_rate=int(cfg.get("audio.sample_rate", 16000)),
                               input_device=cfg.get("audio.input_device", "default"))
                rec.start()
                time.sleep(1.5)
                audio = rec.stop()
                peak = peak_level(audio)
                exc_msg = None
            except Exception as exc:
                peak, exc_msg = 0.0, str(exc)

            def show():
                test_btn.config(state="normal")
                if exc_msg:
                    mic_status.config(text=f"Couldn't run the test: {exc_msg}", fg=_ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                elif peak < 0.02:
                    mic_status.config(
                        text=f"⚠ Barely heard anything (level {peak:.3f}). Grant VibeFlow "
                             "Microphone access in System Settings, and check the right mic "
                             "is selected and not muted.", fg=_ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                else:
                    mic_status.config(text=f"✓ Your microphone is working (level {peak:.2f}). You're all set!",
                                      fg=_OK)
            root.after(0, show)

        threading.Thread(target=work, daemon=True).start()

    test_btn.config(command=mic_test)

    def finish():
        try:
            cfg.set("onboarding.completed", True)
            cfg.save()
        except Exception:
            pass
        root.destroy()

    bar = tk.Frame(root, bg=_BG)
    bar.pack(side="bottom", fill="x", padx=22, pady=18)
    ttk.Button(bar, text="Start dictating  →", command=finish).pack(side="right")
    label(bar, f"VibeFlow {__version__}", bg=_BG, fg=_SOFT, font=("Helvetica Neue", 9)).pack(side="left", anchor="s")

    root.protocol("WM_DELETE_WINDOW", finish)
    root.mainloop()
    return 0


def _open_mic_settings() -> None:
    try:
        permissions.open_pane("Microphone")
    except Exception:
        pass
