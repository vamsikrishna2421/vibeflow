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
    ai_setup,
    autostart,
    config as config_mod,
    icons,
    notifier,
    overlay as overlay_mod,
)
from . import licensing
from .core import ai_format, appmode, history
from .audio import AudioError, Recorder, is_silent
from .focus_detect import detect_focus
from .hotkey import DeliveryHotkey, HotkeyManager
from .output import COPIED, deliver
from .core.curate import curate
from .core.text import clean_transcript, expand_snippets, preview
from .transcriber import Transcriber, TranscriptionError
from .core.persona import Persona
from .core.vocabulary import Vocabulary

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
        self._cfg_mtime = None  # config.yaml mtime, to pick up Settings-window edits
        self._update_info = None  # set when a newer release is found
        self._last_raw_transcript = ""  # unedited transcript (for recovery)
        self._deliver_pending_until = 0.0  # arms the Ctrl+Shift+V delivery hotkey
        self._delivery_hotkey = None
        self.icon = None  # set in run()
        # Licensing (offline): paid features (AI formatting) gate on this.
        self._license = licensing.evaluate(config_mod.config_dir())
        self._license_nudged = False
        self._license_mtime = None

    # ------------------------------------------------------------------
    # Builders (re-used on config reload)
    # ------------------------------------------------------------------
    def _build_recorder(self) -> Recorder:
        return Recorder(
            sample_rate=int(self.cfg.get("audio.sample_rate", 16000)),
            input_device=self.cfg.get("audio.input_device", "auto"),
        )

    def _build_transcriber(self) -> Transcriber:
        return Transcriber(
            size=self.cfg.get("model.size", "base"),
            language=self.cfg.get("model.language", "en"),
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
                # Distinguish "the mic gave us silence" (a fixable setup problem)
                # from "we heard you but found no words". The first is the common
                # fresh-install trap: Windows hands a blocked/muted mic a silent
                # stream (no error), so dictation looks broken for no clear reason.
                if is_silent(audio):
                    self.overlay.show("info", "VibeFlow · No sound from mic")
                    self._notify(
                        __app_name__,
                        "No sound from the microphone. Check Windows mic access "
                        "(Settings ▸ Privacy & security ▸ Microphone ▸ turn on "
                        "“Let desktop apps access your microphone”) and that the "
                        "right mic is selected and not muted.",
                    )
                else:
                    self.overlay.show("info", "VibeFlow · No speech detected")
                    self._notify(__app_name__, "No speech detected.")
                return

            # Keep the user's own words recoverable (for the empty-output guard
            # and the tray "Copy last transcript (unedited)").
            self._last_raw_transcript = text.strip()

            strip_fillers = bool(self.cfg.get("text.strip_fillers", False))
            ai_on = ai_format.is_enabled(self.cfg)
            if ai_on and not self._license.is_paid:
                # AI formatting is a paid feature; voice-to-text stays free.
                ai_on = False
                if not self._license_nudged:
                    self._license_nudged = True
                    self._notify(
                        __app_name__,
                        "AI formatting is a VibeFlow Pro feature and your trial has "
                        "ended. Open the tray menu ▸ License to unlock it. "
                        "Voice-to-text stays free.",
                    )
            persona_on = bool(self.cfg.get("text.persona", True))

            # Per-app formatting: choose how to format for the destination app,
            # resolved from the foreground window now (re-verified before typing).
            # Fail-safe: any error falls back to DEFAULT (today's behaviour).
            outcome = appmode.DEFAULT
            target_hwnd = None
            target_name = None
            target_exe = ""
            try:
                if bool(self.cfg.get("text.modes.enabled", True)):
                    target_hwnd = appmode.foreground_hwnd()
                    app_id = appmode.target_app(target_hwnd)
                    outcome = appmode.resolve_outcome(
                        app_id, self.cfg.get("text.modes.rules", []) or []
                    )
                    target_name = app_id.friendly
                    target_exe = app_id.exe
            except Exception:  # pragma: no cover - never break dictation
                outcome = appmode.DEFAULT

            if outcome == appmode.VERBATIM:
                # "Leave as spoken": deliver the unedited transcript — no
                # deterministic curation, no AI (protects commands / code).
                text = self._last_raw_transcript
                if target_name:
                    self.overlay.show("info", f"VibeFlow · As spoken — {target_name}")
            else:
                # DEFAULT / PROFESSIONAL / CASUAL all start from deterministic
                # offline curation; AI then applies the tone when it is enabled.
                text = curate(
                    text,
                    spoken_commands=bool(self.cfg.get("text.spoken_commands", True)),
                    capitalize_sentences=bool(
                        self.cfg.get("text.capitalize_sentences", True)
                    ),
                    strip_fillers=(strip_fillers and not ai_on),  # regex only when AI off
                    fillers=self.cfg.get("text.fillers", []) or None,
                )
                tone = {appmode.PROFESSIONAL: "professional",
                        appmode.CASUAL: "casual",
                        appmode.EMAIL: "email"}.get(outcome)
                if ai_on:
                    # Visible "Restructuring for <App>…" while the local model runs.
                    if target_name:
                        label = (
                            f"Restructuring for {target_name}…" if tone
                            else f"Cleaning up — {target_name}"
                        )
                        self.overlay.show("info", f"VibeFlow · {label}")
                    profile = self.persona.profile_text() if persona_on else None
                    ai_text = ai_format.format_text(
                        text, self.cfg, persona=profile,
                        strip_fillers=strip_fillers, tone=tone,
                    )
                    if ai_text:
                        text = ai_text
                # If AI is OFF but a tone was requested, the deterministic
                # curation above is the graceful fallback (toggle precedence).

            # Safety: never type nothing for non-empty speech (e.g. an
            # all-filler utterance) — fall back to the user's raw words.
            if not text.strip() and self._last_raw_transcript:
                text = self._last_raw_transcript
                self._notify(__app_name__, "Only filler heard — inserted as-is.")

            try:
                text = expand_snippets(text, self.cfg.get("text.snippets", {}) or {})
            except Exception:  # pragma: no cover - never break dictation
                pass
            focus = detect_focus()
            result = deliver(
                text,
                output_mode=self.cfg.get("output.mode", "auto"),
                focus_state=focus,
                insertion=self.cfg.get("output.insertion", "paste"),
                trailing_space=bool(self.cfg.get("output.trailing_space", True)),
                auto_fallback=self.cfg.get("output.auto_fallback", "clipboard"),
                expected_hwnd=target_hwnd,
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
            # Optional local dictation history (opt-in; never breaks delivery).
            try:
                if bool(self.cfg.get("text.history.enabled", False)):
                    history.append(
                        text, target_name or "",
                        max_entries=int(self.cfg.get("text.history.max", 500) or 500),
                    )
            except Exception:  # pragma: no cover - never break dictation
                pass
            # One-time, in-context offer: the first time you dictate into a known
            # email/chat app, suggest the one-click Starter Pack. Consent-based —
            # nothing changes until you accept it from the tray.
            try:
                if (
                    target_exe
                    and appmode.app_category(target_exe)
                    and not bool(self.cfg.get("text.modes.starter_pack_offered", False))
                ):
                    self.cfg.set("text.modes.starter_pack_offered", True)
                    self._save_config()
                    self._notify(
                        __app_name__,
                        "Tip: VibeFlow can keep terminals & code editors exactly as you "
                        "speak them and adapt other apps to your style. Turn it on in "
                        "Settings → “Adapt formatting to each app”.",
                    )
            except Exception:  # pragma: no cover - never break dictation
                pass
            # Persona profiling (opt-in): keep a capped local sample of what you
            # dictate, and periodically distil a short style profile (background).
            if persona_on and self.persona.add_sample(text):
                self.persona.save()
                if self.persona.needs_profile():
                    threading.Thread(target=self._profile_worker, daemon=True).start()
            if result == COPIED:
                self.overlay.show("clipboard")
                # No field was focused, so the text is on the clipboard. Arm the
                # "deliver here" hotkey: click into any app within 60s and press
                # Ctrl+Shift+V to place it, formatted for that app.
                if self.cfg.get("text.modes.deliver_hotkey"):
                    self._deliver_pending_until = time.time() + float(
                        self.cfg.get("text.modes.pending_timeout", 60) or 60
                    )
                    self._notify(
                        "Dictation ready",
                        "On your clipboard. Click into any app and press "
                        "Ctrl+Shift+V to place it, formatted for that app.",
                    )
                else:
                    self._notify("Copied to clipboard", preview(text))
            else:
                self.overlay.show("done")
        except TranscriptionError as exc:
            import traceback

            logging.getLogger("vibeflow").error(
                "Transcription error:\n%s", traceback.format_exc()
            )
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
            self._maybe_reload_config()          # pick up Settings-window edits
            self.vocabulary.reload_if_changed()  # pick up manager-window deletes
            self.persona.reload_if_changed()     # pick up profile-window edits
            self._maybe_reload_license()          # pick up a newly-activated license
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
                from .core import ai_format

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
        self._delivery_hotkey = DeliveryHotkey(
            is_armed=lambda: time.time() < self._deliver_pending_until,
            on_fire=self._deliver_hotkey_fire,
        )
        self._delivery_hotkey.start()
        threading.Thread(target=self._clip_watch_loop, daemon=True).start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        self._apply_install_opt_ins()
        self._first_run_notice()
        threading.Thread(target=self._startup_update_check, daemon=True).start()

    def _first_run_notice(self) -> None:
        """One-time welcome + privacy note on the very first launch."""
        marker = config_mod.config_dir() / ".welcomed"
        try:
            if marker.exists():
                return
        except Exception:
            return
        self._notify(
            __app_name__,
            f"Welcome! Hold {self._hotkey_label()} to dictate anywhere. Everything "
            "runs on this PC. Personalized AI quietly learns your writing style "
            "locally (nothing leaves your computer; turn it off or clear it any "
            "time in the tray).",
        )
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1", encoding="utf-8")
        except Exception:
            pass

    def _model_cached(self) -> bool:
        """Is the chosen speech model already downloaded? (False on a fresh PC.)"""
        try:
            size = self.cfg.get("model.size", "base")
            base = config_mod.models_dir() / f"models--Systran--faster-whisper-{size}"
            return base.exists() and any(base.rglob("model.bin"))
        except Exception:
            return True  # don't nag if we can't tell

    def _preload_model(self) -> None:
        try:
            if not self._model_cached():
                # First-ever run: the model isn't on disk yet. Download it (needs
                # internet, and there is no file to be locked, so no retry).
                self._set_status("Downloading speech model…")
                self._refresh()
                self._notify(
                    __app_name__,
                    "First launch: downloading the speech model (~150 MB). This "
                    "happens once and needs internet — after that VibeFlow runs "
                    "fully offline.",
                )
                self.transcriber.load()
            else:
                # Cached model: load offline-only (fast local open, no network).
                # This short retry is just a safety net for a transient first-open
                # hiccup (e.g. antivirus scanning the model file). The real
                # auto-update failure — Windows "Redirection Guard", inherited from
                # the installer, refusing to traverse the model's cache symlink —
                # is fixed at the source: the installer now relaunches VibeFlow via
                # Explorer, outside its mitigated process tree.
                deadline = time.monotonic() + 12.0
                last_err = None
                while True:
                    try:
                        self.transcriber.load(allow_download=False)
                        last_err = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_err = exc
                        if time.monotonic() >= deadline:
                            break
                        self._set_status("Loading model…")
                        self._refresh()
                        time.sleep(2.0)
                if last_err is not None:
                    # Offline path never recovered. As a last resort allow a
                    # network reload once — covers a genuinely incomplete/corrupt
                    # cache (not a lock), and surfaces a clear error if offline.
                    self.transcriber.load(allow_download=True)
            self._model_ready = True
            self._set_status("Ready")
            import os as _os
            logging.getLogger("vibeflow").info(
                "Model ready: %s %s (cwd=%s)", self.cfg.get("model.size"),
                self.transcriber._resolved, _os.getcwd(),
            )
            self._notify(
                __app_name__,
                f"Ready. {self._trigger_hint()} to dictate.",
            )
        except Exception as exc:
            import os as _os
            import traceback

            try:
                _cwd = _os.getcwd()
                _cwd_ok = _os.path.isdir(_cwd)
            except Exception as _cwd_exc:  # noqa: BLE001
                _cwd, _cwd_ok = f"<getcwd failed: {_cwd_exc}>", False
            logging.getLogger("vibeflow").error(
                "Model load failed (cwd=%r exists=%s):\n%s",
                _cwd, _cwd_ok, traceback.format_exc(),
            )
            # Probe model.bin directly to capture the OS-level reason that
            # ctranslate2's generic "Unable to open file" message hides.
            try:
                import glob as _glob
                _log = logging.getLogger("vibeflow")
                _mdir = getattr(self.transcriber, "models_dir", "") or ""
                _bins = _glob.glob(_os.path.join(_mdir, "**", "model.bin"), recursive=True)
                _log.error("probe: models_dir=%r found=%d", _mdir, len(_bins))
                for _b in _bins:
                    _info = {"islink": _os.path.islink(_b)}
                    try:
                        _info["target"] = _os.readlink(_b)
                    except Exception:
                        _info["target"] = None
                    for _label, _p in (("link", _b), ("real", _os.path.realpath(_b))):
                        try:
                            with open(_p, "rb") as _fh:
                                _fh.read(16)
                            _info["open_" + _label] = "OK"
                        except OSError as _oe:
                            _info["open_" + _label] = (
                                "errno=%s winerror=%s %s"
                                % (_oe.errno, getattr(_oe, "winerror", None), _oe.strerror)
                            )
                    _log.error("probe %s: %s", _b, _info)
            except Exception as _pe:  # noqa: BLE001
                logging.getLogger("vibeflow").error("probe failed: %s", _pe)
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
            Item("Settings (stays open)…", self._open_settings),
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
                        "Fast — qwen2.5:1.5b (1 GB · fastest, may reword)",
                        lambda i: self._set_ai_model("fast"),
                        checked=lambda i: self._ai_tier() == "fast",
                        radio=True,
                    ),
                    Item(
                        "Balanced — qwen2.5:3b (2 GB · recommended, keeps your words)",
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
            Item("Manage AI models…", self._open_models_manager),
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
                "Remove filler words (um, uh)",
                self._toggle_fillers,
                checked=lambda i: bool(self.cfg.get("text.strip_fillers", True)),
            ),
            Item(
                "Adapt formatting to each app",
                Menu(
                    Item(
                        "Enabled",
                        self._toggle_modes,
                        checked=lambda i: bool(self.cfg.get("text.modes.enabled", True)),
                    ),
                    Menu.SEPARATOR,
                    Item("Clear my app rules", self._clear_modes_rules),
                ),
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
            Menu.SEPARATOR,
            Item("Copy last transcript (unedited)", self._copy_raw_transcript),
            Item(
                "Re-insert last dictation",
                Menu(
                    Item("Exactly as spoken", self._reinsert_spoken),
                    Item("Cleaned up", self._reinsert_cleaned),
                    Item("Formatted for this app", self._reinsert_for_app),
                ),
            ),
            Item(
                "Dictation history",
                Menu(
                    Item(
                        "Save my dictations (local)",
                        self._toggle_history,
                        checked=lambda i: bool(self.cfg.get("text.history.enabled", False)),
                    ),
                    Item("Open history…", self._open_history),
                    Item("Clear history", self._clear_history),
                ),
            ),
            Item("Report a problem…", self._report_problem),
            Item(
                lambda i: (
                    f"⬆ Install update ({self._update_info['version']})…"
                    if self._update_info
                    else "Check for updates"
                ),
                self._update_action,
            ),
            Menu.SEPARATOR,
            Item(lambda i: self._license_label(), self._open_license),
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

    def _license_label(self) -> str:
        return f"License · {self._license.badge}"

    def _open_license(self, *_args) -> None:
        self._launch_manager("--license")

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

    def _toggle_fillers(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.strip_fillers", False))
        self.cfg.set("text.strip_fillers", enabled)
        self._save_config()
        self._notify(
            __app_name__,
            "Filler words (um, uh) will be removed. Your unedited text stays "
            "available via the tray's “Copy last transcript (unedited).”"
            if enabled
            else "Keeping filler words as spoken.",
        )
        self._refresh()

    def _toggle_modes(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.modes.enabled", True))
        self.cfg.set("text.modes.enabled", enabled)
        self._save_config()
        self._notify(
            __app_name__,
            "Per-app formatting on: terminals and code editors keep your exact "
            "words; other apps format as usual. The on-screen status shows which "
            "app each dictation was formatted for."
            if enabled
            else "Per-app formatting off: every app uses your normal formatting.",
        )
        self._refresh()

    def _setup_starter_pack(self, *_args) -> None:
        """One click: email -> professional, chat -> casual (terminals/code stay
        as spoken by default). Rules for apps you don't have simply never fire."""
        self.cfg.set("text.modes.enabled", True)
        self.cfg.set("text.modes.rules", appmode.starter_pack_rules())
        self.cfg.set("text.modes.starter_pack_offered", True)
        self._save_config()
        self._notify(
            __app_name__,
            "Smart formatting is on: emails (Outlook…) come out professional, "
            "chats (Slack/Teams/WhatsApp…) stay casual, and terminals/code stay "
            "exactly as spoken. Clear it anytime from the tray.",
        )
        self._refresh()

    def _clear_modes_rules(self, *_args) -> None:
        self.cfg.set("text.modes.rules", [])
        self._save_config()
        self._notify(
            __app_name__,
            "Cleared your per-app rules. Terminals and code editors still stay as "
            "spoken; every other app uses your normal formatting.",
        )
        self._refresh()

    def _toggle_history(self, *_args) -> None:
        enabled = not bool(self.cfg.get("text.history.enabled", False))
        self.cfg.set("text.history.enabled", enabled)
        self._save_config()
        self._notify(
            __app_name__,
            "Saving your dictations locally on this PC — open or clear them from "
            "the tray. Nothing leaves your computer."
            if enabled
            else "Stopped saving dictation history.",
        )
        self._refresh()

    def _open_history(self, *_args) -> None:
        try:
            out = config_mod.config_dir() / "dictation_history.html"
            out.write_text(history.render_html(history.load()), encoding="utf-8")
            self._open_path(str(out))
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't open history: {exc}")

    def _clear_history(self, *_args) -> None:
        history.clear()
        try:
            (config_mod.config_dir() / "dictation_history.html").unlink()
        except Exception:
            pass
        self._notify(__app_name__, "Cleared your dictation history.")
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

    # -- updates & feedback --------------------------------------------
    def _startup_update_check(self) -> None:
        time.sleep(8)  # let everything settle before hitting the network
        try:
            from . import update_check

            info = update_check.check()
        except Exception:
            info = None
        if info and info.get("newer"):
            self._update_info = info
            self._notify(
                __app_name__,
                f"VibeFlow {info['version']} is available — open the tray menu to update.",
            )
            self._refresh()

    def _update_action(self, *_args) -> None:
        if self._update_info:
            self._apply_update()
        else:
            self._check_updates()

    def _check_updates(self, *_args) -> None:
        def work():
            try:
                from . import update_check

                info = update_check.check()
            except Exception:
                info = None
            if info is None:
                self._notify(__app_name__, "Couldn't check for updates (no internet?).")
            elif info.get("newer"):
                self._update_info = info
                self._notify(
                    __app_name__,
                    f"VibeFlow {info['version']} is available — choose “Install "
                    "update” in the tray menu.",
                )
            else:
                self._notify(__app_name__, f"You're on the latest version (v{__version__}).")
            self._refresh()

        threading.Thread(target=work, daemon=True).start()

    def _apply_update(self, *_args) -> None:
        info = self._update_info
        if not info:
            return self._check_updates()
        if not info.get("installer_url"):
            # The release asset may not have finished uploading at the last
            # check — re-check once before giving up to the browser.
            try:
                from . import update_check

                fresh = update_check.check()
                if fresh and fresh.get("installer_url"):
                    self._update_info = info = fresh
            except Exception:
                pass
        if not info.get("installer_url"):
            self._notify(
                __app_name__, "Update isn't downloadable yet — opening the release page."
            )
            self._open_path(info.get("page_url"))
            return

        def work():
            from . import update_check

            self._set_status("Downloading update…")
            self._refresh()
            path = update_check.download_installer(
                info["installer_url"],
                progress=lambda m: (self._set_status(m), self._refresh()),
            )
            if not path:
                self._notify(__app_name__, "Update download failed — opening the page.")
                self._open_path(info.get("page_url"))
                self._set_status("Ready")
                self._refresh()
                return
            self._notify(__app_name__, f"Installing VibeFlow {info['version']}…")
            update_check.run_installer(path)  # closes this instance & relaunches

        threading.Thread(target=work, daemon=True).start()

    def _copy_raw_transcript(self, *_args) -> None:
        """Put the last *unedited* transcript on the clipboard (recovery)."""
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to recover yet.")
            return
        try:
            import pyperclip

            pyperclip.copy(raw)
            self._notify(__app_name__, "Copied your last unedited transcript to the clipboard.")
        except Exception:
            pass

    def _reinsert_spoken(self, *_args) -> None:
        self._reinsert_last(cleaned=False)

    def _reinsert_cleaned(self, *_args) -> None:
        self._reinsert_last(cleaned=True)

    def _reinsert_last(self, cleaned: bool) -> None:
        """Re-deliver the last dictation with the other outcome — your recovery
        path when an app's automatic choice wasn't what you wanted (e.g. you
        dictated prose into an editor and want it cleaned up, or AI reworded a
        command and you want it exactly as spoken)."""
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to re-insert yet.")
            return
        threading.Thread(
            target=self._reinsert_worker, args=(raw, cleaned), daemon=True
        ).start()

    def _apply_outcome(self, raw: str, outcome: str) -> str:
        """Format ``raw`` per a per-app outcome (verbatim/professional/casual/
        default). Mirrors the formatting in :meth:`_process`."""
        if outcome == appmode.VERBATIM:
            return raw
        ai_on = ai_format.is_enabled(self.cfg)
        strip_fillers = bool(self.cfg.get("text.strip_fillers", False))
        text = curate(
            raw,
            spoken_commands=bool(self.cfg.get("text.spoken_commands", True)),
            capitalize_sentences=bool(self.cfg.get("text.capitalize_sentences", True)),
            strip_fillers=(strip_fillers and not ai_on),
            fillers=self.cfg.get("text.fillers", []) or None,
        )
        if ai_on:
            tone = {appmode.PROFESSIONAL: "professional",
                    appmode.CASUAL: "casual"}.get(outcome)
            persona_on = bool(self.cfg.get("text.persona", True))
            profile = self.persona.profile_text() if persona_on else None
            ai_text = ai_format.format_text(
                text, self.cfg, persona=profile, strip_fillers=strip_fillers, tone=tone
            )
            if ai_text:
                text = ai_text
        return text

    def _deliver_text(self, text: str) -> None:
        """Deliver already-formatted ``text`` to the focused field / clipboard."""
        try:
            text = expand_snippets(text, self.cfg.get("text.snippets", {}) or {})
        except Exception:  # pragma: no cover - never break delivery
            pass
        focus = detect_focus()
        result = deliver(
            text,
            output_mode=self.cfg.get("output.mode", "auto"),
            focus_state=focus,
            insertion=self.cfg.get("output.insertion", "paste"),
            trailing_space=bool(self.cfg.get("output.trailing_space", True)),
            auto_fallback=self.cfg.get("output.auto_fallback", "clipboard"),
        )
        if result == COPIED:
            self.overlay.show("clipboard")
            self._notify("Copied to clipboard", preview(text))
        else:
            self.overlay.show("done")

    def _reinsert_worker(self, raw: str, cleaned: bool) -> None:
        try:
            # The tray menu had focus; let Windows restore focus to your window.
            time.sleep(0.35)
            if cleaned:
                self.overlay.show("info", "VibeFlow · Cleaning up…")
                text = self._apply_outcome(raw, appmode.DEFAULT)
            else:
                self.overlay.show("info", "VibeFlow · Re-inserting as spoken…")
                text = raw
            self._deliver_text(text)
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't re-insert: {exc}")

    def _deliver_hotkey_fire(self) -> None:
        """Ctrl+Shift+V pressed while a dictation is pending on the clipboard →
        place it here, formatted for the focused app. Disarm immediately so a
        key-repeat or second press can't deliver twice."""
        if time.time() >= self._deliver_pending_until:
            return
        self._deliver_pending_until = 0.0
        self._reinsert_for_app()

    def _wait_keys_released(self, timeout: float = 1.5) -> None:
        """Block until Ctrl/Shift/Win are physically up (so a held delivery hotkey
        doesn't corrupt the paste). Returns immediately when nothing is held."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            get_state = ctypes.windll.user32.GetAsyncKeyState
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not any(
                    get_state(vk) & 0x8000 for vk in (0x11, 0x10, 0x5B, 0x5C)
                ):
                    return
                time.sleep(0.03)
        except Exception:
            pass

    def _reinsert_for_app(self, *_args) -> None:
        """Deliver the last dictation formatted for whatever app you're now in —
        dictate anywhere, then place it where it belongs. Reached from the tray
        and from the Ctrl+Shift+V delivery hotkey."""
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to deliver yet.")
            return
        threading.Thread(
            target=self._reinsert_for_app_worker, args=(raw,), daemon=True
        ).start()

    def _reinsert_for_app_worker(self, raw: str) -> None:
        try:
            # Wait for any held modifier (e.g. the Ctrl+Shift of the delivery
            # hotkey) to lift so it can't corrupt the paste, then let focus settle.
            self._wait_keys_released()
            time.sleep(0.2)
            outcome = appmode.DEFAULT
            name = None
            try:
                app_id = appmode.target_app(appmode.foreground_hwnd())
                outcome = appmode.resolve_outcome(
                    app_id, self.cfg.get("text.modes.rules", []) or []
                )
                name = app_id.friendly
            except Exception:
                outcome = appmode.DEFAULT
            if outcome != appmode.VERBATIM and ai_format.is_enabled(self.cfg) and name:
                self.overlay.show("info", f"VibeFlow · Restructuring for {name}…")
            elif name:
                self.overlay.show("info", f"VibeFlow · Delivering — {name}")
            self._deliver_text(self._apply_outcome(raw, outcome))
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't deliver: {exc}")

    def _report_problem(self, *_args) -> None:
        # Open the folder containing vibeflow.log, plus the issues page.
        self._open_path(str(config_mod.config_dir()))
        self._open_path("https://github.com/vamsikrishna2421/vibeflow/issues")
        self._notify(
            __app_name__,
            "Opened your VibeFlow folder — please attach 'vibeflow.log' to your report.",
        )

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

    def _maybe_reload_license(self) -> None:
        """Re-evaluate the license if license.key changed (activated in the window)."""
        try:
            lic = config_mod.config_dir() / licensing.LICENSE_FILENAME
            mtime = lic.stat().st_mtime if lic.exists() else 0.0
        except Exception:
            return
        if mtime != self._license_mtime:
            self._license_mtime = mtime
            new = licensing.evaluate(config_mod.config_dir())
            if new.is_paid and not self._license.is_paid:
                self._license_nudged = False
                self._notify(__app_name__, f"Activated — {new.badge}. AI formatting unlocked.")
            self._license = new
            if self.icon is not None:
                try: self.icon.update_menu()
                except Exception: pass

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
        threading.Thread(
            target=self._setup_learning_worker, args=(self._learning_model(),), daemon=True
        ).start()

    def _learning_model(self) -> str:
        """Model for adaptive (AI) term learning: reuse the user's chosen AI
        formatting model so enabling learning never forces a bigger download than
        they picked; fall back to the smallest tier — never a hardcoded 3b."""
        chosen = str(self.cfg.get("ai.model", "") or "").strip()
        return chosen or "qwen2.5:1.5b"

    def _setup_learning_worker(self, model: str) -> None:
        def progress(message: str) -> None:
            self._set_status(message)
            self._refresh()

        # Honest disclosure (off the UI thread): only promise a download when the
        # chosen model isn't already installed — reusing it costs nothing.
        if ai_setup.is_installed() and ai_setup.has_model(model):
            self._notify(
                __app_name__,
                f"Turning on adaptive learning — reusing your installed model "
                f"({model}), no download. Uses ~2 GB RAM only while learning.",
            )
        else:
            size = next(
                (s for _t, (m, s) in ai_setup.MODEL_TIERS.items() if m == model), ""
            )
            self._notify(
                __app_name__,
                f"Setting up adaptive learning ({model}"
                + (f", one-time ~{size} download" if size else "")
                + "). Uses ~2 GB RAM only while learning (freed when idle). "
                "Watch the tray tooltip for progress.",
            )

        ok, message = ai_setup.setup(model, progress=progress)
        if ok:
            self.cfg.set("text.ai_learning", True)
            self.cfg.set("text.teach_back", True)  # learning rides on teach-back
            self.cfg.set("text.teach_back_model", model)
            self._record_pulled_model(model)
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
                    threading.Thread(
                        target=self._setup_learning_worker,
                        args=(self._learning_model(),), daemon=True,
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
        threading.Thread(
            target=self._setup_ai_worker, args=(model, size), daemon=True
        ).start()

    def _setup_ai_worker(self, model: str, size: str = "") -> None:
        def progress(message: str) -> None:
            self._set_status(message)
            self._refresh()

        # Be honest up front: only promise a download when something is actually
        # missing. Switching to an already-installed model is near-instant, so
        # don't claim "I'll download everything (N GB)". The check hits Ollama's
        # local API, so it runs here on the worker thread, not the UI thread.
        if ai_setup.is_installed() and ai_setup.has_model(model):
            self._notify(
                __app_name__, f"Switching AI formatting to {model} (already installed)…"
            )
        else:
            self._notify(
                __app_name__,
                f"Setting up AI ({model}, {size}). I'll install the runtime and "
                "download the model automatically — watch the tray tooltip for progress.",
            )

        ok, message = ai_setup.setup(model, progress=progress)
        logging.getLogger("vibeflow").info(
            "AI setup: model=%s ok=%s msg=%s", model, ok, message
        )
        if ok:
            self.cfg.set("ai.enabled", True)
            self.cfg.set("ai.model", model)
            self._record_pulled_model(model)
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
            if self._delivery_hotkey:
                self._delivery_hotkey.stop()
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

    def _maybe_reload_config(self) -> None:
        """Pick up edits made by the Settings window (a separate process writing
        config.yaml) and apply them live, without a restart."""
        try:
            mtime = config_mod.config_path().stat().st_mtime
        except OSError:
            return
        if self._cfg_mtime is None:
            self._cfg_mtime = mtime
            return
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime
        try:
            self.cfg.data = config_mod.load_config().data
            # Most settings are read fresh from cfg each dictation, so they take
            # effect immediately. Language is cached on the transcriber — re-apply
            # (the transcriber sanitises unknown values to English).
            try:
                self.transcriber.language = self.cfg.get("model.language", "en")
            except Exception:
                pass
            # Apply a microphone change (Settings → Microphone) live. The recorder
            # opens a fresh stream each recording and resolves the device then, so
            # storing the raw config value (e.g. "auto") is enough.
            try:
                self.recorder.input_device = self.cfg.get("audio.input_device", "auto")
            except Exception:
                pass
            logging.getLogger("vibeflow").info("settings reloaded from disk")
            self._refresh()
        except Exception:  # pragma: no cover - never break on a bad reload
            pass

    def _open_settings(self, *_args) -> None:
        if not self._launch_manager("--settings"):
            self._notify(__app_name__, "Couldn't open Settings. Edit config.yaml via "
                         "“Report a problem…” instead.")

    def _open_models_manager(self, *_args) -> None:
        if not self._launch_manager("--models-manager"):
            self._notify(__app_name__, "Couldn't open the AI model manager.")

    def _record_pulled_model(self, model: str) -> None:
        """Remember a model VibeFlow downloaded, so the model manager can show
        which models are ours vs. ones you installed in Ollama yourself."""
        try:
            pulled = list(self.cfg.get("ai.pulled_models", []) or [])
            if model and model not in pulled:
                pulled.append(model)
                self.cfg.set("ai.pulled_models", pulled)
        except Exception:
            pass

    def _save_config(self) -> None:
        try:
            self.cfg.save()
            try:  # remember our own write so the watcher doesn't re-load it
                self._cfg_mtime = config_mod.config_path().stat().st_mtime
            except OSError:
                pass
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
