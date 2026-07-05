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


# The speech models VibeFlow exposes, mapped to their HuggingFace CTranslate2 repo.
# Passing the explicit repo id (rather than a bare shorthand) makes model loading
# independent of the installed faster-whisper version's built-in shortcut table, so
# large-v3-turbo / distil-large-v3 load reliably. distil-large-v3 is English-only.
MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
}


def resolve_model(size: str) -> str:
    """Model shorthand -> the HF repo id to hand faster-whisper (pass-through if unknown)."""
    return MODEL_REPOS.get(size, size)


def model_cache_dirname(size: str) -> str | None:
    """HF-hub cache folder name for a model shorthand (None if unknown)."""
    repo = MODEL_REPOS.get(size)
    return ("models--" + repo.replace("/", "--")) if repo else None


# Prepend this much silence before transcription. Whisper's encoder has an edge
# effect and its VAD can trim a soft speech onset, so audio that starts *exactly*
# at the first spoken word tends to lose that word ("spin up a…" → "…"). A short
# lead-in of silence gives the model a clean run-up and fixes the dropped opener.
LEAD_PAD_S = 0.5


def _lead_pad(audio):
    import numpy as np

    x = np.asarray(audio, dtype="float32")
    n = int(LEAD_PAD_S * 16000)
    return x if n <= 0 else np.concatenate([np.zeros(n, dtype="float32"), x])


# A non-Whisper engine exposed for the bake-off, dispatched by the model-id prefix.
def _engine_of(size: str) -> str:
    return "moonshine" if str(size or "").startswith("moonshine") else "whisper"


def _audio_to_wav(audio, sample_rate: int = 16000) -> str:
    """Write a float32 mono array to a temp 16-bit WAV and return its path — the
    Moonshine ONNX runtime accepts a WAV path robustly."""
    import os
    import tempfile
    import wave

    import numpy as np

    x = np.asarray(audio, dtype="float32").flatten()
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return path


class Transcriber:
    """Lazy wrapper around a speech model — faster-whisper by default, or the
    Moonshine / Parakeet ONNX engines when the model id selects them."""

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
        self.engine = _engine_of(size)
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
        if self.engine != "whisper":
            self._model = self.engine  # sentinel — the ONNX engine loads/caches per call
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
        name = resolve_model(self.size)
        try:
            return WhisperModel(name, local_files_only=True, **common)
        except Exception:
            if not allow_download:
                raise
            return WhisperModel(name, local_files_only=False, **common)

    def transcribe(self, audio, prompt: str | None = None) -> str:
        """Transcribe a float32 numpy audio array (16 kHz) into text.

        ``prompt`` is passed as Whisper's ``initial_prompt`` to bias decoding
        toward the user's adaptive vocabulary (names, jargon, acronyms).
        """
        if self._model is None:
            self.load()

        if self.engine == "moonshine":
            return self._transcribe_moonshine(audio)

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

    def _transcribe_moonshine(self, audio) -> str:
        """Moonshine v2 via onnxruntime — a tiny, edge-optimized model. Best on
        short (<~30 s) clips; may drift on long audio. self.size is e.g. 'moonshine/base'."""
        import os

        try:
            from moonshine_onnx import transcribe as _moonshine_transcribe
        except Exception as exc:
            raise TranscriptionError(
                "Moonshine isn't available in this build (useful-moonshine-onnx missing)."
            ) from exc
        path = _audio_to_wav(audio)
        try:
            res = _moonshine_transcribe(path, self.size)
            if isinstance(res, (list, tuple)):
                return " ".join(str(r) for r in res).strip()
            return str(res).strip()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

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
            _lead_pad(audio),
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            initial_prompt=prompt or None,
        )
        return "".join(segment.text for segment in segments)

    def transcribe_words(self, audio, prompt: str | None = None):
        """Word-level transcription — list of (start, end, word) with per-word
        timestamps, for the streaming LocalAgreement processor. Whisper engine only.
        Each pass re-transcribes the rolling window independently (no cross-window
        conditioning), which is what LocalAgreement needs."""
        if self._model is None:
            self.load()
        lang = str(self.language or "").strip().lower()
        if lang in ("", "auto", "auto-detect", "autodetect"):
            lang = "en"
        # GREEDY decoding (beam_size=1) for streaming: each pass must run well faster
        # than real time so the model keeps up while you speak (then only a short tail
        # remains on release). LocalAgreement's cross-pass agreement recovers the small
        # accuracy that greedy loses, so the committed text stays clean. This is what
        # takes a 5-minute dictation from ~5 min of waiting to a few seconds.
        segments, _info = self._model.transcribe(
            _lead_pad(audio),
            language=lang,
            beam_size=1,
            vad_filter=self.vad_filter,
            initial_prompt=prompt or None,
            word_timestamps=True,
            condition_on_previous_text=False,
        )
        out = []
        for seg in segments:
            for w in (getattr(seg, "words", None) or []):
                # Shift back by the lead pad so times are relative to the real audio.
                s, e = float(w.start) - LEAD_PAD_S, float(w.end) - LEAD_PAD_S
                if e <= 0:  # word falls entirely inside the silent pad
                    continue
                out.append((max(0.0, s), max(0.0, e), w.word))
        return out


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
