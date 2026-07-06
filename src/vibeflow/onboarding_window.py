"""
First-run onboarding (WINDOWS) — a one-time welcome window (own process, via
``VibeFlow.exe --onboarding``). It greets, shows how to dictate, and runs a
**live microphone check** so a blocked/muted/wrong mic is caught here — before
the user's very first dictation — instead of surfacing later as a mystifying
"no speech". Windows-only copy; the Mac build has its own.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import __app_name__, __version__, config as config_mod

_BG = "#141020"
_CARD = "#1b1730"
_INK = "#f4f2fb"
_SOFT = "#b7b2d0"
_BRAND = "#8b6dff"
_OK = "#3ed598"
_ERR = "#ff6b6b"


def _hotkey_label(cfg) -> str:
    if str(cfg.get("hotkey.mode", "push_to_talk")) == "push_to_talk":
        return f"hold {cfg.get('hotkey.push_to_talk_key', 'right ctrl')}"
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

    # Hero
    label(root, "Welcome to VibeFlow", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=26, pady=(24, 2))
    label(root, "Premium voice-to-text that types wherever you are — fully on-device.",
          fg=_SOFT, font=("Segoe UI", 11), wraplength=450, justify="left").pack(anchor="w", padx=26)

    # Step 1 — how to dictate
    s1 = tk.Frame(root, bg=_CARD)
    s1.pack(fill="x", padx=22, pady=(18, 8))
    label(s1, "1 · How to dictate", bg=_CARD, fg=_BRAND, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    label(s1, f"{_hotkey_label(cfg).capitalize()} and just speak. Your words appear "
              "instantly wherever your cursor is — email, chat, docs, anywhere.",
          bg=_CARD, fg=_INK, font=("Segoe UI", 11), wraplength=430, justify="left").pack(anchor="w", padx=16, pady=(0, 14))

    # Step 2 — microphone check
    s2 = tk.Frame(root, bg=_CARD)
    s2.pack(fill="x", padx=22, pady=8)
    label(s2, "2 · Check your microphone", bg=_CARD, fg=_BRAND, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    mic_status = label(s2, "Let's make sure VibeFlow can hear you.", bg=_CARD, fg=_INK,
                       font=("Segoe UI", 11), wraplength=430, justify="left")
    mic_status.pack(anchor="w", padx=16, pady=(0, 8))
    mic_row = tk.Frame(s2, bg=_CARD)
    mic_row.pack(anchor="w", padx=16, pady=(0, 14))
    test_btn = ttk.Button(mic_row, text="🎤 Test my microphone")
    test_btn.pack(side="left")
    settings_link = label(s2, "Open Microphone settings →", bg=_CARD, fg=_SOFT,
                          font=("Segoe UI", 9, "underline"), cursor="hand2")
    settings_link.bind("<Button-1>", lambda e: _open_mic_settings())
    # (shown only if the test finds a problem)

    def mic_test():
        test_btn.config(state="disabled")
        mic_status.config(text="Listening for 1.5s — say a few words…", fg=_INK)
        settings_link.pack_forget()

        def work():
            try:
                import time
                from .audio import Recorder, peak_level, SILENCE_PEAK
                rec = Recorder(sample_rate=int(cfg.get("audio.sample_rate", 16000)),
                               input_device=cfg.get("audio.input_device", "default"))
                rec.start()
                time.sleep(1.5)
                audio = rec.stop()
                peak = peak_level(audio)
            except Exception as exc:
                peak, SILENCE_PEAK, exc_msg = 0.0, 1e-4, str(exc)
            else:
                exc_msg = None

            def show():
                test_btn.config(state="normal")
                if exc_msg:
                    mic_status.config(text=f"Couldn't run the test: {exc_msg}", fg=_ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                elif peak < 0.02:
                    mic_status.config(
                        text=f"⚠ Barely heard anything (level {peak:.3f}). Check your mic "
                             "isn't muted, the right one is selected, and VibeFlow has "
                             "microphone access.", fg=_ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                else:
                    mic_status.config(text=f"✓ Your microphone is working (level {peak:.2f}). You're all set!",
                                      fg=_OK)
            root.after(0, show)

        threading.Thread(target=work, daemon=True).start()

    test_btn.config(command=mic_test)

    # Footer
    def finish():
        try:
            cfg.set("onboarding.completed", True)
            cfg.save()
        except Exception:
            pass
        root.destroy()

    bar = tk.Frame(root, bg=_BG)
    bar.pack(side="bottom", fill="x", padx=22, pady=18)
    start = ttk.Button(bar, text="Start dictating  →", command=finish)
    start.pack(side="right")
    label(bar, f"VibeFlow {__version__}", bg=_BG, fg=_SOFT, font=("Segoe UI", 8)).pack(side="left", anchor="s")

    root.protocol("WM_DELETE_WINDOW", finish)  # closing the window still marks it done
    root.mainloop()
    return 0


def _open_mic_settings() -> None:
    try:
        import os
        os.startfile("ms-settings:privacy-microphone")  # noqa: S606
    except Exception:
        try:
            webbrowser.open("ms-settings:privacy-microphone")
        except Exception:
            pass
