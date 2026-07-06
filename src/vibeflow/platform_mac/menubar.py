"""macOS menu-bar app — rumps NSStatusItem + the core dictation pipeline.

The Mac counterpart to the Windows ``app.py`` tray app. It keeps the *exact*
``_process`` flow (transcribe → curate → per-app outcome → snippets → deliver →
history → teach-back) and swaps the Windows "hands" for Mac ones (focus via the
Accessibility API, paste via Cmd+V, frontmost-app identity via NSWorkspace).

UI threading rule: rumps owns the main thread. All heavy work (model load,
transcription, AI) runs on worker threads that only *write* small shared state;
a single short ``rumps.Timer`` pushes that state onto the menu bar, so no AppKit
object is ever touched from a background thread.
"""

from __future__ import annotations

import difflib
import json
import logging
import threading
import time

from .. import __app_name__, __version__, ai_setup, config as config_mod, licensing
from ..audio import AudioError, Recorder, is_silent, peak_level
from ..core import ai_format, appmode
from ..core.curate import curate
from ..core.persona import Persona
from ..core.text import clean_transcript, expand_snippets, preview
from ..core.vocabulary import Vocabulary
from ..core import history
from ..transcriber import Transcriber, TranscriptionError
from . import appdetect, autostart, catalog, defaults, permissions, singleinstance, updater
from .focus_detect import detect_focus
from .hotkey import MacHotkeys
from .output import COPIED, deliver
from .overlay import StatusOverlay

log = logging.getLogger("vibeflow")

# Menu-bar glyphs for each state (the textual status lives in the first menu row).
_GLYPHS = {"idle": "🎙", "recording": "🔴", "busy": "🟠"}


