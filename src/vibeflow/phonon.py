"""Phonon speech engine adapter (Fermion Research's ``fermion-research`` package).

Phonon-2 is a compressed NVIDIA Parakeet-TDT 0.6B v3: English only, ~160 MB,
native CPU kernels on Windows, Linux and Intel Macs, MLX on Apple silicon.
Everything that knows about the fermion package lives here; the Transcriber
picks the engine, adds the lead-in silence and handles the Whisper fallback.

``fermion`` is imported lazily, so the rest of VibeFlow works without it (Python
3.9 installs, the test-suite).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .core.numbers import spoken_numbers_to_digits, tidy_digits

# VibeFlow model ids accepted in ``model.size`` -> the name fermion loads.
# phonon-2.5-en is the newer sibling; it writes digits itself.
MODELS = {"phonon-2": "phonon-2", "phonon-2.5-en": "phonon-2.5-en"}


class PhononError(RuntimeError):
    """A Phonon model couldn't load or decode."""


def prepare_env(models_dir: str | Path | None) -> None:
    """Point fermion at VibeFlow's models folder; no progress bars (the windowed
    app has no console). Existing values win, so a developer can redirect them."""
    if models_dir:
        os.environ.setdefault("FERMION_CACHE_DIR", str(models_dir))
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def is_cached(size: str = "phonon-2", models_dir: str | Path | None = None) -> bool | None:
    """Is this Phonon model unpacked on disk? None when it can't be told (the
    package isn't installed), so callers can let the loader decide."""
    try:
        prepare_env(models_dir)
        from fermion._speech import fetch
        from fermion.transcribe import _resolve

        repo, _key, pin, local_dir = _resolve(MODELS.get(size, size))
        if local_dir is not None:
            return True
        return bool(fetch.installed(repo, pin["unpack_dir"]))
    except (Exception, SystemExit):  # fermion refuses with SystemExit
        return None


def load(size: str, models_dir: str | Path | None = None, language: str = "en"):
    """Load a Phonon model, downloading it once. Returns (model, engine kind),
    where the kind is "cpu" or "mlx"."""
    try:
        import fermion
    except Exception as exc:
        raise PhononError(f"{size} needs the 'fermion-research' package (Python 3.10+).") from exc
    prepare_env(models_dir)  # fermion creates the folders it needs
    try:
        model = fermion.load_speech(MODELS.get(size, size), quiet=True)
    except (Exception, SystemExit) as exc:  # fermion refuses with SystemExit
        raise PhononError(f"Could not load the '{size}' model: {exc}") from exc
    lang = str(language or "").strip().lower()
    if lang not in ("", "en", "auto", "auto-detect", "autodetect"):
        logging.getLogger("vibeflow").warning(
            "%s is English only; language %r is ignored.", size, lang
        )
    try:
        kind = str(model.describe().get("engine") or "cpu")
    except Exception:
        kind = "cpu"
    return model, kind


def transcribe(model, audio) -> str:
    """Decode 16 kHz mono float32 audio and return text as a person would type it.

    Phonon writes most numbers as words ("five hundred three") and puts the
    spaces in the wrong place around digits it writes itself ("at245 PM"); both
    are repaired here, so the output reads like Whisper's ("503", "at 2:45 PM").
    The vocabulary isn't sent as hotwords: on the benchmark clips they split
    words ("kubectl" -> "Qube Ectle") at the default strength and did nothing at
    lower ones. Learned terms still reach the optional AI formatting step.
    """
    try:
        result = model.transcribe_array_detailed(audio, hotwords=[])
    except (Exception, SystemExit) as exc:  # fermion refuses with SystemExit
        raise PhononError(f"Transcription failed: {exc}") from exc
    return spoken_numbers_to_digits(tidy_digits(str(getattr(result, "text", "") or "")))
