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

import os
import sys
import threading

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

            text = self.transcriber.transcribe(audio)
            self._model_ready = True
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
            if ai_format.is_enabled(self.cfg):
                ai_text = ai_format.format_text(text, self.cfg)
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
            import logging

            logging.getLogger("vibeflow").info(
                "delivered: focus=%s result=%s chars=%d", focus, result, len(text)
            )
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
        threading.Thread(target=self._preload_model, daemon=True).start()

    def _preload_model(self) -> None:
        try:
            self.transcriber.load()
            self._model_ready = True
            self._set_status("Ready")
            import logging

            logging.getLogger("vibeflow").info(
                "Model ready: %s %s", self.cfg.get("model.size"), self.transcriber._resolved
            )
            self._notify(
                __app_name__,
                f"Ready. {self._trigger_hint()} to dictate.",
            )
        except Exception as exc:
            import logging
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
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda i: autostart.is_enabled(),
            ),
            Item(f"About {__app_name__} {__version__}", self._about),
            Item("Quit", self._quit),
        )

    # -- menu actions ---------------------------------------------------
    def _set_output(self, mode: str) -> None:
        self.cfg.set("output.mode", mode)
        self._save_config()
        self._notify(__app_name__, f"Output set to '{mode}'.")

    def _open_config(self, *_args) -> None:
        path = config_mod.ensure_user_config()
        self._open_path(str(path))

    def _open_config_dir(self, *_args) -> None:
        self._open_path(str(config_mod.config_dir()))

    def _reload(self, *_args) -> None:
        self.cfg = config_mod.load_config(self.cfg.path)
        self.recorder = self._build_recorder()
        self.transcriber = self._build_transcriber()
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
        if ok:
            self.cfg.set("ai.enabled", True)
            self.cfg.set("ai.model", model)
            self._save_config()
        self._notify("AI formatting ready" if ok else "AI setup failed", message)
        self._set_status("Ready")
        self._refresh()

    def _quit(self, *_args) -> None:
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