class MenuBarApp:
    """Owns Mac app state and the rumps menu-bar UI."""

    def __init__(self, cfg: config_mod.Config) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._recording = False
        self._busy = False
        self._model_ready = False
        self._stopping = False
        self._stream_session = None          # active streaming session, if any
        self._offline_dl = False             # offline-model download in progress
        self._license = licensing.evaluate(config_mod.config_dir())
        self._empty_streak = 0               # consecutive silent/no-speech (mic-trouble detector)

        self._status = "Starting…"
        self._state = "idle"
        self._last_raw_transcript = ""
        self._last_output = None
        self._last_output_ts = 0.0
        self._clip_last = None
        self._expected_pid = 0
        self._cfg_mtime = None
        self._deliver_pending_until = 0.0  # arms the Cmd+Shift+V delivery hotkey
        self._notify_queue: list = []       # drained on the main thread by the timer
        self._notify_lock = threading.Lock()
        self._listeners_started = False
        self._lock_handle = None             # single-instance lock
        self._record_started_ts = 0.0        # for the max-duration watchdog
        self._busy_deadline = 0.0            # abandon a hung transcription past this
        self._ax_ok_last = None              # tracks Accessibility-grant transitions
        self._update_info = None             # set when a newer GitHub release is found
        self._icon_paths = None              # state -> menu-bar logo PNG path
        self._icon_state_last = None

        # On-screen status pill (rendered on the main thread by the timer).
        self.overlay = StatusOverlay(enabled=bool(self.cfg.get("feedback.overlay", True)))
        self._overlay_text = ""
        self._overlay_until = 0.0            # 0 = hidden, inf = until replaced

        self.recorder = self._build_recorder()
        self.transcriber = self._build_transcriber()
        self.hotkeys = self._build_hotkeys()
        self.vocabulary = self._build_vocabulary()
        self.persona = self._build_persona()
        self._app = None  # the rumps.App, created in run()
        self._items: dict = {}  # MenuItems we refresh checkmarks on

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
            language=self.cfg.get("model.language", "en"),
            device=self.cfg.get("model.device", "auto"),
            compute_type=self.cfg.get("model.compute_type", "auto"),
            models_dir=str(config_mod.models_dir()),
        )

    def _build_hotkeys(self) -> MacHotkeys:
        return MacHotkeys(
            push_to_talk_key=self.cfg.get("hotkey.push_to_talk_key", "cmd_r"),
            on_start=self.start_recording,
            on_stop=self.stop_recording,
            deliver_is_armed=lambda: time.time() < self._deliver_pending_until,
            deliver_on_fire=self._deliver_hotkey_fire,
        )

    def _build_vocabulary(self) -> Vocabulary:
        return Vocabulary(
            path=config_mod.config_dir() / "vocabulary.json",
            seed=self.cfg.get("text.vocabulary", []) or [],
        )

    def _build_persona(self) -> Persona:
        return Persona(path=config_mod.config_dir() / "persona.json")

    # ------------------------------------------------------------------
    # Recording lifecycle (called from the pynput listener thread)
    # ------------------------------------------------------------------
    def start_recording(self) -> None:
        # License gate: after the 14-day trial, the whole app is locked until this
        # Mac is activated. Re-evaluate each time so expiry / activation take effect.
        self._license = licensing.evaluate(config_mod.config_dir())
        if not self._license.tool_unlocked:
            self.hotkeys.reset()
            self._notify(
                __app_name__,
                "Your free trial has ended. Open the VibeFlow menu → “Activate” to "
                "unlock this Mac ($10 once, lifetime).",
            )
            return
        with self._lock:
            if self._recording or self._busy:
                self.hotkeys.reset()
                return
            # Set the watchdog clock BEFORE flipping _recording, so the timer can
            # never see _recording=True with a stale (0.0) start time and stop the
            # very first recording instantly.
            self._record_started_ts = time.time()
            self._recording = True
        try:
            self.recorder.start()
        except AudioError as exc:
            with self._lock:
                self._recording = False
            self.hotkeys.reset()
            self._set("idle", "Microphone error")
            self._overlay_flash("⚠️ Microphone error")
            self._notify("Microphone error", str(exc))
            return

        # Streaming (default): transcribe WHILE speaking so the paste is near-instant
        # on release. Whisper engine only; any failure falls back to batch.
        self._stream_session = None
        try:
            if bool(self.cfg.get("model.streaming", True)) and \
                    getattr(self.transcriber, "engine", "whisper") == "whisper":
                from ..streaming import StreamingSession
                self._stream_session = StreamingSession(
                    self.transcriber, self.recorder, prompt=self.vocabulary.prompt()
                )
                self._stream_session.start()
        except Exception as exc:
            self._stream_session = None
            log.info("streaming start failed (%s); using batch", exc)

        self._set("recording", "Listening…")
        self._overlay_persist("🎙 Listening…")

    def stop_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            self._busy = True
        # Remember the app that had focus while talking, so we don't paste into
        # the wrong window if focus moves during transcription.
        self._expected_pid = appdetect.frontmost_pid()
        audio = self.recorder.stop()
        # Generous deadline (scaled to clip length) after which a transcription is
        # presumed hung and abandoned, so the app can never stay stuck "busy".
        dur = self.recorder.duration(audio)
        self._busy_deadline = time.time() + max(60.0, dur * 3.0)
        self._set("busy", "Transcribing…")
        self._overlay_persist("✍️ Transcribing…")
        session = getattr(self, "_stream_session", None)
        self._stream_session = None
        if session is not None:
            threading.Thread(
                target=self._process_streamed, args=(session, audio), daemon=True
            ).start()
        else:
            threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    # ------------------------------------------------------------------
    # The pipeline (worker thread) — mirrors app.py:_process
    # ------------------------------------------------------------------
    def _process_streamed(self, session, audio) -> None:
        """Deliver a streamed transcript; fall back to batch on failure or if the
        result looks implausibly short (streaming fell behind → never ship a cut-off)."""
        text = None
        try:
            text = session.finalize(audio)  # full recording — the live buffer is cleared
        except Exception as exc:
            log.info("streaming failed (%s); falling back to batch transcribe", exc)
        secs = self.recorder.duration(audio)
        if text and len(text.strip()) >= max(12, secs * 6):
            self._process(audio, text=text)
        else:
            self._process(audio)

    def _process(self, audio, text=None) -> None:
        try:
            seconds = self.recorder.duration(audio)
            if seconds < float(self.cfg.get("audio.min_seconds", 0.4)):
                self._overlay_flash("Too short — ignored")
                self._notify(__app_name__, "Recording too short — ignored.")
                return

            if text is None:  # streaming may have already transcribed during speech
                log.info("transcribing %.1fs of audio", seconds)
                text = self.transcriber.transcribe(audio, prompt=self.vocabulary.prompt())
                self._model_ready = True
            if bool(self.cfg.get("text.debug_log", False)):
                log.info("debug raw transcript: %r", (text or "")[:240])
            text = clean_transcript(
                text,
                strip=bool(self.cfg.get("text.strip", True)),
                capitalize_first=bool(self.cfg.get("text.capitalize_first", False)),
                remove_trailing_period=bool(
                    self.cfg.get("text.remove_trailing_period", False)
                ),
            )
            if not text:
                # Work out WHY nothing came back so the message is actionable. The
                # common trap is a muted/blocked/wrong mic handing a silent-or-quiet
                # stream (no error) — peak_level tells that apart from real no-speech.
                peak = peak_level(audio)
                self._empty_streak += 1
                quiet = is_silent(audio) or peak < 0.02  # real speech peaks ~0.1+
                if is_silent(audio):
                    self._overlay_flash("No sound from mic")
                    reason = ("No sound from the microphone. Check the right mic is "
                              "selected and not muted, and that VibeFlow has Microphone "
                              "permission.")
                elif quiet:
                    self._overlay_flash("Mic level very low")
                    reason = ("VibeFlow is barely hearing you — the input level is very "
                              "low. Check the mic isn't muted and VibeFlow has Microphone "
                              "permission.")
                else:
                    self._overlay_flash("No speech detected")
                    reason = "No speech detected — try speaking a bit louder or closer to the mic."
                # Two silent/quiet captures in a row is almost never the user — it's a
                # permission/selection problem. Say so and open the mic settings pane.
                if quiet and self._empty_streak >= 2:
                    self._notify(__app_name__, reason + " Opening Microphone settings…")
                    try:
                        permissions.open_pane("Microphone")
                    except Exception:
                        pass
                else:
                    self._notify(__app_name__, reason)
                return
            self._empty_streak = 0  # a real transcript came through — mic is working
            self._last_raw_transcript = text.strip()

            strip_fillers = bool(self.cfg.get("text.strip_fillers", False))
            ai_on = ai_format.is_enabled(self.cfg)
            persona_on = bool(self.cfg.get("text.persona", True))

            # Per-app formatting: resolve the destination app's outcome (Mac
            # detection + catalog). Fail-safe: any error falls back to DEFAULT.
            outcome = appmode.DEFAULT
            target_name = None
            target_exe = ""
            try:
                if bool(self.cfg.get("text.modes.enabled", True)):
                    app_id, target_name, _pid = appdetect.identify()
                    outcome = catalog.resolve_outcome(
                        app_id, self.cfg.get("text.modes.rules", []) or []
                    )
                    target_exe = app_id.exe
            except Exception:  # pragma: no cover - never break dictation
                outcome = appmode.DEFAULT

            if outcome == appmode.VERBATIM:
                text = self._last_raw_transcript
                if target_name:
                    self._set("busy", f"As spoken — {target_name}")
                    self._overlay_persist(f"As spoken — {target_name}")
            else:
                text = curate(
                    text,
                    spoken_commands=bool(self.cfg.get("text.spoken_commands", True)),
                    capitalize_sentences=bool(
                        self.cfg.get("text.capitalize_sentences", True)
                    ),
                    strip_fillers=True,  # always: deterministic filler removal is a default cleanup layer
                    fillers=self.cfg.get("text.fillers", []) or None,
                )
                tone = {appmode.PROFESSIONAL: "professional",
                        appmode.CASUAL: "casual",
                        appmode.EMAIL: "email"}.get(outcome)
                if ai_on:
                    if target_name:
                        self._set("busy", f"Restructuring for {target_name}…")
                        self._overlay_persist(f"Restructuring for {target_name}…")
                    profile = self.persona.profile_text() if persona_on else None
                    if self.cfg.get("ai.provider", "ollama") == "builtin":
                        # "Offline — no Ollama" tier: clean up with the built-in local LLM.
                        from ..core import offline_cleanup
                        ai_text = offline_cleanup.format_text(text, self.cfg, persona=profile)
                    else:
                        ai_text = ai_format.format_text(
                            text, self.cfg, persona=profile,
                            strip_fillers=False, tone=tone,
                        )
                    if ai_text:
                        text = ai_text

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
                expected_pid=self._expected_pid,
            )
            self._last_output = text.strip()
            self._last_output_ts = time.time()
            log.info("delivered: focus=%s result=%s chars=%d", focus, result, len(text))

            # Optional local dictation history (opt-in; never breaks delivery).
            try:
                if bool(self.cfg.get("text.history.enabled", False)):
                    history.append(
                        text, target_name or "",
                        max_entries=int(self.cfg.get("text.history.max", 500) or 500),
                    )
            except Exception:  # pragma: no cover - never break dictation
                pass

            # One-time, in-context Starter Pack offer the first time you dictate
            # into a known email/chat app.
            try:
                if (
                    target_exe
                    and catalog.app_category(target_exe)
                    and not bool(self.cfg.get("text.modes.starter_pack_offered", False))
                ):
                    self.cfg.set("text.modes.starter_pack_offered", True)
                    self._save_config()
                    self._notify(
                        __app_name__,
                        "Tip: VibeFlow can format for each app automatically — "
                        "professional in email, casual in chat. Turn it on from the "
                        "menu: Adapt formatting to each app → Set up smart formatting.",
                    )
            except Exception:  # pragma: no cover - never break dictation
                pass

            # Persona profiling (opt-in): capped local sample → periodic profile.
            if persona_on and self.persona.add_sample(text):
                self.persona.save()
                if self.persona.needs_profile():
                    threading.Thread(target=self._profile_worker, daemon=True).start()

            if result == COPIED:
                # No field was focused — the text is on the clipboard. Arm the
                # "deliver here" hotkey: click into any app within the timeout and
                # press Cmd+Shift+V to place it, formatted for that app.
                if self.cfg.get("text.modes.deliver_hotkey"):
                    self._deliver_pending_until = time.time() + float(
                        self.cfg.get("text.modes.pending_timeout", 60) or 60
                    )
                    self._overlay_flash("📋 Copied — press ⌘⇧V to place", ttl=6.0)
                    self._notify(
                        "Dictation ready",
                        "On your clipboard. Click into any app and press "
                        "Cmd+Shift+V to place it, formatted for that app.",
                    )
                else:
                    self._overlay_flash("📋 Copied to clipboard")
                    self._notify("Copied to clipboard", preview(text))
            else:
                self._overlay_flash("✓ Inserted")
        except TranscriptionError as exc:
            self._overlay_flash("⚠️ Transcription error")
            self._notify("Transcription error", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("pipeline error")
            self._overlay_flash("⚠️ Something went wrong")
            self._notify("Unexpected error", str(exc))
        finally:
            with self._lock:
                self._busy = False
            self._busy_deadline = 0.0
            self.hotkeys.reset()
            self._set("idle", "Ready")
            # If a persistent overlay (Listening/Transcribing) was never replaced
            # by a flash (e.g. an early return), clear it so it doesn't linger.
            if self._overlay_until == float("inf"):
                self._overlay_clear()

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
            self._maybe_reload_config()
            self.vocabulary.reload_if_changed()
            self.persona.reload_if_changed()
            if not bool(self.cfg.get("text.teach_back", True)):
                continue
            try:
                clip = pyperclip.paste()
            except Exception:
                continue
            if not isinstance(clip, str) or clip == self._clip_last:
                continue
            self._clip_last = clip
            self._maybe_learn_from_clip(clip)

    def _maybe_learn_from_clip(self, clip: str) -> None:
        out = self._last_output
        if not out or not clip:
            return
        clip = clip.strip()
        if not clip or clip == out.strip():
            return
        if time.time() - self._last_output_ts > 600:
            return
        if not (2 <= len(clip) <= 5000):
            return
        ratio = difflib.SequenceMatcher(None, out, clip).ratio()
        if not (0.5 <= ratio < 0.999):
            return

        learned: list = []
        terms = None
        if bool(self.cfg.get("text.ai_learning", False)):
            self._set(self._state, "Learning your terms…")
            try:
                terms = ai_format.extract_terms(clip, self.cfg)
            except Exception:
                terms = None
            if terms:
                learned += self.vocabulary.learn_terms(terms)
        learned += self.vocabulary.learn_from_correction(out, clip)
        learned = list(dict.fromkeys(learned))
        if learned:
            self._last_output = None
            self.vocabulary.save()
            shown = ", ".join(learned[:6])
            self._notify(__app_name__, "Learned from your edit: " + shown)

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
            self._notify(__app_name__, "Updated your writing profile from recent dictation.")

    # ------------------------------------------------------------------
    # Model preload
    # ------------------------------------------------------------------
    def _preload_model(self) -> None:
        try:
            self._set("idle", "Loading model…")
            self.transcriber.load()
            self._model_ready = True
            self._set("idle", "Ready")
            log.info("model ready: %s %s", self.cfg.get("model.size"),
                     self.transcriber._resolved)
            self._notify(__app_name__, f"Ready. {self._trigger_hint()} to dictate.")
        except Exception as exc:
            self._set("idle", "Model failed to load")
            self._notify("Could not load speech model", str(exc))

    # ------------------------------------------------------------------
    # rumps UI
    # ------------------------------------------------------------------
    def run(self) -> None:
        import rumps

        # Single-instance: refuse to start a second copy (it would grab the
        # hotkey and double-process every dictation).
        self._lock_handle = singleinstance.acquire()
        if self._lock_handle is None:
            log.info("another VibeFlow instance is already running — exiting")
            return

        rumps.debug_mode(False)
        # Branded menu-bar icon: the VibeFlow logo with a status dot (recording/
        # busy), falling back to a text glyph if icon rendering isn't available.
        self._icon_paths = self._ensure_menu_icons()
        if self._icon_paths:
            self._app = rumps.App(__app_name__, icon=self._icon_paths["idle"],
                                  template=False, quit_button=None)
        else:
            self._app = rumps.App(__app_name__, title=_GLYPHS["idle"], quit_button=None)
        self._app.menu = self._build_menu(rumps)

        # Background workers that touch no AppKit/TSM state can start now.
        threading.Thread(target=self._preload_model, daemon=True).start()
        threading.Thread(target=self._clip_watch_loop, daemon=True).start()
        threading.Thread(target=self._first_run_permissions, daemon=True).start()
        threading.Thread(target=self._startup_update_check, daemon=True).start()

        # The keyboard listener (a CGEventTap on its own run loop) is started from
        # the first timer tick — i.e. AFTER NSApplication's main loop is up — so
        # the main thread initialises the Text Services Manager first. Starting it
        # before app.run() races TSM init across threads and aborts HIToolbox.
        self._ui_timer = rumps.Timer(self._sync_ui, 0.3)
        self._ui_timer.start()
        self._app.run()

    def _ensure_menu_icons(self):
        """Render the VibeFlow logo (with a per-state status dot) to PNGs for the
        menu bar. Returns ``{state: path}`` or ``None`` if rendering isn't possible."""
        try:
            from .. import icons

            d = config_mod.config_dir() / "menubar_icons"
            d.mkdir(parents=True, exist_ok=True)
            paths = {}
            for state in ("idle", "recording", "busy"):
                p = d / f"{state}.png"
                icons.make_tray_image(state, size=36).save(str(p))
                paths[state] = str(p)
            return paths
        except Exception:  # pragma: no cover - branding is best-effort
            log.debug("menu-bar icon render failed", exc_info=True)
            return None

    def _start_listeners_once(self) -> None:
        if self._listeners_started:
            return
        self._listeners_started = True
        # Ask for the mic up front so the prompt never appears mid-dictation
        # (where it would swallow the push-to-talk key-release).
        try:
            permissions.request_microphone()
        except Exception:
            pass
        try:
            self.hotkeys.start()
        except Exception:  # pragma: no cover - never break the UI loop
            log.exception("hotkey listener failed to start")

    def _reconcile_accessibility(self) -> None:
        """When Accessibility is granted, (re)start the keyboard listener so its
        event tap is created *trusted* — no app restart needed. This is what makes
        setup finish the moment the user flips the toggle."""
        ok = permissions.accessibility_ok()
        if self._ax_ok_last is None:
            self._ax_ok_last = ok
            return
        if ok and not self._ax_ok_last:
            log.info("accessibility granted — (re)starting hotkey listener")
            try:
                self.hotkeys.stop()
            except Exception:
                pass
            try:
                self.hotkeys.start()
            except Exception:
                pass
            self._overlay_flash("✓ Setup complete — hold Right ⌘ to talk", ttl=5.0)
            self._notify(__app_name__, "Setup complete — hold Right ⌘ and speak.")
        self._ax_ok_last = ok

    def _recording_watchdog(self) -> None:
        """Safety nets so the app can never stick: stop an over-long recording,
        and abandon a transcription that has hung past its deadline."""
        if self._recording:
            max_seconds = float(self.cfg.get("audio.max_seconds", 120) or 120)
            if time.time() - self._record_started_ts > max_seconds:
                log.info("recording watchdog: stopping after %.0fs", max_seconds)
                self.hotkeys.reset()
                self.stop_recording()
            return
        # Not recording but stuck "busy" past the deadline → a hung transcription.
        if self._busy and self._busy_deadline and time.time() > self._busy_deadline:
            log.warning("processing watchdog: abandoning a stuck transcription")
            with self._lock:
                self._busy = False
            self._busy_deadline = 0.0
            self.hotkeys.reset()
            self._overlay_flash("⚠️ Transcription timed out — try again")
            self._set("idle", "Ready")

    def _mi(self, rumps, key, title, callback=None):
        """Make a MenuItem, remember it under ``key`` for later state refresh."""
        item = rumps.MenuItem(title, callback=callback)
        self._items[key] = item
        return item

    def _build_menu(self, rumps):
        self._items.clear()
        return [
            self._mi(rumps, "status", self._status),
            self._mi(rumps, "hint", f"Hold {self._hotkey_label()} to talk"),
            None,
            ("Output", [
                self._mi(rumps, "out_auto", "Auto (type or clipboard)",
                         lambda s: self._set_output("auto")),
                self._mi(rumps, "out_type", "Always type",
                         lambda s: self._set_output("type")),
                self._mi(rumps, "out_clip", "Always clipboard",
                         lambda s: self._set_output("clipboard")),
            ]),
            ("Speech accuracy", [
                self._mi(rumps, "acc_small", "Fast (small)",
                         lambda s: self._set_accuracy("small")),
                self._mi(rumps, "acc_medium", "Accurate (medium · recommended)",
                         lambda s: self._set_accuracy("medium")),
            ]),
            ("AI formatting", [
                self._mi(rumps, "ai_off", "Off (plain voice-to-text)",
                         lambda s: self._set_ai_model("off")),
                self._mi(rumps, "ai_fast", "Fast — qwen2.5:1.5b",
                         lambda s: self._set_ai_model("fast")),
                self._mi(rumps, "ai_balanced", "Balanced — qwen2.5:3b (recommended)",
                         lambda s: self._set_ai_model("balanced")),
                self._mi(rumps, "ai_best", "Best — gemma2:2b",
                         lambda s: self._set_ai_model("best")),
                None,
                self._mi(rumps, "ai_offline", "Offline — no Ollama (built-in 3B · ~2 GB)",
                         lambda s: self._set_ai_model("offline")),
            ]),
            ("Adapt formatting to each app", [
                self._mi(rumps, "modes_enabled", "Enabled", self._toggle_modes),
                None,
                self._mi(rumps, "starter", "Set up smart formatting (1-click)",
                         self._setup_starter_pack),
                self._mi(rumps, "clear_rules", "Clear my app rules",
                         self._clear_modes_rules),
            ]),
            self._mi(rumps, "teachback", "Learn from my edits", self._toggle_teachback),
            self._mi(rumps, "ai_learning", "Adaptive learning (AI)",
                     self._toggle_ai_learning),
            self._mi(rumps, "vocab",
                     f"My vocabulary ({len(self.vocabulary.terms)} words)…",
                     self._open_vocabulary),
            ("Personalized AI", [
                self._mi(rumps, "persona", "Match my writing style",
                         self._toggle_persona),
                self._mi(rumps, "persona_view", "View my profile…", self._open_persona),
                self._mi(rumps, "persona_forget", "Forget my writing style",
                         self._forget_persona),
            ]),
            ("Dictation history", [
                self._mi(rumps, "hist_save", "Save my dictations (local)",
                         self._toggle_history),
                self._mi(rumps, "hist_open", "Open history…", self._open_history),
                self._mi(rumps, "hist_clear", "Clear history", self._clear_history),
            ]),
            None,
            self._mi(rumps, "copy_raw", "Copy last transcript (unedited)",
                     self._copy_raw_transcript),
            ("Re-insert last dictation", [
                self._mi(rumps, "re_spoken", "Exactly as spoken",
                         self._reinsert_spoken),
                self._mi(rumps, "re_cleaned", "Cleaned up", self._reinsert_cleaned),
                self._mi(rumps, "re_app", "Formatted for this app",
                         self._reinsert_for_app),
            ]),
            None,
            self._mi(rumps, "perms", "Set Up VibeFlow (permissions)…",
                     self._open_permissions),
            self._mi(rumps, "open_cfg", "Open settings file", self._open_config),
            self._mi(rumps, "open_dir", "Open settings folder", self._open_config_dir),
            self._mi(rumps, "reload", "Reload settings", self._reload),
            self._mi(rumps, "overlay", "Show on-screen status", self._toggle_overlay),
            self._mi(rumps, "start_login", "Start at login", self._toggle_autostart),
            self._mi(rumps, "debug_log", "Detailed logging (troubleshooting)",
                     self._toggle_debug_log),
            None,
            self._mi(rumps, "license", "Activate / License…", self._activate_license),
            self._mi(rumps, "update", "Check for updates…", self._open_update_dialog),
            self._mi(rumps, "about", f"About {__app_name__} {__version__}", self._about),
            self._mi(rumps, "quit", "Quit", self._quit),
        ]

    def _sync_ui(self, _timer=None) -> None:
        """Main-thread heartbeat: start the listener once the app loop is up,
        deliver queued notifications, and push state + checkmarks to the menu."""
        try:
            self._start_listeners_once()  # safe: now on the main thread, NSApp up
            self._reconcile_accessibility()
            self._recording_watchdog()
            self._drain_notifications()
            self._check_update_marker()
            self._render_overlay()
            # Reflect state on the menu bar: swap the branded logo icon (or fall
            # back to a text glyph). Only update on change to avoid flicker.
            if self._icon_paths:
                if self._icon_state_last != self._state:
                    try:
                        self._app.icon = self._icon_paths.get(
                            self._state, self._icon_paths["idle"]
                        )
                    except Exception:
                        pass
                    self._icon_state_last = self._state
            else:
                self._app.title = _GLYPHS.get(self._state, _GLYPHS["idle"])
            self._set_item_title("status", self._status)
            self._set_item_title("hint", f"Hold {self._hotkey_label()} to talk")
            self._set_item_title(
                "vocab", f"My vocabulary ({len(self.vocabulary.terms)} words)…"
            )
            self._set_item_title(
                "update",
                f"⬆ Install update ({self._update_info['version']})"
                if self._update_info else "Check for updates",
            )
            self._refresh_states()
        except Exception:  # pragma: no cover - never let the timer die
            pass

    # -- on-screen overlay (state written from any thread; rendered here) --
    def _overlay_persist(self, text: str) -> None:
        self._overlay_text = text
        self._overlay_until = float("inf")

    def _overlay_flash(self, text: str, ttl: float = 2.5) -> None:
        self._overlay_text = text
        self._overlay_until = time.time() + ttl

    def _overlay_clear(self) -> None:
        self._overlay_until = 0.0

    def _render_overlay(self) -> None:
        """Show/hide the status pill on the main thread per the latest state."""
        self.overlay.set_enabled(bool(self.cfg.get("feedback.overlay", True)))
        if self._overlay_text and time.time() < self._overlay_until:
            self.overlay.show(self._overlay_text)
        else:
            self.overlay.hide()

    def _drain_notifications(self) -> None:
        """Show queued notifications on the main thread (Cocoa requires it)."""
        with self._notify_lock:
            pending = self._notify_queue
            self._notify_queue = []
        if not pending:
            return
        try:
            import rumps
            for title, message in pending:
                rumps.notification(title, "", message)
        except Exception:  # pragma: no cover - notifications best-effort
            log.debug("notification failed", exc_info=True)

    def _set_item_title(self, key: str, title: str) -> None:
        item = self._items.get(key)
        if item is not None and item.title != title:
            item.title = title

    def _check(self, key: str, on: bool) -> None:
        item = self._items.get(key)
        if item is not None:
            item.state = 1 if on else 0

    def _refresh_states(self) -> None:
        mode = self.cfg.get("output.mode")
        self._check("out_auto", mode == "auto")
        self._check("out_type", mode == "type")
        self._check("out_clip", mode == "clipboard")

        size = self.cfg.get("model.size")
        self._check("acc_small", size == "small")
        self._check("acc_medium", size == "medium")

        tier = self._ai_tier()
        self._check("ai_off", not bool(self.cfg.get("ai.enabled", False)))
        self._check("ai_fast", tier == "fast")
        self._check("ai_balanced", tier == "balanced")
        self._check("ai_best", tier == "best")
        self._check("ai_offline", tier == "offline")

        self._check("modes_enabled", bool(self.cfg.get("text.modes.enabled", True)))
        self._check("teachback", bool(self.cfg.get("text.teach_back", True)))
        self._check("ai_learning", bool(self.cfg.get("text.ai_learning", False)))
        self._check("persona", bool(self.cfg.get("text.persona", True)))
        self._check("hist_save", bool(self.cfg.get("text.history.enabled", False)))
        self._check("overlay", bool(self.cfg.get("feedback.overlay", True)))
        self._check("debug_log", bool(self.cfg.get("text.debug_log", False)))
        try:
            self._check("start_login", autostart.is_enabled())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Menu actions — output / accuracy / AI
    # ------------------------------------------------------------------
    def _set_output(self, mode: str) -> None:
        self.cfg.set("output.mode", mode)
        self._save_config()
        self._notify(__app_name__, f"Output set to '{mode}'.")

    def _set_accuracy(self, size: str) -> None:
        self.cfg.set("model.size", size)
        self._save_config()
        self.transcriber = self._build_transcriber()
        self._model_ready = False
        labels = {"small": "Fast", "medium": "Accurate"}
        self._notify(__app_name__, f"Speech accuracy: {labels.get(size, size)}. "
                     "The model downloads on first use if it's new.")
        threading.Thread(target=self._preload_model, daemon=True).start()

    def _ai_tier(self):
        if not bool(self.cfg.get("ai.enabled", False)):
            return None
        if self.cfg.get("ai.provider", "ollama") == "builtin":
            return "offline"
        model = self.cfg.get("ai.model")
        for tier, (tier_model, _size) in ai_setup.MODEL_TIERS.items():
            if tier_model == model:
                return tier
        return None

    def _set_ai_model(self, tier: str) -> None:
        if tier == "off":
            from ..core import offline_cleanup
            offline_cleanup.unload()
            self.cfg.set("ai.enabled", False)
            self._save_config()
            self._notify(__app_name__, "AI formatting off — plain voice-to-text.")
            return
        if tier == "offline":
            self._set_ai_offline()
            return
        model, size = ai_setup.MODEL_TIERS[tier]
        self._notify(__app_name__, f"Setting up AI ({model}, {size}). Needs Ollama "
                     "(ollama.com) — watch the menu-bar status for progress.")
        threading.Thread(target=self._setup_ai_worker, args=(model,), daemon=True).start()

    def _setup_ai_worker(self, model: str) -> None:
        def progress(message: str) -> None:
            self._set(self._state, message)

        ok, message = ai_setup.setup(model, progress=progress)
        if ok:
            from ..core import offline_cleanup
            offline_cleanup.unload()  # leaving the built-in tier → free its RAM
            self.cfg.set("ai.enabled", True)
            self.cfg.set("ai.provider", "ollama")
            self.cfg.set("ai.model", model)
            self._save_config()
        self._notify("AI formatting ready" if ok else "AI setup failed", message)
        self._set("idle", "Ready")

    def _set_ai_offline(self) -> None:
        """Built-in no-Ollama model as the AI engine. Downloads ~2 GB on first use."""
        from ..core import offline_cleanup

        self.cfg.set("ai.enabled", True)
        self.cfg.set("ai.provider", "builtin")
        self._save_config()
        if offline_cleanup.is_downloaded():
            self._notify(__app_name__, "AI formatting: Offline (no Ollama) — ready.")
            return
        if getattr(self, "_offline_dl", False):
            self._notify(__app_name__, "Offline model is still downloading…")
            return
        self._offline_dl = True
        self._notify(__app_name__, f"AI formatting: Offline — downloading the model "
                     f"({offline_cleanup.MODEL_SIZE_HINT}). I'll notify you when it's ready.")

        def _fetch() -> None:
            def _prog(frac: float) -> None:
                self._set(self._state, f"Offline model… {int(frac * 100)}%")

            ok = offline_cleanup.download(progress=_prog)
            self._offline_dl = False
            self._notify(__app_name__, "Offline AI ready — no Ollama needed. ✓" if ok
                         else "Offline AI download failed — re-select it to retry.")
            self._set("idle", "Ready")

        threading.Thread(target=_fetch, daemon=True).start()

    # ------------------------------------------------------------------
    # Menu actions — toggles
    # ------------------------------------------------------------------
    def _toggle_modes(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("text.modes.enabled", True))
        self.cfg.set("text.modes.enabled", enabled)
        self._save_config()
        self._notify(__app_name__, "Per-app formatting on: terminals/editors keep "
                     "your exact words; other apps format as usual."
                     if enabled else "Per-app formatting off.")

    def _setup_starter_pack(self, _s=None) -> None:
        self.cfg.set("text.modes.enabled", True)
        self.cfg.set("text.modes.rules", catalog.starter_pack_rules())
        self.cfg.set("text.modes.starter_pack_offered", True)
        self._save_config()
        self._notify(__app_name__, "Smart formatting on: emails come out "
                     "professional, chats stay casual, terminals/code stay as spoken.")

    def _clear_modes_rules(self, _s=None) -> None:
        self.cfg.set("text.modes.rules", [])
        self._save_config()
        self._notify(__app_name__, "Cleared your per-app rules. Terminals and code "
                     "editors still stay as spoken.")

    def _toggle_teachback(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("text.teach_back", True))
        self.cfg.set("text.teach_back", enabled)
        self._save_config()
        self._notify(__app_name__, "Will learn from your edits — cut/copy your "
                     "corrected text." if enabled else "Stopped learning from edits.")

    def _toggle_ai_learning(self, _s=None) -> None:
        if bool(self.cfg.get("text.ai_learning", False)):
            self.cfg.set("text.ai_learning", False)
            self._save_config()
            self._notify(__app_name__, "Adaptive AI learning off. Edits still "
                         "learned offline.")
            return
        model = str(self.cfg.get("text.teach_back_model", "qwen2.5:3b"))
        self._notify(__app_name__, f"Setting up adaptive learning ({model}). Needs "
                     "Ollama; watch the menu-bar status for progress.")
        threading.Thread(target=self._setup_learning_worker, args=(model,),
                         daemon=True).start()

    def _setup_learning_worker(self, model: str) -> None:
        def progress(message: str) -> None:
            self._set(self._state, message)

        ok, message = ai_setup.setup(model, progress=progress)
        if ok:
            self.cfg.set("text.ai_learning", True)
            self.cfg.set("text.teach_back", True)
            self.cfg.set("text.teach_back_model", model)
            self._save_config()
        self._notify("Adaptive learning ready" if ok else "Adaptive learning setup failed",
                     message)
        self._set("idle", "Ready")

    def _toggle_persona(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("text.persona", True))
        self.cfg.set("text.persona", enabled)
        self._save_config()
        self._notify(__app_name__, "Personalized AI on — learns your domain & tone "
                     "locally." if enabled else "Personalized AI off.")

    def _toggle_history(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("text.history.enabled", False))
        self.cfg.set("text.history.enabled", enabled)
        self._save_config()
        self._notify(__app_name__, "Saving your dictations locally on this Mac."
                     if enabled else "Stopped saving dictation history.")

    def _toggle_overlay(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("feedback.overlay", True))
        self.cfg.set("feedback.overlay", enabled)
        self._save_config()
        self.overlay.set_enabled(enabled)
        if enabled:
            self._overlay_flash("On-screen status on")
        self._notify(__app_name__, "On-screen status on." if enabled
                     else "On-screen status off.")

    def _toggle_debug_log(self, _s=None) -> None:
        enabled = not bool(self.cfg.get("text.debug_log", False))
        self.cfg.set("text.debug_log", enabled)
        self._save_config()
        self._notify(__app_name__, "Detailed logging ON — raw transcript and "
                     "corrections go to vibeflow.log." if enabled
                     else "Detailed logging off.")

    def _toggle_autostart(self, _s=None) -> None:
        try:
            enabled = autostart.toggle()
        except Exception as exc:
            self._notify(__app_name__, f"Couldn't change Start-at-login: {exc}")
            return
        self._notify(__app_name__, "VibeFlow will start automatically at login."
                     if enabled else "VibeFlow will no longer start at login.")

    # ------------------------------------------------------------------
    # Menu actions — vocabulary / persona / history files
    # ------------------------------------------------------------------
    def _open_vocabulary(self, _s=None) -> None:
        path = config_mod.config_dir() / "my_vocabulary.txt"
        try:
            self.vocabulary.write_wordlist(path)
        except Exception:
            pass
        self._open_path(str(path))

    def _open_persona(self, _s=None) -> None:
        path = config_mod.config_dir() / "my_writing_profile.txt"
        profile = self.persona.profile_text() or (
            "(Not enough dictation yet — keep using VibeFlow and it will learn "
            "your style.)"
        )
        body = (
            "# VibeFlow — your writing profile (local to this Mac)\n\n"
            f"{profile}\n\n(based on {len(self.persona.samples)} recent dictations)\n"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        except Exception:
            return
        self._open_path(str(path))

    def _forget_persona(self, _s=None) -> None:
        self.persona.clear()
        self.persona.save()
        self._notify(__app_name__, "Forgot your writing profile. It will rebuild as "
                     "you dictate.")

    def _activate_license(self, _s=None) -> None:
        """Native Activate dialog: paste a Lemon Squeezy key to unlock this Mac, or buy.
        Runs on the main thread (menu callback) so the AppKit window is safe."""
        import webbrowser

        import rumps

        cfg_dir = config_mod.config_dir()
        status = licensing.evaluate(cfg_dir)
        if status.state == "licensed" and status.edition != "beta":
            self._notify(__app_name__, "This Mac is already licensed. Thank you!")
            return
        lead = ("Your free trial has ended. " if status.state == "locked"
                else f"{status.badge}. ")
        win = rumps.Window(
            message=lead + "Paste your license key to unlock this Mac for life, or buy "
                           "VibeFlow ($10 — one device, no subscription).",
            title="VibeFlow — Activate",
            default_text="",
            ok="Activate",
            cancel="Later",
            dimensions=(340, 44),
        )
        win.add_button("Buy — $10")
        resp = win.run()
        if resp.clicked == 2:  # "Buy — $10"
            webbrowser.open(licensing.LS_CHECKOUT_URL)
            return
        if resp.clicked == 1:  # "Activate"
            key = (resp.text or "").strip()
            if not key:
                self._notify(__app_name__, "Paste your license key, then click Activate.")
                return
            try:
                licensing.activate_license(cfg_dir, key)
                self._license = licensing.evaluate(cfg_dir)
                self._notify(__app_name__, "Unlocked — this Mac is licensed for life. Thank you!")
            except licensing.ActivationError as exc:
                self._notify(__app_name__, f"Activation failed: {exc}")

    def _open_history(self, _s=None) -> None:
        try:
            out = config_mod.config_dir() / "dictation_history.html"
            out.write_text(history.render_html(history.load()), encoding="utf-8")
            self._open_path(str(out))
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't open history: {exc}")

    def _clear_history(self, _s=None) -> None:
        history.clear()
        try:
            (config_mod.config_dir() / "dictation_history.html").unlink()
        except Exception:
            pass
        self._notify(__app_name__, "Cleared your dictation history.")

    # ------------------------------------------------------------------
    # Menu actions — recovery / re-insert
    # ------------------------------------------------------------------
    def _copy_raw_transcript(self, _s=None) -> None:
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to recover yet.")
            return
        try:
            import pyperclip
            pyperclip.copy(raw)
            self._notify(__app_name__, "Copied your last unedited transcript.")
        except Exception:
            pass

    def _reinsert_spoken(self, _s=None) -> None:
        self._reinsert_last(cleaned=False)

    def _reinsert_cleaned(self, _s=None) -> None:
        self._reinsert_last(cleaned=True)

    def _reinsert_last(self, cleaned: bool) -> None:
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to re-insert yet.")
            return
        threading.Thread(target=self._reinsert_worker, args=(raw, cleaned),
                         daemon=True).start()

    def _reinsert_worker(self, raw: str, cleaned: bool) -> None:
        try:
            time.sleep(0.35)  # let focus return to your window
            text = self._apply_outcome(raw, appmode.DEFAULT) if cleaned else raw
            self._deliver_text(text)
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't re-insert: {exc}")

    def _deliver_hotkey_fire(self) -> None:
        """Cmd+Shift+V pressed while a dictation is pending → place it here,
        formatted for the focused app. Disarm immediately so a key-repeat or
        second press can't deliver twice."""
        if time.time() >= self._deliver_pending_until:
            return
        self._deliver_pending_until = 0.0
        self._reinsert_for_app()

    def _reinsert_for_app(self, _s=None) -> None:
        raw = self._last_raw_transcript
        if not raw:
            self._notify(__app_name__, "No recent dictation to deliver yet.")
            return
        threading.Thread(target=self._reinsert_for_app_worker, args=(raw,),
                         daemon=True).start()

    def _reinsert_for_app_worker(self, raw: str) -> None:
        try:
            time.sleep(0.2)
            outcome = appmode.DEFAULT
            name = None
            try:
                app_id, name, _pid = appdetect.identify()
                outcome = catalog.resolve_outcome(
                    app_id, self.cfg.get("text.modes.rules", []) or []
                )
            except Exception:
                outcome = appmode.DEFAULT
            if outcome != appmode.VERBATIM and ai_format.is_enabled(self.cfg) and name:
                self._set(self._state, f"Restructuring for {name}…")
            self._deliver_text(self._apply_outcome(raw, outcome))
        except Exception as exc:  # pragma: no cover - defensive
            self._notify(__app_name__, f"Couldn't deliver: {exc}")

    def _apply_outcome(self, raw: str, outcome: str) -> str:
        """Format ``raw`` per a per-app outcome — mirrors :meth:`_process`."""
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
                    appmode.CASUAL: "casual",
                    appmode.EMAIL: "email"}.get(outcome)
            persona_on = bool(self.cfg.get("text.persona", True))
            profile = self.persona.profile_text() if persona_on else None
            ai_text = ai_format.format_text(
                text, self.cfg, persona=profile, strip_fillers=strip_fillers, tone=tone
            )
            if ai_text:
                text = ai_text
        return text

    def _deliver_text(self, text: str) -> None:
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
            self._notify("Copied to clipboard", preview(text))

    # ------------------------------------------------------------------
    # Settings file / reload
    # ------------------------------------------------------------------
    def _open_config(self, _s=None) -> None:
        self._open_path(str(config_mod.ensure_user_config()))

    def _open_config_dir(self, _s=None) -> None:
        self._open_path(str(config_mod.config_dir()))

    def _reload(self, _s=None) -> None:
        self.cfg = defaults.load_mac_config(self.cfg.path)
        self.recorder = self._build_recorder()
        self.transcriber = self._build_transcriber()
        self.vocabulary = self._build_vocabulary()
        self.persona = self._build_persona()
        self._model_ready = False
        self.hotkeys.stop()
        self.hotkeys = self._build_hotkeys()
        self.hotkeys.start()
        threading.Thread(target=self._preload_model, daemon=True).start()
        self._notify(__app_name__, "Settings reloaded.")

    def _maybe_reload_config(self) -> None:
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
            self.cfg.data = defaults.load_mac_config().data
            try:
                self.transcriber.language = self.cfg.get("model.language", "en")
            except Exception:
                pass
            log.info("settings reloaded from disk")
        except Exception:  # pragma: no cover - never break on a bad reload
            pass

    def _save_config(self) -> None:
        try:
            self.cfg.save()
            try:
                self._cfg_mtime = config_mod.config_path().stat().st_mtime
            except OSError:
                pass
        except Exception as exc:
            self._notify("Could not save settings", str(exc))

    # ------------------------------------------------------------------
    # Setup / permissions (macOS gates the mic + Accessibility)
    # ------------------------------------------------------------------
    def _run_setup(self, _s=None) -> None:
        """One clean setup pass: fire the Microphone prompt, fire the Accessibility
        prompt, and open the Accessibility pane. The app then auto-detects the
        grant (see :meth:`_reconcile_accessibility`) and finishes on its own — no
        app restart, no extra steps."""
        if not permissions.missing():
            self._notify(__app_name__, "You're all set — hold "
                         f"{self._hotkey_label()} and speak.")
            return
        permissions.request_microphone()      # one-click Allow prompt
        if not permissions.accessibility_ok():
            permissions.prompt_accessibility()  # Apple dialog + deep-link
            permissions.open_pane("Accessibility")
            self._notify(
                "One step to finish setup",
                "Turn ON VibeFlow under Accessibility (the window that just "
                "opened). That's the only manual step — VibeFlow detects it "
                "automatically; no restart needed.",
            )

    def _open_permissions(self, _s=None) -> None:
        self._run_setup()

    def _first_run_permissions(self) -> None:
        """First launch: run the one-shot setup, or just welcome the user."""
        time.sleep(1.0)  # let the app settle before popping prompts
        marker = config_mod.config_dir() / ".welcomed_mac"
        first = not marker.exists()
        if permissions.missing():
            self._run_setup()
        elif first:
            self._notify(
                __app_name__,
                f"Welcome! Hold {self._hotkey_label()} to dictate anywhere. "
                "Everything runs on this Mac — no internet, no accounts.",
            )
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1", encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Self-update (GitHub Releases)
    # ------------------------------------------------------------------
    def _startup_update_check(self) -> None:
        time.sleep(8)  # let everything settle before hitting the network
        try:
            info = updater.check()
        except Exception:
            info = None
        if info and info.get("newer") and info.get("zip_url"):
            self._update_info = info
            self._notify(__app_name__, f"VibeFlow {info['version']} is available — "
                         "open the menu to update.")

    def _launch_manager(self, flag: str) -> None:
        """Spawn a standalone Tk window in its own process (own event loop)."""
        import subprocess
        import sys
        try:
            args = ([sys.executable, flag] if getattr(sys, "frozen", False)
                    else [sys.executable, "-m", "vibeflow", flag])
            subprocess.Popen(args)
        except Exception:
            pass

    def _open_update_dialog(self, _s=None) -> None:
        self._launch_manager("--update")

    def _check_update_marker(self) -> None:
        """The update dialog (separate process) downloads the new build and drops a
        marker; the menu-bar process does the swap-and-quit it can't do itself.
        Marker name must match update_window.UPDATE_MARKER."""
        import os

        marker = config_mod.config_dir() / "update_pending.json"
        if not marker.exists():
            return
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            data = None
        try:
            marker.unlink()
        except Exception:
            pass
        if not data:
            return
        zip_path, ver = data.get("zip"), data.get("version")
        if not zip_path or not os.path.exists(zip_path):
            return
        self._notify(__app_name__, f"Installing VibeFlow {ver}… it will reopen automatically.")
        if updater.apply_update(zip_path, expected_version=ver):
            self._quit()  # the helper waits on THIS process, then swaps + relaunches

    def _update_action(self, _s=None) -> None:
        if self._update_info:
            self._apply_update()
        else:
            self._check_updates()

    def _check_updates(self, _s=None) -> None:
        def work():
            try:
                info = updater.check()
            except Exception:
                info = None
            if info is None:
                self._notify(__app_name__, "Couldn't check for updates (no internet?).")
            elif info.get("newer") and info.get("zip_url"):
                self._update_info = info
                self._notify(__app_name__, f"VibeFlow {info['version']} is available — "
                             "choose “Install update” in the menu.")
            else:
                self._notify(__app_name__, f"You're on the latest version (v{__version__}).")

        threading.Thread(target=work, daemon=True).start()

    def _apply_update(self, _s=None) -> None:
        info = self._update_info
        if not info or not info.get("zip_url"):
            return self._check_updates()

        def work():
            self._set(self._state, "Downloading update…")
            path = updater.download_zip(
                info["zip_url"], progress=lambda m: self._set(self._state, m)
            )
            if not path:
                self._notify(__app_name__, "Update download failed — opening the page.")
                self._open_path(info.get("page_url"))
                self._set("idle", "Ready")
                return
            self._set(self._state, "Installing update…")
            if updater.apply_update(path, expected_version=info.get("version")):
                self._notify(__app_name__, f"Installing VibeFlow {info['version']}… "
                             "it will reopen automatically.")
                self._quit()  # the helper swaps the bundle and relaunches
            else:
                self._notify(__app_name__, "Update couldn't be verified/installed — "
                             "opening the release page.")
                self._open_path(info.get("page_url"))
                self._set("idle", "Ready")

        threading.Thread(target=work, daemon=True).start()

    def _about(self, _s=None) -> None:
        self._notify(f"{__app_name__} {__version__}",
                     f"Offline voice typing. {self._trigger_hint()} to dictate.")

    def _quit(self, _s=None) -> None:
        import rumps
        self._stopping = True
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.overlay.hide()
        except Exception:
            pass
        rumps.quit_application()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set(self, state: str, status: str) -> None:
        self._state = state
        self._status = status

    def _hotkey_label(self) -> str:
        key = str(self.cfg.get("hotkey.push_to_talk_key", "cmd_r"))
        pretty = {"cmd_r": "Right ⌘", "cmd_l": "Left ⌘", "cmd": "⌘"}
        return pretty.get(
            key.lower(),
            "+".join(p.strip().capitalize() for p in key.split("+") if p.strip()),
        )

    def _trigger_hint(self) -> str:
        return f"Hold {self._hotkey_label()}"

    def _notify(self, title: str, message: str) -> None:
        # Queue from any thread; the rumps.Timer delivers it on the main thread
        # (Cocoa's notification center must be touched from the main thread).
        if not bool(self.cfg.get("feedback.notifications", True)):
            return
        with self._notify_lock:
            self._notify_queue.append((title, message))

    @staticmethod
    def _open_path(path: str) -> None:
        try:
            import subprocess
            subprocess.Popen(["open", path])
        except Exception:
            pass


def run() -> int:
    """Entry point: load config (with Mac defaults) and start the menu-bar app."""
    from .. import logsetup

    try:
        logsetup.setup()
    except Exception:
        logging.basicConfig(level=logging.INFO)

    cfg = defaults.load_mac_config()
    MenuBarApp(cfg).run()
    return 0
