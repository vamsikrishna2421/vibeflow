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


def format_text(text: str, cfg, persona: str | None = None) -> str | None:
    """Return an AI-formatted version of ``text``, or ``None`` to fall back.

    When ``persona`` (a short profile of the user's domain/tone) is given, the
    formatter is nudged to keep the output in the user's voice.
    """
    if not text or not is_enabled(cfg):
        return None
    provider = str(cfg.get("ai.provider", "ollama")).lower()
    try:
        if provider == "ollama":
            return _ollama_generate(text, cfg, persona=persona)
        return None
    except Exception as exc:  # never break dictation because of AI
        _warn(f"AI formatting unavailable ({exc}); using plain transcript")
        return None


def _ollama_generate(text: str, cfg, persona: str | None = None) -> str | None:
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    model = str(cfg.get("ai.model", DEFAULT_MODEL))
    timeout = float(cfg.get("ai.timeout", 20))
    prompt = (cfg.get("ai.prompt") or "").strip() or _DEFAULT_PROMPT
    if persona and persona.strip():
        prompt = (
            f"{prompt}\n\nContext about the author (match their voice and "
            f"terminology, do not mention this context): {persona.strip()}"
        )

    payload = {
        "model": model,
        "prompt": f"{prompt}\n\nText:\n{text}\n\nCleaned text:",
        "stream": False,
        "options": {"temperature": 0.2},
    }
    body = _post_json(f"{endpoint}/api/generate", payload, timeout)
    result = (body.get("response") or "").strip()
    return result or None


_PERSONA_PROMPT = (
    "Below are short samples of one person's dictated text. In 2-3 sentences, "
    "describe their professional domain or sector, the kind of content they "
    "usually produce, and their tone and style. Be specific and concise. Start "
    "with 'The user'. Do NOT quote or list the samples back.\n\n"
    "Samples:\n{samples}\n\nProfile:"
)


def build_persona_profile(samples, cfg, timeout: float | None = None):
    """Summarise the user's dictation samples into a short style profile.

    Returns a profile string, or ``None`` when no local LLM is reachable or
    there isn't enough material. Never raises. Uses the more accurate extraction
    model (qwen2.5:3b when present) since this is a background task.
    """
    texts = [s for s in (samples or []) if s and s.strip()]
    if len(texts) < 3:
        return None
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    model = _pick_extract_model(cfg)
    if not model:
        return None
    t = float(timeout if timeout is not None else cfg.get("ai.teach_back_timeout", 30))
    joined = "\n".join(f"- {s.strip()}" for s in texts[-30:])
    payload = {
        "model": model,
        "prompt": _PERSONA_PROMPT.format(samples=joined),
        "stream": False,
        "options": {"temperature": 0.3},
    }
    try:
        body = _post_json(f"{endpoint}/api/generate", payload, t)
    except Exception as exc:
        _warn(f"persona profiling unavailable ({exc})")
        return None
    profile = (body.get("response") or "").strip()
    # Keep it short and clean (defensive against a chatty model).
    if not profile:
        return None
    return profile[:600]


# ---------------------------------------------------------------------------
# Teach-back: let the local LLM pick the technical terms out of corrected text
# ---------------------------------------------------------------------------
# A slightly larger model is far more *precise* at telling technical terms from
# ordinary words (qwen2.5:1.5b misses terms and hallucinates "tool"/"quarterly";
# qwen2.5:3b is clean). Teach-back runs in the background, so the extra latency
# is invisible — we prefer the more accurate model when it is installed.
EXTRACT_MODEL_PREFERENCE = ("qwen2.5:3b", "gemma2:2b", "qwen2.5:1.5b")

_EXTRACT_PROMPT = (
    "You extract technical vocabulary from text. List the technical terms - "
    "product names, tools, commands, libraries, frameworks, acronyms, file or "
    "function names, and domain jargon - that a dictation system should remember "
    "how to spell. Ignore ordinary English words like 'tool', 'report', "
    "'quarterly', 'meeting'. Reply with ONLY a comma-separated list of those "
    "terms exactly as written, nothing else. If there are none, reply NONE.\n\n"
    "Example text: Restart the Nginx server and run the database migration with Alembic.\n"
    "Example answer: Nginx, Alembic\n\n"
    "Text: {text}\nAnswer:"
)


def installed_models(cfg) -> list:
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    body = _get_json(f"{endpoint}/api/tags", timeout=5)
    return [m.get("name", "") for m in body.get("models", [])]


def _pick_extract_model(cfg):
    """Choose the most accurate *installed* model for term extraction."""
    try:
        names = installed_models(cfg)
    except Exception:
        return None
    if not names:
        return None
    preferred = str(cfg.get("text.teach_back_model", "") or "").strip()
    order = ([preferred] if preferred else []) + list(EXTRACT_MODEL_PREFERENCE)
    order.append(str(cfg.get("ai.model", DEFAULT_MODEL)))
    for want in order:
        if not want:
            continue
        for n in names:
            if n == want or n == f"{want}:latest" or n.split(":")[0] == want.split(":")[0]:
                return n
    return names[0]


def extract_terms(corrected: str, cfg, timeout: float | None = None):
    """Ask a local LLM which words in ``corrected`` are technical terms to learn.

    Returns a list of terms (possibly empty) when a local LLM answered, or
    ``None`` when no local LLM is reachable — so the caller can fall back to the
    deterministic teach-back learner. Never raises.
    """
    if not corrected or not corrected.strip():
        return []
    endpoint = str(cfg.get("ai.endpoint", DEFAULT_ENDPOINT)).rstrip("/")
    model = _pick_extract_model(cfg)
    if not model:
        return None
    t = float(timeout if timeout is not None else cfg.get("ai.teach_back_timeout", 30))
    payload = {
        "model": model,
        "prompt": _EXTRACT_PROMPT.format(text=corrected.strip()),
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        body = _post_json(f"{endpoint}/api/generate", payload, t)
    except Exception as exc:
        _warn(f"teach-back term extraction unavailable ({exc}); using deterministic fallback")
        return None
    return _parse_terms(body.get("response") or "", corrected)


def _parse_terms(raw: str, source: str) -> list:
    """Parse the model's comma-separated answer into validated terms.

    Only terms that actually appear in ``source`` are kept (anti-hallucination).
    """
    answer = (raw or "").strip()
    if not answer or answer.upper().startswith("NONE"):
        return []
    src_low = source.lower()
    out, seen = [], set()
    for piece in answer.replace("\n", ",").split(","):
        term = piece.strip().strip("\"'`.;:()[]{}").strip()
        if not term or len(term) > 60:
            continue
        if term.lower() not in src_low:      # must be a word from the user's text
            continue
        if term.lower() in seen:
            continue
        seen.add(term.lower())
        out.append(term)
    return out[:12]


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
