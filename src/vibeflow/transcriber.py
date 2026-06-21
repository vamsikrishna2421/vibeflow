"""Offline speech-to-text using faster-whisper (CTranslate2).

The model is downloaded once into the app's data folder and then runs fully
offline. ``faster_whisper`` is imported lazily so the rest of VibeFlow — and the
test-suite — works without the (large) inference dependencies installed.
"""

from __future__ import annotations

from pathlib import Path


class TranscriptionError(RuntimeError):
    """Raised when a model cannot be loaded or audio cannot be transcribed."""


class Transcriber:
    """Lazy wrapper around a faster-whisper model."""

    def __init__(
        self,
        size: str = "base",
        language: str = "auto",
        device: str = "auto",
        compute_type: str = "auto",
        models_dir: str | Path | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        self.size = size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.models_dir = str(models_dir) if models_dir else None
        self.beam_size = int(beam_size)
        self.vad_filter = bool(vad_filter)
        self._model = None
        self._resolved: tuple[str, str] | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self, allow_download: bool = True) -> None:
        """Load the model into memory (downloading it on first ever use).

        ``allow_download=False`` forces a pure offline open and never touches the
        network: used when retrying a model that is already cached but briefly
        locked (e.g. antivirus scanning model.bin right after an auto-update).
        """
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - depends on host
            raise TranscriptionError(
                "The speech engine (faster-whisper) is not installed. "
                "Run the installer or 'pip install -r requirements.txt'."
            ) from exc

        device, compute_type = _resolve_device(self.device, self.compute_type)
        self._resolved = (device, compute_type)
        if self.models_dir:
            try:
                Path(self.models_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        common = dict(
            device=device,
            compute_type=compute_type,
            download_root=self.models_dir,
        )
        try:
            # Offline-first: if the model is already downloaded, load it with no
            # network access at all (true offline + faster startup, and avoids a
            # huggingface.co call that crashed the windowed build). Only reach the
            # internet if the model isn't cached yet (first-ever run).
            try:
                self._model = WhisperModel(self.size, local_files_only=True, **common)
            except Exception:
                # The caller is retrying a *cached* model that is momentarily
                # locked (antivirus scan after an update); a slow network
                # fallback on every attempt would burn the retry budget, so
                # re-raise and let the caller retry the fast offline path.
                if not allow_download:
                    raise
                self._model = WhisperModel(self.size, local_files_only=False, **common)
        except Exception as exc:
            raise TranscriptionError(
                f"Could not load the '{self.size}' model on {device}/{compute_type}: {exc}"
            ) from exc

    def transcribe(self, audio, prompt: str | None = None) -> str:
        """Transcribe a float32 numpy audio array (16 kHz) into text.

        ``prompt`` is passed as Whisper's ``initial_prompt`` to bias decoding
        toward the user's adaptive vocabulary (names, jargon, acronyms).
        """
        if self._model is None:
            self.load()

        # English by default. A valid language code set in config still works,
        # but anything empty / "auto" / an unknown value falls back to English so
        # a bad setting can never crash transcription (faster-whisper raises on
        # unknown codes). Whisper auto-detection is intentionally not used.
        lang = str(self.language or "").strip().lower()
        if lang in ("", "auto", "auto-detect", "autodetect"):
            lang = "en"
        try:
            return self._run(audio, lang, prompt)
        except Exception as exc:
            if lang != "en":
                import logging

                logging.getLogger("vibeflow").warning(
                    "language %r failed (%s: %s); using English",
                    lang, type(exc).__name__, exc,
                )
                try:
                    return self._run(audio, "en", prompt)
                except Exception as exc2:
                    raise TranscriptionError(f"Transcription failed: {exc2}") from exc2
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

    def _run(self, audio, language, prompt: str | None):
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            initial_prompt=prompt or None,
        )
        return "".join(segment.text for segment in segments)


def _resolve_device(device: str, compute_type: str) -> tuple[str, str]:
    """Pick a concrete (device, compute_type) pair, auto-detecting CUDA."""
    dev = (device or "auto").lower()
    if dev == "auto":
        dev = "cuda" if _cuda_available() else "cpu"

    compute = (compute_type or "auto").lower()
    if compute == "auto":
        compute = "float16" if dev == "cuda" else "int8"
    return dev, compute


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False
