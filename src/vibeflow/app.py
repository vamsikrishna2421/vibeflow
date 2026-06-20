"""The VibeFlow application: state machine + system-tray UI.

Wires together the hotkey listener, microphone, transcriber and output router,
and exposes everything through a small tray icon menu. The VibeFlow logo sits in
the system tray with a small status dot:

    (no dot)  = idle (ready)
    red dot   = recording
    amber dot = transcribing

All heavy work (transcription) runs off the hotkey/UI threads so the app stays
responsive.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from . import (
    __app_name__,
    __version__,
    ai_format,
    ai_setup,
    autostart,
    config as config_mod,
    icons,
    notifier,
    overlay as overlay_mod,
)
from .audio import AudioError, Recorder
from .focus_detect import detect_focus
from .hotkey import HotkeyManager
from .output import COPIED, deliver
from .curate import curate
from .text import clean_transcript, preview
from .transcriber import Transcriber, TranscriptionError
from .persona import Persona
from .vocabulary import Vocabulary

_APP_USER_MODEL_ID = "VibeFlow.Dictation"


def _set_app_user_model_id() -> None:
    """Tag the process so Windows shows the VibeFlow identity in notifications
    and groups it on the taskbar. (The microphone 'in use by' name comes from
    the packaged executable's version metadata, not from this.)"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            _APP_USER_MODEL_ID
        )
    except Exception:
        pass


