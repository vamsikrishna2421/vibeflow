"""Microphone capture.

A small wrapper around ``sounddevice`` that records mono 16 kHz float32 audio —
exactly what Whisper-style models expect — into memory while the user holds (or
toggles) the hotkey. ``sounddevice``/``numpy`` are imported lazily so importing
this module never fails on a machine without audio libraries installed.
"""

from __future__ import annotations

import threading


class AudioError(RuntimeError):
    """Raised when the microphone cannot be opened or read."""


class Recorder:
    """Records audio into memory and returns it as a float32 numpy array."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        input_device: str | int | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.input_device = _normalize_device(input_device)
        self._frames: list = []
        self._stream = None
        self._lock = threading.Lock()
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Open the input stream and begin collecting audio."""
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on host
            raise AudioError(
                "Could not load the audio backend (sounddevice). "
                "Install requirements and check your microphone."
            ) from exc

        with self._lock:
            self._frames = []
            self._recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self.input_device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._recording = False
            raise AudioError(f"Could not open microphone: {exc}") from exc

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        # Called from a separate audio thread; copy because the buffer is reused.
        if self._recording:
            with self._lock:
                self._frames.append(indata.copy())

    def stop(self):
        """Stop recording and return the captured audio as a 1-D float32 array."""
        import numpy as np

        with self._lock:
            self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            frames = self._frames
            self._frames = []

        if not frames:
            return np.zeros(0, dtype="float32")
        audio = np.concatenate(frames, axis=0)
        if audio.ndim > 1:  # mix down to mono just in case
            audio = audio.mean(axis=1)
        return audio.astype("float32", copy=False)

    def duration(self, audio) -> float:
        """Length of an audio array in seconds."""
        try:
            return float(len(audio)) / float(self.sample_rate)
        except Exception:
            return 0.0


def _normalize_device(device: str | int | None):
    """Translate a friendly device setting into something sounddevice accepts."""
    if device in (None, "", "default"):
        return None
    if isinstance(device, int):
        return device
    text = str(device).strip()
    if text.isdigit():
        return int(text)
    return text  # sounddevice accepts a (sub)string name match


def list_input_devices() -> list[str]:
    """Return human-readable lines describing available input devices."""
    try:
        import sounddevice as sd
    except Exception as exc:
        return [f"(could not query audio devices: {exc})"]

    lines: list[str] = []
    try:
        for index, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                # Device names can contain embedded newlines / odd characters;
                # flatten them to a single tidy line.
                name = " ".join(str(dev.get("name", "unknown")).split())
                lines.append(f"[{index}] {name} ({dev.get('max_input_channels')} ch)")
    except Exception as exc:
        return [f"(could not query audio devices: {exc})"]
    return lines or ["(no input devices found)"]
