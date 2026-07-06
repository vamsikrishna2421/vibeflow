"""
First-run onboarding (WINDOWS) — a one-time welcome window (own process, via
``VibeFlow.exe --onboarding``). It greets, shows how to dictate, and runs a
**live microphone check** so a blocked/muted/wrong mic is caught here — before
the user's very first dictation — instead of surfacing later as a mystifying
"no speech". Windows-only copy; the Mac build has its own. Visuals from the
shared ``theme`` module.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import __app_name__, __version__, config as config_mod, theme as T


def _hotkey_label(cfg) -> str:
    if str(cfg.get("hotkey.mode", "push_to_talk")) == "push_to_talk":
        return f"hold {cfg.get('hotkey.push_to_talk_key', 'right ctrl')}"
    return f"press {cfg.get('hotkey.toggle_combo', 'ctrl+space')}"


def run(config_path: str | None = None) -> int:
    cfg = config_mod.load_config(config_path)
    root = tk.Tk()
    root.title(f"Welcome to {__app_name__}")
    root.configure(bg=T.BG)
    try:
        root.geometry("500x470")
        root.resizable(False, False)
    except Exception:
        pass

    def label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", T.BG), fg=kw.pop("fg", T.INK), **kw)

    label(root, "Welcome to VibeFlow", font=T.font(T.DISPLAY, "bold")).pack(anchor="w", padx=26, pady=(24, 2))
    label(root, "Premium voice-to-text that types wherever you are — fully on-device.",
          fg=T.SOFT, font=T.font(T.BODY), wraplength=450, justify="left").pack(anchor="w", padx=26)

    # Step 1 — how to dictate
    s1 = T.rounded_card(root, fill="x", padx=22, pady=(18, 8))
    label(s1, "1 · How to dictate", bg=T.CARD, fg=T.BRAND, font=T.font(T.LABEL, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    label(s1, f"{_hotkey_label(cfg).capitalize()} and just speak. Your words appear "
              "instantly wherever your cursor is — email, chat, docs, anywhere.",
          bg=T.CARD, fg=T.INK, font=T.font(T.BODY), wraplength=430, justify="left").pack(anchor="w", padx=16, pady=(0, 14))

    # Step 2 — microphone check
    s2 = T.rounded_card(root, fill="x", padx=22, pady=8)
    label(s2, "2 · Check your microphone", bg=T.CARD, fg=T.BRAND, font=T.font(T.LABEL, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    mic_status = label(s2, "Let's make sure VibeFlow can hear you.", bg=T.CARD, fg=T.INK,
                       font=T.font(T.BODY), wraplength=430, justify="left")
    mic_status.pack(anchor="w", padx=16, pady=(0, 8))
    mic_row = tk.Frame(s2, bg=T.CARD)
    mic_row.pack(anchor="w", padx=16, pady=(0, 14))
    test_btn = ttk.Button(mic_row, text="🎤  Test my microphone")
    test_btn.pack(side="left")
    settings_link = label(s2, "Open Microphone settings →", bg=T.CARD, fg=T.SOFT,
                          font=T.font(T.CAPTION), cursor="hand2")
    settings_link.bind("<Button-1>", lambda e: _open_mic_settings())

    def mic_test():
        test_btn.config(state="disabled")
        mic_status.config(text="Listening… say anything, like “testing, one two three”.", fg=T.LIVE)
        settings_link.pack_forget()

        def work():
            try:
                import time
                from .audio import Recorder, peak_level
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
                    mic_status.config(text=f"Couldn't run the test: {exc_msg}", fg=T.ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                elif peak < 0.02:
                    mic_status.config(
                        text="⚠ That's very quiet — VibeFlow can barely hear you. Usually "
                             "it's mic permission or the wrong mic selected.", fg=T.ERR)
                    settings_link.pack(anchor="w", padx=16, pady=(0, 14))
                else:
                    mic_status.config(text="✓ Loud and clear — your mic's all set.", fg=T.OK)
                    _unlock_cta()
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

    bar = tk.Frame(root, bg=T.BG)
    bar.pack(side="bottom", fill="x", padx=24, pady=18)
    label(bar, f"VibeFlow {__version__}", bg=T.BG, fg=T.FAINT, font=T.font(T.CAPTION)).pack(side="left", anchor="s")
    # Gate: the prominent CTA appears only after the mic test passes — so nobody
    # leaves onboarding without confirming VibeFlow can actually hear them (the
    # exact silent-mic trap this window exists to prevent). A quiet skip stays.
    cta = tk.Frame(bar, bg=T.BG)
    cta.pack(side="right")
    skip = label(cta, "Skip for now →", bg=T.BG, fg=T.SOFT, font=T.font(T.BODY), cursor="hand2")
    skip.pack(side="right")
    skip.bind("<Button-1>", lambda e: finish())

    def _unlock_cta():
        try:
            skip.pack_forget()
        except Exception:
            pass
        T.primary_button(cta, "Start dictating  →", finish).pack(side="right")

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
