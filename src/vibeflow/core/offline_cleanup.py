"""No-Ollama cleanup — a small local LLM embedded in VibeFlow.

For users who don't want to install Ollama, this runs the SAME strict-proofreader
cleanup with a compact Qwen2.5-3B model via ``llama-cpp-python`` (the same
llama.cpp engine Ollama uses, but in-process). It's fully **opt-in**: nothing is
downloaded or loaded until the user enables the tray option, at which point the
~2 GB GGUF is fetched once into the app-data folder.

Everything is lazy and defensive — a missing model, missing runtime, or a bad
generation returns ``None`` so the caller keeps the deterministic-curated text.
The same drift guards as the Ollama path protect against a small model rewriting
the speaker's meaning.
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from pathlib import Path

_log = logging.getLogger("vibeflow")

# Qwen2.5-3B-Instruct, Q4_K_M — matches the Ollama-3b cleanup quality (bake-off
# verified: fixes mis-heard technical terms without drift), ~2 GB on disk.
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/"
    "resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
)
MODEL_FILE = "qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_SIZE_HINT = "~2 GB"

_llm = None            # cached llama_cpp.Llama once loaded
_llm_lock = threading.Lock()


def model_path() -> Path:
    from ..config import config_dir

    return config_dir() / "models" / MODEL_FILE


def is_downloaded() -> bool:
    """True if the GGUF model is present on disk (i.e. the feature is set up)."""
    try:
        p = model_path()
        return p.exists() and p.stat().st_size > 100_000_000
    except Exception:
        return False


def download(progress=None) -> bool:
    """Fetch the model into the app-data folder. Returns True on success.

    ``progress(fraction)`` is called with 0..1 as bytes arrive (optional). Writes
    to a ``.part`` file and renames on completion so a half-finished download is
    never mistaken for a working model.
    """
    dest = model_path()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "VibeFlow"})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0) or 0)
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)  # 1 MB
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        try:
                            progress(done / total)
                        except Exception:
                            pass
        tmp.replace(dest)
        return True
    except Exception as exc:
        _log.info("offline_cleanup: download failed (%s)", exc)
        try:
            dest.with_suffix(".part").unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _get_llm():
    """Load (and cache) the model, or return None if unavailable."""
    global _llm
    with _llm_lock:
        if _llm is not None:
            return _llm
        if not is_downloaded():
            return None
        try:
            import os

            from llama_cpp import Llama

            _llm = Llama(
                model_path=str(model_path()),
                n_ctx=8192,
                n_threads=max(2, (os.cpu_count() or 4) - 1),
                verbose=False,
            )
            return _llm
        except Exception as exc:
            _log.info("offline_cleanup: model load failed (%s)", exc)
            return None


def unload() -> None:
    """Drop the in-memory model (frees ~2 GB RAM) — called when disabled."""
    global _llm
    with _llm_lock:
        _llm = None


def format_text(text: str, cfg, *, persona: str | None = None) -> str | None:
    """Clean ``text`` with the local model. Returns cleaned text, or None on any
    failure / drift so the caller keeps the deterministic-curated text."""
    if not text or not text.strip():
        return None
    llm = _get_llm()
    if llm is None:
        return None

    from .ai_format import _DEFAULT_PROMPT, _mostly_preserved, _preserves_voice

    system = _DEFAULT_PROMPT
    if persona:
        system += f"\n\nSpeaker's known terms/style (for correction context only): {persona}"
    try:
        with _llm_lock:
            resp = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Text:\n{text}\n\nCorrected text:"},
                ],
                temperature=0,
                max_tokens=2048,
            )
        out = (resp["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        _log.info("offline_cleanup: generation failed (%s)", exc)
        return None

    if not out:
        return None
    # Drift guards: reject a point-of-view change or a large length swing (a small
    # model going off the rails) — fall back to the deterministic text instead.
    if not _preserves_voice(text, out):
        return None
    if len(out) > len(text) * 1.7 or len(out) < len(text) * 0.5:
        return None
    # Faithfulness guard: allow targeted fixes (e.g. "fathering" -> "gathering")
    # but reject wholesale paraphrasing — keep the plain transcript instead.
    if not _mostly_preserved(text, out):
        return None
    return out
