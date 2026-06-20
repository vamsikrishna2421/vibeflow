"""Adaptive vocabulary — learn the user's frequent terms and bias Whisper toward
them (via ``initial_prompt``), so names/jargon transcribe better over time.

Two learning signals:

* **Teach-back (strongest, deterministic).** When the user edits VibeFlow's
  output and copies/cuts the result, we diff old vs new and learn the corrected
  words. Because we learn from the *corrected* text, we capture the *right*
  spelling — never Whisper's mistake. No LLM required.
* **Safe frequency (weak).** Recurring "term-like" words (CamelCase, ACRONYMs,
  identifiers, things with digits) from finished transcripts. A plausibility
  gate keeps one-off gibberish out.

Stored at ``%APPDATA%\\VibeFlow\\vocabulary.json``. Pure logic + file I/O, so the
learning rules are easy to unit-test.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'._\-]*")
MAX_TERMS = 60  # cap for the initial_prompt (Whisper prompt budget is limited)


def _words(text: str):
    return _WORD.findall(text or "")


def is_termlike(word: str) -> bool:
    """A name/jargon/acronym/identifier rather than an ordinary word."""
    if len(word) < 2:
        return False
    if re.search(r"[a-z][A-Z]", word):          # CamelCase / kubeCtl
        return True
    if word.isupper() and word.isalpha():        # ACRONYM
        return True
    if re.search(r"\d", word):                   # has a digit (v3, oauth2)
        return True
    if len(word) > 2 and re.search(r"[._\-]", word[1:-1]):  # foo.bar, a_b
        return True
    return False


class Vocabulary:
    """A weighted, persisted set of the user's domain terms."""

    def __init__(self, path: str | Path | None = None, seed=None) -> None:
        self.path = Path(path) if path else None
        self.terms: dict = {}  # lowercase key -> {"term": display, "w": int, "t": ts}
        self._load()
        for term in seed or []:
            self.add(term, weight=5)

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        try:
            if self.path and self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data.get("terms"), dict):
                    self.terms = data["terms"]
        except Exception:
            self.terms = {}

    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"terms": self.terms}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # -- learning ------------------------------------------------------
    def add(self, term: str, weight: int = 1) -> bool:
        term = (term or "").strip().strip(".,!?;:\"'()[]{}")
        if not (2 <= len(term) <= 40) or not _WORD.fullmatch(term):
            return False
        key = term.lower()
        entry = self.terms.get(key)
        if entry:
            entry["w"] += weight
            entry["t"] = time.time()
            # Prefer a more specific spelling if the new one looks term-like.
            if is_termlike(term) and not is_termlike(entry["term"]):
                entry["term"] = term
        else:
            self.terms[key] = {"term": term, "w": weight, "t": time.time()}
        return True

    def learn_from_text(self, text: str) -> int:
        """Safe frequency: only clearly term-like words."""
        learned = 0
        for word in _words(text):
            if is_termlike(word) and self.add(word, 1):
                learned += 1
        if learned:
            self._prune()
        return learned

    def learn_from_correction(self, original: str, corrected: str) -> list:
        """Teach-back: diff old vs new output; learn the corrected words."""
        old, new = _words(original), _words(corrected)
        matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        learned = []
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                for word in new[j1:j2]:
                    # Strong signal: learn the user's spelling (weight high).
                    if self.add(word, weight=4):
                        learned.append(word)
        if learned:
            self._prune()
        return learned

    # -- use -----------------------------------------------------------
    def prompt(self) -> str:
        """The ``initial_prompt`` string biasing Whisper toward top terms."""
        if not self.terms:
            return ""
        top = sorted(
            self.terms.values(), key=lambda e: (e["w"], e["t"]), reverse=True
        )[:MAX_TERMS]
        return "Vocabulary: " + ", ".join(e["term"] for e in top) + "."

    def _prune(self) -> None:
        if len(self.terms) <= MAX_TERMS * 3:
            return
        kept = sorted(
            self.terms.items(), key=lambda kv: (kv[1]["w"], kv[1]["t"]), reverse=True
        )[: MAX_TERMS * 2]
        self.terms = dict(kept)
