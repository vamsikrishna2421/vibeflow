"""Stage 4: deterministic, offline curation of raw transcripts.

Turns Whisper's raw output into tidier *written* text with **no AI**:
  * applies spoken layout commands ("new line", "new paragraph"),
  * normalises spacing around punctuation,
  * fixes the lone pronoun "i" -> "I" (and its contractions),
  * capitalises the start of sentences.

Everything here is a pure function (no I/O), so it's fast, fully offline, and
easy to unit-test. For heavier rewriting/formatting, see the optional AI layer
in :mod:`vibeflow.ai_format`.
"""

from __future__ import annotations

import re

_PARAGRAPH = re.compile(r"(?i)\bnew\s+paragraph\b")
_NEWLINE = re.compile(r"(?i)\bnew\s+line\b|\bnext\s+line\b")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.!?;:])")
_SPACE_AFTER_PUNCT = re.compile(r"([,.!?;:])(?=[^\s\d])")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_SPACE_AROUND_NL = re.compile(r"[ \t]*\n[ \t]*")
_LONE_I = re.compile(r"\bi\b")
_I_CONTRACTION = re.compile(r"\bi('(?:m|ve|ll|d|s|re))\b", re.IGNORECASE)
_AFTER_SENTENCE = re.compile(r"([.!?]\s+)([a-z])")
_AFTER_NEWLINE = re.compile(r"(\n[ \t]*)([a-z])")
_FIRST_ALPHA = re.compile(r"^(\s*)([a-z])")


def curate(
    text: str,
    *,
    spoken_commands: bool = True,
    capitalize_sentences: bool = True,
    fix_pronoun_i: bool = True,
) -> str:
    """Return a tidied version of ``text``."""
    if not text:
        return ""

    out = text
    if spoken_commands:
        out = _PARAGRAPH.sub("\n\n", out)
        out = _NEWLINE.sub("\n", out)

    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _SPACE_AFTER_PUNCT.sub(r"\1 ", out)
    out = _MULTISPACE.sub(" ", out)
    out = _SPACE_AROUND_NL.sub("\n", out)

    if fix_pronoun_i:
        out = _I_CONTRACTION.sub(lambda m: "I" + m.group(1), out)
        out = _LONE_I.sub("I", out)

    if capitalize_sentences:
        out = _capitalize(out)

    return out.strip()


def _capitalize(text: str) -> str:
    text = _FIRST_ALPHA.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _AFTER_SENTENCE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _AFTER_NEWLINE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text
