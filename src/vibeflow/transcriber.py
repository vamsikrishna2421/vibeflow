"""Offline speech-to-text using faster-whisper (CTranslate2).

The model is downloaded once into the app's data folder and then runs fully
offline. ``faster_whisper`` is imported lazily so the rest of VibeFlow — and the
test-suite — works without the (large) inference dependencies installed.
"""

from __future__ import annotations

import sys
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

        if self.models_dir:
            try:
                Path(self.models_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        device, compute_type = _resolve_device(self.device, self.compute_type)
        try:
            self._model = self._open_model(WhisperModel, device, compute_type, allow_download)
            self._resolved = (device, compute_type)
        except Exception as exc:
            # A machine can have an NVIDIA GPU but no CUDA runtime (the cuBLAS/cuDNN
            # DLLs), so an explicit ``device: cuda`` fails to load with e.g.
            # "Library cublas64_12.dll is not found". Fall back to CPU rather than
            # leaving the user unable to dictate. (The default already resolves to
            # CPU; this guards the opt-in GPU path.)
            if device != "cpu":
                import logging

                logging.getLogger("vibeflow").warning(
                    "GPU model load failed on %s/%s (%s); falling back to CPU.",
                    device, compute_type, exc,
                )
                try:
                    self._model = self._open_model(WhisperModel, "cpu", "int8", allow_download)
                    self._resolved = ("cpu", "int8")
                    self.device, self.compute_type = "cpu", "int8"
                    return
                except Exception as exc2:
                    raise TranscriptionError(
                        f"Could not load the '{self.size}' model on cpu/int8: {exc2}"
                    ) from exc2
            raise TranscriptionError(
                f"Could not load the '{self.size}' model on {device}/{compute_type}: {exc}"
            ) from exc

    def _open_model(self, WhisperModel, device: str, compute_type: str, allow_download: bool):
        """Construct a ``WhisperModel`` offline-first (cached model → no network).

        Trying ``local_files_only=True`` first keeps a cached model fully offline
        (faster startup, and avoids a huggingface.co call that crashed the
        windowed build); only an uncached model reaches the internet. When
        ``allow_download`` is False (a retry of a momentarily-locked cached model,
        e.g. antivirus scanning ``model.bin`` after an update) the network path is
        skipped so the retry budget isn't burned on a slow fallback.
        """
        common = dict(
            device=device, compute_type=compute_type, download_root=self.models_dir
        )
        try:
            return WhisperModel(self.size, local_files_only=True, **common)
        except Exception:
            if not allow_download:
                raise
            return WhisperModel(self.size, local_files_only=False, **common)

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
            return self._run_with_lang(audio, lang, prompt)
        except Exception as exc:
            # The model loaded on the GPU but inference can't reach the CUDA
            # runtime (cuBLAS/cuDNN missing): rebuild on CPU once and retry, so a
            # GPU without its libraries never breaks dictation.
            if self._resolved and self._resolved[0] != "cpu" and self._reload_on_cpu():
                try:
                    return self._run_with_lang(audio, lang, prompt)
                except Exception as exc2:
                    raise TranscriptionError(f"Transcription failed: {exc2}") from exc2
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

    def _run_with_lang(self, audio, lang: str, prompt: str | None) -> str:
        """Transcribe, falling back from a bad language code to English."""
        try:
            return self._run(audio, lang, prompt)
        except Exception as exc:
            if lang != "en":
                import logging

                logging.getLogger("vibeflow").warning(
                    "language %r failed (%s: %s); using English",
                    lang, type(exc).__name__, exc,
                )
                return self._run(audio, "en", prompt)
            raise

    def _reload_on_cpu(self) -> bool:
        """Rebuild the model on CPU after a GPU failure. ``True`` on success."""
        try:
            from faster_whisper import WhisperModel
        except Exception:
            return False
        import logging

        logging.getLogger("vibeflow").warning(
            "GPU transcription failed; falling back to CPU (model=%s).", self.size
        )
        self._model = None
        try:
            self._model = self._open_model(WhisperModel, "cpu", "int8", allow_download=True)
            self._resolved = ("cpu", "int8")
            self.device, self.compute_type = "cpu", "int8"
            return True
        except Exception:
            self._model = None
            return False

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
    """Pick a concrete (device, compute_type) pair.

    ``auto`` uses the GPU only when CUDA is genuinely usable here (a CUDA device
    *and* its runtime libraries loadable), otherwise CPU — so a machine with an
    NVIDIA GPU but no CUDA runtime quietly runs on CPU instead of failing with
    "cublas64_12.dll is not found". Explicit ``cuda``/``cpu`` are honoured (and an
    unusable explicit ``cuda`` still falls back to CPU at load/inference time).
    """
    dev = (device or "auto").lower()
    if dev == "auto":
        dev = "cuda" if _cuda_available() else "cpu"
    if dev not in ("cpu", "cuda"):
        dev = "cpu"

    compute = (compute_type or "auto").lower()
    if compute == "auto":
        compute = "float16" if dev == "cuda" else "int8"
    return dev, compute


def _cuda_available() -> bool:
    """True only when a CUDA GPU is present *and* its runtime can actually load.

    ctranslate2 reporting a GPU is not enough: many machines have an NVIDIA GPU
    but no CUDA runtime (the cuBLAS/cuDNN DLLs), where selecting CUDA fails at
    load/inference. Requiring cuBLAS to load means ``auto`` only picks the GPU
    when it will really work.
    """
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False
    return _cuda_runtime_loadable()


def _cuda_runtime_loadable() -> bool:
    """Whether the CUDA math runtime (cuBLAS) can be loaded on this machine."""
    import ctypes

    name = "cublas64_12.dll" if sys.platform == "win32" else "libcublas.so.12"
    try:
        ctypes.CDLL(name)
        return True
    except OSError:
        return False
