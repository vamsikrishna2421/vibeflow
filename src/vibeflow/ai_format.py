"""Optional AI text formatting via a **local** LLM.

This is the "voice-to-text *with AI*" mode — entirely opt-in. When
``ai.enabled`` is true, the curated transcript is sent to a local LLM (Ollama by
default, running on your own machine) which rewrites it into clean, well-
formatted prose. Nothing leaves your computer.

Design notes:
  * Uses only the standard library (``urllib``) — no extra dependency.
  * Fully defensive: any error/timeout/missing server returns ``None`` and the
    caller simply keeps the plain (deterministically-curated) transcript. AI can
    only *improve* output, never break dictation.
  * Ollama is a free, one-command local LLM runner: https://ollama.com
"""

from __future__ import annotations

import json
import urllib.request

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"  # benchmark winner: fast, tiny, clean, reliable

_DEFAULT_PROMPT = (
    "You clean up dictated text. Rewrite the text below with correct "
    "capitalization, punctuation, and paragraph breaks, and fix obvious "
    "speech-to-text errors. Preserve the original meaning and wording as much as "
    "possible. Do not add commentary, explanations, or quotation marks. Output "
    "ONLY the cleaned-up text."
)


def is_enabled(cfg) -> bool:
    return bool(cfg.get("ai.enabled", False))


def format_text(text: str, cfg) -> str | None:
    """Return an AI-formatted version of ``text``, or ``None`` to fall back."""
    if not text or not is_enabled(cfg):
        return None
    provider = str(cfg.get("ai.provider", "ollama")).lower()
    try:
        if provider == "ollama":
            return _ollama_generate(text, cfg)
        return None
    except Exception as exc:  # never break dictation because of AI
        _warn(f"AI formatting unavailable ({exc}); using plain transcript")
        return None


def _ollama_generate(text: str, cfg) -> str | None:
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    model = str(cfg.get("ai.model", DEFAULT_MODEL))
    timeout = float(cfg.get("ai.timeout", 20))
    prompt = (cfg.get("ai.prompt") or "").strip() or _DEFAULT_PROMPT

    payload = {
        "model": model,
        "prompt": f"{prompt}\n\nText:\n{text}\n\nCleaned text:",
        "stream": False,
        "options": {"temperature": 0.2},
    }
    body = _post_json(f"{endpoint}/api/generate", payload, timeout)
    result = (body.get("response") or "").strip()
    return result or None


def check(cfg) -> tuple[bool, str]:
    """Connectivity test for the local LLM. Returns ``(ok, message)``."""
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    model = str(cfg.get("ai.model", DEFAULT_MODEL))
    try:
        body = _get_json(f"{endpoint}/api/tags", timeout=5)
        names = [m.get("name", "") for m in body.get("models", [])]
        if not names:
            return False, (
                f"Ollama is running at {endpoint} but has no models. "
                f"Run:  ollama pull {model}"
            )
        has = any(n == model or n.startswith(model.split(":")[0]) for n in names)
        return True, (
            f"Connected to Ollama at {endpoint}. Models: {', '.join(names)}. "
            + ("Selected model is available." if has else f"Run: ollama pull {model}")
        )
    except Exception as exc:
        return False, (
            f"Could not reach a local LLM at {endpoint}: {exc}\n"
            "Install Ollama from https://ollama.com, then run 'ollama serve' "
            f"and 'ollama pull {model}'."
        )


# ---------------------------------------------------------------------------
# Tiny HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------
def _post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _warn(message: str) -> None:
    try:
        import logging

        logging.getLogger("vibeflow").warning(message)
    except Exception:
        pass
