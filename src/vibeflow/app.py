"""The VibeFlow application: state machine + system-tray UI.

Wires together the hotkey listener, microphone, transcriber and output router,
and exposes everything through a small tray icon menu. The icon changes colour
to show what's happening:

    blue  = idle (ready)
    red   = recording
    amber = transcribing

All heavy work (transcription) runs off the hotkey/UI threads so the app stays
responsive.
"""

from __future__ import annotations

import os
import threading

from . import __app_name__, __version__, config as config_mod, notifier
from .audio import AudioError, Recorder
from .focus_detect import detect_focus
from .hotkey import HotkeyManager
from .output import COPIED, deliver
from .text import clean_transcript, preview
from .transcriber import Transcriber, TranscriptionError

# Tray icon colours per state.
_COLOR_IDLE = (70, 130, 180, 255)
_COLOR_REC = (220, 50, 50, 255)
_COLOR_BUSY = (230, 170, 40, 255)


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
            mode=self.cfg.get("hotkey.mode", "toggle"),
            toggle_combo=self.cfg.get("hotkey.toggle_combo", "ctrl+alt+space"),
            push_to_talk_key=self.cfg.get("hotkey.push_to_talk_key", "ctrl_r"),
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
        self._set_status("Transcribing…")
        self._refresh()

        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio) -> None:
        try:
            seconds = self.recorder.duration(audio)
            min_seconds = float(self.cfg.get("audio.min_seconds", 0.4))
            if seconds < min_seconds:
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
                self._notify(__app_name__, "No speech detected.")
                return

            result = deliver(
                text,
                output_mode=self.cfg.get("output.mode", "auto"),
                focus_state=detect_focus(),
                insertion=self.cfg.get("output.insertion", "paste"),
                restore_clipboard=bool(self.cfg.get("output.restore_clipboard", True)),
                trailing_space=bool(self.cfg.get("output.trailing_space", True)),
                auto_fallback=self.cfg.get("output.auto_fallback", "clipboard"),
            )
            if result == COPIED:
                self._notify("Copied to clipboard", preview(text))
        except TranscriptionError as exc:
            notifier.play(notifier.ERROR, self._sounds)
            self._notify("Transcription error", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            notifier.play(notifier.ERROR, self._sounds)
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
        try:
            import pystray
        except Exception as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "The tray UI (pystray) is not installed. "
                "Run the installer or 'pip install -r requirements.txt'."
            ) from exc

        self.icon = pystray.Icon(
            __app_name__,
            icon=self._image(_COLOR_IDLE),
            title=self._tooltip(),
            menu=self._menu(pystray),
        )
        self.icon.run(setup=self._on_ready)

    def _on_ready(self, icon) -> None:
        icon.visible = True
        self._set_status("Loading model…")
        self._refresh()
        self.hotkeys.start()
        threading.Thread(target=self._preload_model, daemon=True).start()

    def _preload_model(self) -> None:
        try:
            self.transcriber.load()
            self._model_ready = True
            self._set_status("Ready")
            self._notify(
                __app_name__,
                f"Ready. {self._trigger_hint()} to dictate.",
            )
        except TranscriptionError as exc:
            self._set_status("Model failed to load")
            self._notify("Could not load speech model", str(exc))
        finally:
            self._refresh()

    def _menu(self, pystray):
        Item = pystray.MenuItem
        Menu = pystray.Menu
        return Menu(
            Item(lambda _: self._status, None, enabled=False),
            Menu.SEPARATOR,
            Item(
                "Trigger",
                Menu(
                    Item(
                        "Toggle (tap to start/stop)",
                        lambda i: self._set_mode("toggle"),
                        checked=lambda i: self.cfg.get("hotkey.mode") == "toggle",
                        radio=True,
                    ),
                    Item(
                        "Push-to-talk (hold key)",
                        lambda i: self._set_mode("push_to_talk"),
                        checked=lambda i: self.cfg.get("hotkey.mode") == "push_to_talk",
                        radio=True,
                    ),
                ),
            ),
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
            Menu.SEPARATOR,
            Item("Open settings file", self._open_config),
            Item("Open settings folder", self._open_config_dir),
            Item("Reload settings", self._reload),
            Menu.SEPARATOR,
            Item(f"About {__app_name__} {__version__}", self._about),
            Item("Quit", self._quit),
        )

    # -- menu actions ---------------------------------------------------
    def _set_mode(self, mode: str) -> None:
        self.cfg.set("hotkey.mode", mode)
        self._save_config()
        self.hotkeys.stop()
        self.hotkeys = self._build_hotkeys()
        self.hotkeys.start()
        self._notify(__app_name__, f"Trigger: {self._trigger_hint()}")

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
        threading.Thread(target=self._preload_model, daemon=True).start()
        self._notify(__app_name__, "Settings reloaded.")

    def _about(self, *_args) -> None:
        self._notify(
            f"{__app_name__} {__version__}",
            f"Offline voice typing. {self._trigger_hint()} to dictate.",
        )

    def _quit(self, *_args) -> None:
        try:
            self.hotkeys.stop()
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

    def _trigger_hint(self) -> str:
        if self.cfg.get("hotkey.mode") == "push_to_talk":
            return f"Hold {self.cfg.get('hotkey.push_to_talk_key', 'ctrl_r')}"
        return f"Press {self.cfg.get('hotkey.toggle_combo', 'ctrl+alt+space')}"

    def _save_config(self) -> None:
        try:
            self.cfg.save()
        except Exception as exc:
            self._notify("Could not save settings", str(exc))

    def _set_status(self, status: str) -> None:
        self._status = status

    def _tooltip(self) -> str:
        return f"{__app_name__} — {self._status}"

    def _image(self, color):
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([24, 8, 40, 38], radius=8, fill=color)
        d.arc([18, 20, 46, 48], start=0, end=180, fill=color, width=4)
        d.line([32, 48, 32, 56], fill=color, width=4)
        d.line([23, 56, 41, 56], fill=color, width=4)
        return img

    def _current_color(self):
        if self._recording:
            return _COLOR_REC
        if self._busy:
            return _COLOR_BUSY
        return _COLOR_IDLE

    def _refresh(self) -> None:
        if self.icon is None:
            return
        try:
            self.icon.icon = self._image(self._current_color())
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
