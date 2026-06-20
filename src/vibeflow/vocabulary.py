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
import logging
import re
import time
from pathlib import Path

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'._\-]*")
MAX_TERMS = 60  # cap for the initial_prompt (Whisper prompt budget is limited)

# Header for the friendly, user-editable word list (see write_wordlist).
WORDLIST_HEADER = (
    "# VibeFlow vocabulary — the words it has learned to spell from your speech.\n"
    "#\n"
    "#   - Delete a line (then save) to make VibeFlow FORGET that word.\n"
    "#   - Add your own words, one per line, to TEACH them directly.\n"
    "#   - Just save and close — your changes apply automatically.\n"
    "#\n"
    "# Lines starting with '#' and blank lines are ignored.\n"
    "# ---------------------------------------------------------------------\n"
)

# Ordinary function words we must never learn as "vocabulary" (they would just
# waste the prompt budget and bias Whisper toward noise).
_STOPWORDS = frozenset(
    """
    a an and the this that these those of to in on at by for with from into onto
    out up off over under above below as is are was were be been being am do does
    did has have had having will would shall should can could may might must not
    no nor so if then than too very just also still even here there it its it's
    i you he she we they them him her us my your his our their me what which who
    whom whose when where why how all any each few more most some such only own
    same about after before between through during again once because while until
    """.split()
)


def _words(text: str):
    return _WORD.findall(text or "")


def _clean(word: str) -> str:
    """Strip surrounding punctuation from a token."""
    return (word or "").strip(".,!?;:\"'()[]{}").strip()


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


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
        self._mtime = self._file_mtime()
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
            self._mtime = self._file_mtime()
        except Exception:
            pass

    def _file_mtime(self):
        try:
            return self.path.stat().st_mtime if self.path and self.path.exists() else None
        except Exception:
            return None

    def reload_if_changed(self) -> bool:
        """Re-read the store if the file changed underneath us (e.g. the
        vocabulary manager window deleted some words). Returns True if reloaded.
        """
        m = self._file_mtime()
        if m is not None and m != self._mtime:
            self._load()
            self._mtime = m
            return True
        return False

    # -- viewing / pruning (user-friendly) -----------------------------
    def list_terms(self) -> list:
        """All learned display terms, sorted case-insensitively."""
        return sorted((e["term"] for e in self.terms.values()), key=str.lower)

    def remove(self, term: str) -> bool:
        """Forget a single term. Returns True if it was present."""
        key = (term or "").strip().lower()
        if key in self.terms:
            del self.terms[key]
            return True
        return False

    def write_wordlist(self, path) -> Path:
        """Write a friendly, editable word list (one term per line)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(self.list_terms())
        path.write_text(WORDLIST_HEADER + body + "\n", encoding="utf-8")
        return path

    def sync_from_wordlist(self, path) -> tuple:
        """Reconcile the vocabulary with a user-edited word list.

        Words the user removed from the file are forgotten; words they added are
        learned (weight 5). Returns ``(added, removed)``. Existing words keep
        their learned weight. Comments (``#``) and blank lines are ignored.
        """
        path = Path(path)
        if not path.exists():
            return (0, 0)
        wanted = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                wanted.append(s)
        wanted_keys = {w.lower() for w in wanted}
        removed = 0
        for key in list(self.terms.keys()):
            if key not in wanted_keys:
                del self.terms[key]
                removed += 1
        added = 0
        for w in wanted:
            if w.lower() not in self.terms and self.add(w, weight=5):
                added += 1
        return (added, removed)

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

    def _should_learn(self, word: str, context):
        """Return the cleaned term to learn, or ``None``.

        A corrected word is worth learning only when it is a genuine term —
        either *term-like* (CamelCase / ACRONYM / has-digit / dotted) or the
        corrected spelling of a *similar-looking* word from our output (the
        mistake it replaced, e.g. ``kubectl`` for ``CubeCTL``). Stop-words,
        very short words and stray fragments are rejected so we never bias
        Whisper toward noise.
        """
        w = _clean(word)
        if not (3 <= len(w) <= 40):
            return None
        if w.lower() in _STOPWORDS:
            return None
        if is_termlike(w):
            return w
        for other in context:
            oc = _clean(other)
            if oc.lower() != w.lower() and _similar(oc, w) >= 0.6:
                return w
        return None

    def learn_from_correction(self, original: str, corrected: str) -> list:
        """Teach-back: learn the *terms* the user fixed in our output.

        We compare word-by-word rather than by positional diff (which mis-aligns
        and flags unchanged words). For each word in the corrected text that is
        **not already in our output**, we learn it when :meth:`_should_learn`
        accepts it. This handles both a whole edited sentence and a single
        copied term, and never re-learns words that were already correct.
        """
        ctx = _words(original)
        ctx_lower = {_clean(w).lower() for w in ctx}
        candidates, learned = [], []
        for raw in _words(corrected):
            candidates.append(raw)
            if _clean(raw).lower() in ctx_lower:
                continue  # already present in our output — not a correction
            term = self._should_learn(raw, ctx)
            if term and self.add(term, weight=4):
                learned.append(term)
        if learned:
            self._prune()
        logging.getLogger("vibeflow").info(
            "teach-back diff: candidates=%s learned=%s", candidates, learned
        )
        return learned

    def learn_terms(self, terms) -> list:
        """Add LLM-identified technical terms from the user's corrected text.

        The model already judged what is technical; we split any multi-word
        phrases into tokens and apply only light hygiene (length, stop-words)
        before adding. Returns the list of terms actually stored.
        """
        learned = []
        for term in terms or []:
            for raw in _words(term):  # split "GitHub Actions" -> GitHub, Actions
                w = _clean(raw)
                if not (2 <= len(w) <= 40) or w.lower() in _STOPWORDS:
                    continue
                if self.add(w, weight=4):
                    learned.append(w)
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
