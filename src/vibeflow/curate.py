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

# Deterministic OFFLINE fallback for filler removal (used only when the AI
# formatter is OFF; when AI is on, the local LLM removes fillers context-aware).
# Intentionally CONSERVATIVE per a 4-architect adversarial design review:
#   * list trimmed to unambiguous vocalized non-words (NO "er"/"erm": they
#     collide with ER / extended-release / Erbium / "git-er-done");
#   * whitespace/edge-anchored (NOT \b) so "uh-huh", "(um)", '"um"', "um.",
#     "git-er-done" are never touched;
#   * comma-bracketed fillers ("we should, uh, deploy"; "milk, um, eggs") are
#     LEFT ALONE (list-vs-disfluency is undecidable without semantics) — never
#     merges a list, never leaves a stray comma;
#   * newlines preserved; a filler-only line is dropped; no capitalization here.
FILLERS_DEFAULT = ("um", "uh", "umm", "uhh", "uhm")


def remove_fillers(text: str, fillers=None) -> str:
    """Strip standalone vocalized fillers (um, uh, ...) — conservative & offline."""
    if not text:
        return text
    fl = sorted(fillers or FILLERS_DEFAULT, key=len, reverse=True)
    alt = "|".join(re.escape(f) for f in fl)
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # CRLF/CR -> LF

    only_line = re.compile(rf"[ \t,]*(?:{alt})(?:[ \t,]+(?:{alt}))*[ \t,]*", re.IGNORECASE)
    leading = re.compile(rf"^[ \t]*(?:{alt})(?:[ \t]*,)?(?=[ \t]|$)", re.IGNORECASE)
    internal = re.compile(rf"[ \t]+(?:{alt})(?=[ \t])", re.IGNORECASE)
    # F1: absorb a glued preceding comma ("ship it, um" -> "ship it", not "ship it,").
    # The [ \t]+ before the filler still guards against matching inside a word
    # ("scrum" is never touched). Punctuation-adjacent INTERNAL fillers ("well um,")
    # are intentionally left (keeps comma-bracketed protection) — documented.
    trailing = re.compile(rf"[ \t]*,?[ \t]+(?:{alt})[ \t]*$", re.IGNORECASE)
    collapse = re.compile(r"[ \t]{2,}")

    out_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and only_line.fullmatch(stripped):
            continue  # whole line is just fillers -> drop it (no blank line left)
        line = leading.sub("", line)
        prev = None
        while prev != line:  # fixpoint: clear consecutive fillers ("um uh")
            prev = line
            line = internal.sub("", line)
        line = trailing.sub("", line)
        out_lines.append(collapse.sub(" ", line).strip(" \t"))
    return "\n".join(out_lines)


_PARAGRAPH = re.compile(r"(?i)\bnew\s+paragraph\b")
_NEWLINE = re.compile(r"(?i)\bnew\s+line\b|\bnext\s+line\b")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.!?;:])")
_SPACE_AFTER_PUNCT = re.compile(r"([,.!?;:])(?=[^\s\d])")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_SPACE_AROUND_NL = re.compile(r"[ \t]*\n[ \t]*")
_LONE_I = re.compile(r"\bi\b")
_I_CONTRACTION = re.compile(r"\bi('(?:m|ve|ll|d|s|re))\b", re.IGNORECASE)
# The trailing (?=[a-z]*\b) only matches a lowercase letter that begins an
# all-lowercase word, so case-bearing tokens (iOS, pH, eBay, tPA) are never
# force-capitalized at a sentence start.
_AFTER_SENTENCE = re.compile(r"([.!?]\s+)([a-z])(?=[a-z]*\b)")
_AFTER_NEWLINE = re.compile(r"(\n[ \t]*)([a-z])(?=[a-z]*\b)")
_FIRST_ALPHA = re.compile(r"^(\s*)([a-z])(?=[a-z]*\b)")


def curate(
    text: str,
    *,
    spoken_commands: bool = True,
    capitalize_sentences: bool = True,
    fix_pronoun_i: bool = True,
    strip_fillers: bool = False,
    fillers=None,
) -> str:
    """Return a tidied version of ``text``."""
    if not text:
        return ""

    out = text
    if strip_fillers:
        out = remove_fillers(out, fillers)
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