class VibeFlowApp:
    """Owns application state and the tray UI."""

    def __init__(self, cfg: config_mod.Config) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._recording = False
        self._busy = False
        self._model_ready = False
        self._status = "Starting…"

        self.recorder = self._build_recorder()
        self.transcriber = self._build_transcriber()
        self.hotkeys = self._build_hotkeys()
        self.overlay = overlay_mod.StatusOverlay(
            enabled=bool(self.cfg.get("feedback.overlay", True))
        )
        self.vocabulary = self._build_vocabulary()
        self.persona = self._build_persona()
        self._last_output = None        # what we last produced (for teach-back)
        self._last_output_ts = 0.0
        self._clip_last = None
        self._stopping = False
        self._vocab_wordlist_mtime = None  # set when the user opens the word list
        self.icon = None  # set in run()

    # ------------------------------------------------------------------
    # Builders (re-used on config reload)
    # ------------------------------------------------------------------
    def _build_recorder(self) -> Recorder:
        return Recorder(
            sample_rate=int(self.cfg.get("audio.sample_rate", 16000)),
            input_device=self.cfg.get("audio.input_device", "default"),
        )

    def _build_transcriber(self) -> Transcriber:
        return Transcriber(
            size=self.cfg.get("model.size", "base"),
            language=self.cfg.get("model.language", "auto"),
            device=self.cfg.get("model.device", "auto"),
            compute_type=self.cfg.get("model.compute_type", "auto"),
            models_dir=str(config_mod.models_dir()),
        )

    def _build_hotkeys(self) -> HotkeyManager:
        return HotkeyManager(
            mode=self.cfg.get("hotkey.mode", "push_to_talk"),
            toggle_combo=self.cfg.get("hotkey.toggle_combo", "ctrl+win"),
            push_to_talk_key=self.cfg.get("hotkey.push_to_talk_key", "ctrl+win"),
            on_start=self.start_recording,
            on_stop=self.stop_recording,
        )

    def _build_vocabulary(self) -> Vocabulary:
        return Vocabulary(
            path=config_mod.config_dir() / "vocabulary.json",
            seed=self.cfg.get("text.vocabulary", []) or [],
        )

    def _build_persona(self) -> Persona:
        return Persona(path=config_mod.config_dir() / "persona.json")

    # ------------------------------------------------------------------
    # Recording lifecycle (called from hotkey threads)
    # ------------------------------------------------------------------
    def start_recording(self) -> None:
        with self._lock:
            if self._recording or self._busy:
                # Already busy: don't stack recordings. Keep trigger state sane.
                self.hotkeys.reset_toggle()
                notifier.play(notifier.ERROR, self._sounds)
                return
            self._recording = True

        try:
            self.recorder.start()
        except AudioError as exc:
            with self._lock:
                self._recording = False
            self.hotkeys.reset_toggle()
            self._notify("Microphone error", str(exc))
            notifier.play(notifier.ERROR, self._sounds)
            self._refresh()
            return

        notifier.play(notifier.START, self._sounds)
        self.overlay.show("listening")
        self._set_status("Listening…")
        self._refresh()

    def stop_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            self._busy = True

        audio = self.recorder.stop()
        notifier.play(notifier.STOP, self._sounds)
        self.overlay.show("transcribing")
        self._set_status("Transcribing…")
        self._refresh()

        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio) -> None:
        try:
            seconds = self.recorder.duration(audio)
            min_seconds = float(self.cfg.get("audio.min_seconds", 0.4))
            if seconds < min_seconds:
                self.overlay.show("info", "VibeFlow · Too short — ignored")
                self._notify(__app_name__, "Recording too short — ignored.")
                return

            text = self.transcriber.transcribe(audio, prompt=self.vocabulary.prompt())
            self._model_ready = True
            if bool(self.cfg.get("text.debug_log", False)):
                logging.getLogger("vibeflow").info(
                    "debug raw transcript: %r", (text or "")[:240]
                )
            text = clean_transcript(
                text,
                strip=bool(self.cfg.get("text.strip", True)),
                capitalize_first=bool(self.cfg.get("text.capitalize_first", False)),
                remove_trailing_period=bool(
                    self.cfg.get("text.remove_trailing_period", False)
                ),
            )
            if not text:
                self.overlay.show("info", "VibeFlow · No speech detected")
                self._notify(__app_name__, "No speech detected.")
                return

            # Stage 4: deterministic offline curation, then optional AI cleanup.
            text = curate(
                text,
                spoken_commands=bool(self.cfg.get("text.spoken_commands", True)),
                capitalize_sentences=bool(
                    self.cfg.get("text.capitalize_sentences", True)
                ),
            )
            persona_on = bool(self.cfg.get("text.persona", True))
            if ai_format.is_enabled(self.cfg):
                profile = self.persona.profile_text() if persona_on else None
                ai_text = ai_format.format_text(text, self.cfg, persona=profile)
                if ai_text:
                    text = ai_text

            focus = detect_focus()
            result = deliver(
                text,
                output_mode=self.cfg.get("output.mode", "auto"),
                focus_state=focus,
                insertion=self.cfg.get("output.insertion", "paste"),
                trailing_space=bool(self.cfg.get("output.trailing_space", True)),
                auto_fallback=self.cfg.get("output.auto_fallback", "clipboard"),
            )
            # Remember our output so we can learn from your later edits
            # (teach-back). We deliberately do NOT learn from this raw output —
            # it may contain mistakes, and we must never bias toward those.
            self._last_output = text.strip()
            self._last_output_ts = time.time()
            logging.getLogger("vibeflow").info(
                "teach-back armed: output_len=%d", len(self._last_output)
            )
            logging.getLogger("vibeflow").info(
                "delivered: focus=%s result=%s chars=%d", focus, result, len(text)
            )
            # Persona profiling (opt-in): keep a capped local sample of what you
            # dictate, and periodically distil a short style profile (background).
            if persona_on and self.persona.add_sample(text):
                self.persona.save()
                if self.persona.needs_profile():
                    threading.Thread(target=self._profile_worker, daemon=True).start()
            if result == COPIED:
                self.overlay.show("clipboard")
                self._notify("Copied to clipboard", preview(text))
            else:
                self.overlay.show("done")
        except TranscriptionError as exc:
            notifier.play(notifier.ERROR, self._sounds)
            self.overlay.show("error", "VibeFlow · Transcription error")
            self._notify("Transcription error", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            notifier.play(notifier.ERROR, self._sounds)
            self.overlay.show("error", "VibeFlow · Something went wrong")
            self._notify("Unexpected error", str(exc))
        finally:
            with self._lock:
                self._busy = False
            self.hotkeys.reset_toggle()
            self._set_status("Ready")
            self._refresh()

    # ------------------------------------------------------------------
    # Teach-back: learn from the user's edits (copied/cut corrected text)
    # ------------------------------------------------------------------
    def _clip_watch_loop(self) -> None:
        try:
            import pyperclip
        except Exception:
            return
        while not self._stopping:
            time.sleep(1.2)
            self._maybe_apply_vocab_edits()
            self.vocabulary.reload_if_changed()  # pick up manager-window deletes
            self.persona.reload_if_changed()     # pick up profile-window edits
            if not bool(self.cfg.get("text.teach_back", True)):
                continue
            try:
                clip = pyperclip.paste()
            except Exception:
                continue
            if not isinstance(clip, str) or clip == self._clip_last:
                continue
            self._clip_last = clip
            logging.getLogger("vibeflow").info(
                "clip changed: len=%d armed=%s", len(clip), self._last_output is not None
            )
            self._maybe_learn_from_clip(clip)

    def _maybe_learn_from_clip(self, clip: str) -> None:
        out = self._last_output
        if not out or not clip:
            return
        clip = clip.strip()
        if not clip or clip == out.strip():
            return
        if time.time() - self._last_output_ts > 600:  # only within ~10 minutes
            return
        if not (2 <= len(clip) <= 5000):
            return
        # Only learn from an *edited copy of our own output* — i.e. you dictated,
        # fixed a few words, and copied the whole thing. This keeps unrelated
        # clipboard copies out. (No need to select single words — copy it all.)
        import difflib

        ratio = difflib.SequenceMatcher(None, out, clip).ratio()
        logging.getLogger("vibeflow").info(
            "teach-back: ratio=%.2f (out_len=%d clip_len=%d)", ratio, len(out), len(clip)
        )
        if bool(self.cfg.get("text.debug_log", False)):
            logging.getLogger("vibeflow").info(
                "debug correction: out=%r clip=%r", out[:240], clip[:240]
            )
        if not (0.5 <= ratio < 0.999):
            return

        # Primary: a local LLM reads the corrected text and names the technical
        # terms worth remembering. Safety net: the deterministic learner (precise,
        # offline, no model needed) catches corrected look-alikes the model may
        # skip. Union the two so we get the LLM's breadth without ever regressing.
        learned: list = []
        terms = None
        ai_on = bool(self.cfg.get("text.ai_learning", False))
        if ai_on:
            # Show a live pill — the local model can take a few seconds to warm up.
            self.overlay.show("working", "VibeFlow · Learning your terms…")
            try:
                from . import ai_format

                terms = ai_format.extract_terms(clip, self.cfg)
            except Exception:
                terms = None
            if terms:
                learned += self.vocabulary.learn_terms(terms)
        learned += self.vocabulary.learn_from_correction(out, clip)
        learned = list(dict.fromkeys(learned))
        logging.getLogger("vibeflow").info(
            "teach-back llm_terms=%s learned=%s", terms, learned
        )
        if learned:
            self._last_output = None  # consume only after we actually learned
            self.vocabulary.save()
            shown = ", ".join(learned[:6])
            # The overlay is what the user actually sees (tray balloons are
            # unreliable on Windows); show it there *and* fire the notification.
            self.overlay.show("learned", f"VibeFlow · Learned: {shown}")
            self._notify(__app_name__, "Learned from your edit: " + shown)
        elif ai_on:
            self.overlay.hide()  # clear the "Learning…" pill if nothing qualified

    # ------------------------------------------------------------------
    # Tray UI
    # ------------------------------------------------------------------
    def run(self) -> None:
        _set_app_user_model_id()
        try:
            import pystray
        except Exception as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "The tray UI (pystray) is not installed. "
                "Run the installer or 'pip install -r requirements.txt'."
            ) from exc

        self.icon = pystray.Icon(
            __app_name__,
            icon=icons.make_tray_image("idle"),
            title=self._tooltip(),
            menu=self._menu(pystray),
        )
        self.icon.run(setup=self._on_ready)

    def _on_ready(self, icon) -> None:
        icon.visible = True
        self._set_status("Loading model…")
        self._refresh()
        self.overlay.start()
        self.hotkeys.start()
        threading.Thread(target=self._clip_watch_loop, daemon=True).start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        self._apply_install_opt_ins()

    def _preload_model(self) -> None:
        try:
            self.transcriber.load()
            self._model_ready = True
            self._set_status("Ready")
            logging.getLogger("vibeflow").info(
                "Model ready: %s %s", self.cfg.get("model.size"), self.transcriber._resolved
            )
            self._notify(
                __app_name__,
                f"Ready. {self._trigger_hint()} to dictate.",
            )
        except Exception as exc:
            import traceback

            logging.getLogger("vibeflow").error(
                "Model load failed:\n%s", traceback.format_exc()
            )
            self._set_status("Model failed to load")
            self._notify("Could not load speech model", str(exc))
        finally:
            self._refresh()

    def _menu(self, pystray):
        Item = pystray.MenuItem
        Menu = pystray.Menu
        return Menu(
            Item(lambda _: self._status, None, enabled=False),
            Item(lambda _: f"Hold {self._hotkey_label()} to talk", None, enabled=False),
            Menu.SEPARATOR,
            Item(
                "Output",
                Menu(
                    Item(
                        "Auto (type or clipboard)",
                        lambda i: self._set_output("auto"),
                        checked=lambda i: self.cfg.get("output.mode") == "auto",
                        radio=True,
                    ),
                    Item(
                        "Always type",
                        lambda i: self._set_output("type"),
                        checked=lambda i: self.cfg.get("output.mode") == "type",
                        radio=True,
                    ),
                    Item(
                        "Always clipboard",
                        lambda i: self._set_output("clipboard"),
                        checked=lambda i: self.cfg.get("output.mode") == "clipboard",
                        radio=True,
                    ),
                ),
            ),
            Item(
                "Speech accuracy",
                Menu(
                    Item(
                        "Fast (base · ~0.9s, recommended)",
                        lambda i: self._set_accuracy("base"),
                        checked=lambda i: self.cfg.get("model.size") == "base",
                        radio=True,
                    ),
                    Item(
                        "Balanced (small · ~2.7s)",
                        lambda i: self._set_accuracy("small"),
                        checked=lambda i: self.cfg.get("model.size") == "small",
                        radio=True,
                    ),
                ),
            ),
            Item(
                "AI formatting",
                Menu(
                    Item(
                        "Off (plain voice-to-text)",
                        lambda i: self._set_ai_model("off"),
                        checked=lambda i: not bool(self.cfg.get("ai.enabled", False)),
                        radio=True,
                    ),
                    Item(
                        "Fast — qwen2.5:1.5b (1 GB · recommended)",
                        lambda i: self._set_ai_model("fast"),
                        checked=lambda i: self._ai_tier() == "fast",
                        radio=True,
                    ),
                    Item(
                        "Balanced — qwen2.5:3b (2 GB)",
                        lambda i: self._set_ai_model("balanced"),
                        checked=lambda i: self._ai_tier() == "balanced",
                        radio=True,
                    ),
                    Item(
                        "Best — gemma2:2b (1.6 GB)",
                        lambda i: self._set_ai_model("best"),
                        checked=lambda i: self._ai_tier() == "best",
                        radio=True,
                    ),
                ),
            ),
            Menu.SEPARATOR,
            Item("Open settings file", self._open_config),
            Item("Open settings folder", self._open_config_dir),
            Item("Reload settings", self._reload),
            Menu.SEPARATOR,
            Item(
                "Show on-screen status",
                self._toggle_overlay,
                checked=lambda i: bool(self.cfg.get("feedback.overlay", True)),
            ),
            Item(
                "Learn from my edits",
                self._toggle_teachback,
                checked=lambda i: bool(self.cfg.get("text.teach_back", True)),
            ),
            Item(
                "Adaptive learning (AI · ~2 GB RAM while learning)",
                self._toggle_ai_learning,
                checked=lambda i: bool(self.cfg.get("text.ai_learning", False)),
            ),
            Item(
                lambda i: f"My vocabulary ({len(self.vocabulary.terms)} words)…",
                self._open_vocabulary,
            ),
            Item(
                "Personalized AI",
                Menu(
                    Item(
                        "Match my writing style",
                        self._toggle_persona,
                        checked=lambda i: bool(self.cfg.get("text.persona", True)),
                    ),
                    Item(
                        lambda i: f"View my profile ({len(self.persona.samples)} samples)…",
                        self._open_persona,
                    ),
                    Item("Forget my writing style", self._forget_persona),
                ),
            ),
            Item(
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda i: autostart.is_enabled(),
            ),
            Item(
                "Detailed logging (troubleshooting)",
                self._toggle_debug_log,
                checked=lambda i: bool(self.cfg.get("text.debug_log", False)),
            ),
            Item(f"About {__app_name__} {__version__}", self._about),
            Item("Quit", self._quit),
        )

    # -- menu actions ---------------------------------------------------
    def _set_output(self, mode: str) -> None:
        self.cfg.set("output.mode", mode)
        self._save_config()
        self._notify(__app_name__, f"Output set to '{mode}'.")
        self._refresh()

    def _open_config(self, *_args) -> None:
        path = config_mod.ensure_user_config()
        self._open_path(str(path))

    def _open_config_dir(self, *_args) -> None:
        self._open_path(str(config_mod.config_dir()))

    def _reload(self, *_args) -> None:
        self.cfg = config_mod.load_config(self.cfg.path)
        self.recorder = self._build_recorder()
        self.transcriber = self._build_transcriber()
        self.vocabulary = self._build_vocabulary()
        self.persona = self._build_persona()
        self._model_ready = False
        self.hotkeys.stop()
        self.hotkeys = self._build_hotkeys()
        self.hotkeys.start()
        self.overlay.set_enabled(bool(self.cfg.get("feedback.overlay", True)))
        threading.Thread(target=self._preload_model, daemon=True).start()
        self._notify(__app_name__, "Settings reloaded.")

    def _about(self, *_args) -> None:
        self._notify(
            f"{__app_name__} {__version__}",
            f"Offline voice typing. {self._trigger_hint()} to dictate.",
        )

    def _toggle_autostart(self, *_args) -> None:
        enabled = autostart.toggle()
        self._notify(
            __app_name__,
            "VibeFlow will start automatically with Windows."
            if enabled
            else "VibeFlow will no longer start with Windows.",
        )

    def _toggle_overlay(self, *_args) -> None:
        enabled = not bool(self.cfg.get("feedback.overlay", True))
        self.cfg.set("feedback.overlay", enabled)
        self._save_config()
        self.overlay.set_enabled(enabled)
        if enabled:
            self.overlay.show("info", "VibeFlow · On-screen status on")
        self._refresh()

    def _toggle_teachback(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.teach_back", True))
        self.cfg.set("text.teach_back", enabled)
        self._save_config()
        self._notify(
            __app_name__,
            "Will learn from your edits — just cut/copy your corrected text."
            if enabled
            else "Stopped learning from your edits.",
        )
        self._refresh()

    def _toggle_debug_log(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.debug_log", False))
        self.cfg.set("text.debug_log", enabled)
        self._save_config()
        self._notify(
            __app_name__,
            "Detailed logging ON — your raw transcript and corrections go to "
            "vibeflow.log (for troubleshooting)."
            if enabled
            else "Detailed logging off.",
        )
        self._refresh()

    # -- vocabulary viewing / pruning ----------------------------------
    def _vocab_wordlist_path(self):
        return config_mod.config_dir() / "my_vocabulary.txt"

    def _open_vocabulary(self, *_args) -> None:
        """Open the interactive vocabulary manager window. Falls back to a
        plain editable text list if the window can't be launched."""
        if self._launch_manager("--vocab-manager"):
            return
        path = self._vocab_wordlist_path()
        try:
            self.vocabulary.write_wordlist(path)
            # Baseline the mtime so writing it now isn't seen as a user edit;
            # only the user's subsequent save will trigger a reconcile.
            self._vocab_wordlist_mtime = path.stat().st_mtime
        except Exception:
            self._vocab_wordlist_mtime = None
        self._open_path(str(path))

    def _launch_manager(self, flag: str) -> bool:
        """Launch a standalone manager window (own process, own Tk loop)."""
        import subprocess

        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable, flag]
            else:
                args = [sys.executable, "-m", "vibeflow", flag]
            subprocess.Popen(
                args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return True
        except Exception:
            return False

    def _maybe_apply_vocab_edits(self) -> None:
        """Apply the user's edits to the word list (delete/add words) when they
        save it. Watched from the clipboard loop; only active after the user has
        opened the list this session."""
        if self._vocab_wordlist_mtime is None:
            return
        path = self._vocab_wordlist_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime == self._vocab_wordlist_mtime:
            return
        self._vocab_wordlist_mtime = mtime
        try:
            added, removed = self.vocabulary.sync_from_wordlist(path)
        except Exception:
            return
        if added or removed:
            self.vocabulary.save()
            bits = []
            if added:
                bits.append(f"{added} added")
            if removed:
                bits.append(f"{removed} removed")
            self._notify(__app_name__, "Vocabulary updated — " + ", ".join(bits) + ".")

    # -- persona profiling (opt-in) ------------------------------------
    def _toggle_persona(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.persona", True))
        self.cfg.set("text.persona", enabled)
        self._save_config()
        if enabled:
            self._notify(
                __app_name__,
                "Personalized AI on. VibeFlow keeps a small, local sample of your "
                "dictation and learns your domain & tone to format text more like "
                "you. Works with AI formatting; nothing leaves your PC. View or "
                "clear it anytime in the tray.",
            )
        else:
            self._notify(__app_name__, "Personalized AI off.")
        self._refresh()

    def _profile_worker(self) -> None:
        try:
            profile = ai_format.build_persona_profile(
                self.persona.sample_texts(), self.cfg
            )
        except Exception:
            profile = None
        if profile:
            self.persona.set_profile(profile)
            self.persona.save()
            logging.getLogger("vibeflow").info(
                "persona profile updated (%d chars, %d samples)",
                len(profile),
                len(self.persona.samples),
            )
            self._notify(
                __app_name__, "Updated your writing profile from recent dictation."
            )

    def _open_persona(self, *_args) -> None:
        if self._launch_manager("--persona-manager"):
            return
        path = config_mod.config_dir() / "my_writing_profile.txt"
        profile = self.persona.profile_text() or (
            "(Not enough dictation yet — keep using VibeFlow and it will learn "
            "your style.)"
        )
        body = (
            "# VibeFlow — your writing profile\n"
            "#\n"
            "# What VibeFlow has learned about your domain and tone from your\n"
            "# recent dictation. Used (only when 'Match my writing style' AND AI\n"
            "# formatting are on) to format text more like you. Local to this PC.\n"
            "# To reset it, choose 'Forget my writing style' in the tray.\n"
            "# ------------------------------------------------------------------\n\n"
            f"{profile}\n\n"
            f"(based on {len(self.persona.samples)} recent dictations)\n"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        except Exception:
            return
        self._open_path(str(path))

    def _forget_persona(self, *_args) -> None:
        self.persona.clear()
        self.persona.save()
        self._notify(
            __app_name__, "Forgot your writing profile. It will rebuild as you dictate."
        )
        self._refresh()

    def _toggle_ai_learning(self, *_args) -> None:
        """Opt in/out of AI-powered background learning (a local LLM picks the
        technical terms out of your corrected text). Discloses the cost and
        sets the model up automatically on opt-in."""
        if bool(self.cfg.get("text.ai_learning", False)):
            self.cfg.set("text.ai_learning", False)
            self._save_config()
            self._notify(
                __app_name__,
                "Adaptive AI learning off. Your edits are still learned offline.",
            )
            self._refresh()
            return
        model = str(self.cfg.get("text.teach_back_model", "qwen2.5:3b"))
        self._notify(
            __app_name__,
            f"Setting up adaptive learning ({model}). One-time ~1.8 GB download, "
            "then ~2 GB RAM only while learning (freed when idle, runs only when "
            "you edit and copy a transcript). Watch the tray tooltip for progress.",
        )
        threading.Thread(
            target=self._setup_learning_worker, args=(model,), daemon=True
        ).start()

    def _setup_learning_worker(self, model: str) -> None:
        def progress(message: str) -> None:
            self._set_status(message)
            self._refresh()

        ok, message = ai_setup.setup(model, progress=progress)
        if ok:
            self.cfg.set("text.ai_learning", True)
            self.cfg.set("text.teach_back", True)  # learning rides on teach-back
            self.cfg.set("text.teach_back_model", model)
            self._save_config()
        self._notify(
            "Adaptive learning ready" if ok else "Adaptive learning setup failed",
            message,
        )
        self._set_status("Ready")
        self._refresh()

    def _apply_install_opt_ins(self) -> None:
        """Honor install-time opt-ins. The installer writes a one-shot HKCU
        marker when the user ticks the optional 'adaptive learning' checkbox;
        we enable it once (downloading the model with progress) and clear it."""
        if os.name != "nt":
            return
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\VibeFlow",
                0,
                winreg.KEY_READ | winreg.KEY_SET_VALUE,
            )
        except OSError:
            return
        try:
            try:
                value, _ = winreg.QueryValueEx(key, "EnableAiLearning")
            except OSError:
                value = None
            if value:
                winreg.DeleteValue(key, "EnableAiLearning")  # one-shot signal
                if not bool(self.cfg.get("text.ai_learning", False)):
                    model = str(self.cfg.get("text.teach_back_model", "qwen2.5:3b"))
                    threading.Thread(
                        target=self._setup_learning_worker, args=(model,), daemon=True
                    ).start()
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)

    def _set_accuracy(self, size: str) -> None:
        self.cfg.set("model.size", size)
        self._save_config()
        self.transcriber = self._build_transcriber()
        self._model_ready = False
        labels = {"base": "Fast", "small": "Balanced"}
        self._notify(
            __app_name__,
            f"Speech accuracy: {labels.get(size, size)}. The model downloads on "
            "first use if it's new.",
        )
        self._set_status("Loading model…")
        self._refresh()
        threading.Thread(target=self._preload_model, daemon=True).start()

    def _ai_tier(self):
        if not bool(self.cfg.get("ai.enabled", False)):
            return None
        model = self.cfg.get("ai.model")
        for tier, (tier_model, _size) in ai_setup.MODEL_TIERS.items():
            if tier_model == model:
                return tier
        return None

    def _set_ai_model(self, tier: str) -> None:
        if tier == "off":
            self.cfg.set("ai.enabled", False)
            self._save_config()
            self._notify(__app_name__, "AI formatting off — plain voice-to-text.")
            self._refresh()
            return
        model, size = ai_setup.MODEL_TIERS[tier]
        self._notify(
            __app_name__,
            f"Setting up AI ({model}, {size}). I'll install and download everything "
            "automatically — watch the tray tooltip for progress.",
        )
        threading.Thread(
            target=self._setup_ai_worker, args=(model,), daemon=True
        ).start()

    def _setup_ai_worker(self, model: str) -> None:
        def progress(message: str) -> None:
            self._set_status(message)
            self._refresh()

        ok, message = ai_setup.setup(model, progress=progress)
        logging.getLogger("vibeflow").info(
            "AI setup: model=%s ok=%s msg=%s", model, ok, message
        )
        if ok:
            self.cfg.set("ai.enabled", True)
            self.cfg.set("ai.model", model)
            self._save_config()
        self._notify("AI formatting ready" if ok else "AI setup failed", message)
        self._set_status("Ready")
        self._refresh()

    def _quit(self, *_args) -> None:
        self._stopping = True
        # Note: vocabulary is saved on every learn, so we do NOT save on quit —
        # that prevents a stale instance from clobbering good data with old data.
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.overlay.stop()
        except Exception:
            pass
        if self.icon is not None:
            self.icon.stop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def _sounds(self) -> bool:
        return bool(self.cfg.get("feedback.sounds", True))

    def _hotkey_label(self) -> str:
        key = str(self.cfg.get("hotkey.push_to_talk_key", "ctrl+win"))
        return "+".join(p.strip().capitalize() for p in key.split("+") if p.strip())

    def _trigger_hint(self) -> str:
        return f"Hold {self._hotkey_label()}"

    def _save_config(self) -> None:
        try:
            self.cfg.save()
        except Exception as exc:
            self._notify("Could not save settings", str(exc))

    def _set_status(self, status: str) -> None:
        self._status = status

    def _tooltip(self) -> str:
        return f"{__app_name__} — {self._status}"

    def _state_name(self) -> str:
        if self._recording:
            return "recording"
        if self._busy:
            return "busy"
        return "idle"

    def _refresh(self) -> None:
        if self.icon is None:
            return
        try:
            self.icon.icon = icons.make_tray_image(self._state_name())
            self.icon.title = self._tooltip()
        except Exception:
            pass
        # Re-render the menu so radio/checkbox state (e.g. the selected AI tier)
        # reflects the current config instead of a stale value from startup.
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _notify(self, title: str, message: str) -> None:
        if not bool(self.cfg.get("feedback.notifications", True)):
            return
        if self.icon is None:
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    @staticmethod
    def _open_path(path: str) -> None:
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)  # type: ignore[attr-defined]  # Windows
            else:  # pragma: no cover - non-Windows
                import subprocess
                import sys

                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, path])
        except Exception:
            pass
