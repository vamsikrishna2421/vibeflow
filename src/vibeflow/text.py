"""Text post-processing for transcripts.

These helpers are intentionally pure (no I/O, no third-party imports) so the
trickiest part of the pipeline — turning raw Whisper output into clean,
ready-to-paste text — is easy to reason about and unit-test.
"""

from __future__ import annotations

import re

_WS_RUN = re.compile(r"[ \t\f\v]+")
_SPACE_AROUND_NL = re.compile(r" *\n *")


def clean_transcript(
    text: str | None,
    *,
    strip: bool = True,
    collapse_spaces: bool = True,
    capitalize_first: bool = False,
    remove_trailing_period: bool = False,
) -> str:
    """Normalise raw transcription text into something ready to insert.

    Whisper-style models return segments that often carry leading spaces and
    inconsistent internal whitespace. This collapses runs of spaces/tabs,
    tidies whitespace around newlines, and applies a few optional niceties.

    Args:
        text: Raw transcript (may be ``None`` or empty).
        strip: Trim leading/trailing whitespace from the final string.
        collapse_spaces: Collapse runs of spaces/tabs into single spaces.
        capitalize_first: Upper-case the first alphabetic character.
        remove_trailing_period: Drop a single trailing full stop (handy when
            dictating into chat boxes where you add your own punctuation).

    Returns:
        A cleaned string. Never ``None``.
    """
    if not text:
        return ""

    out = text.replace("\r\n", "\n").replace("\r", "\n")

    if collapse_spaces:
        out = _WS_RUN.sub(" ", out)
        out = _SPACE_AROUND_NL.sub("\n", out)

    if strip:
        out = out.strip()

    if remove_trailing_period and out.endswith("."):
        out = out[:-1].rstrip()

    if capitalize_first and out:
        out = _capitalize_first(out)

    return out


def _capitalize_first(text: str) -> str:
    """Upper-case the first letter without touching the rest of the string."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1 :]
    return text


def with_trailing_space(text: str, enabled: bool) -> str:
    """Append a single trailing space when enabled and not already present.

    Useful when typing into a document so consecutive dictations don't run
    their words together.
    """
    if not enabled or not text:
        return text
    return text if text.endswith((" ", "\n")) else text + " "


def expand_snippets(text: str, snippets: dict | None) -> str:
    """Replace spoken shortcut phrases with their expansions.

    ``snippets`` maps a trigger phrase to its replacement, e.g.
    ``{"my email": "vamsy@example.com", "my address": "1 Main St"}``. Matching is
    case-insensitive and whole-phrase (a trigger only fires on word boundaries, so
    "email" never fires inside "emails"). Longer triggers are tried first so
    "my work email" wins over "my email". With no snippets the text is unchanged,
    which is why the feature is safe to leave always-on: an empty map is a no-op.
    """
    if not text or not snippets:
        return text
    out = text
    for trigger in sorted(
        (k for k in snippets if isinstance(k, str) and k.strip()),
        key=len,
        reverse=True,
    ):
        repl = snippets.get(trigger)
        if repl is None:
            continue
        pattern = re.compile(
            r"(?<!\w)" + re.escape(trigger.strip()) + r"(?!\w)", re.IGNORECASE
        )
        out = pattern.sub(lambda _m, r=str(repl): r, out)
    return out


def preview(text: str, limit: int = 60) -> str:
    """Return a short single-line preview for notifications/logging."""
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"  # ellipsis
