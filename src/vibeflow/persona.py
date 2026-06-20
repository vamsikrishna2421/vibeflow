"""Persona profiling — learn the user's domain, genre and tone from their own
dictation history, then feed a short profile to the AI formatter so the output
reads more like *them*.

Fully local and **opt-in**. Privacy by design:

* Only a small, **capped** rolling window of recent finished transcripts is kept
  (``%APPDATA%\\VibeFlow\\persona.json``) — nothing is uploaded, ever.
* The distilled profile is a couple of sentences, regenerated locally by the
  same on-device LLM used elsewhere.
* The user can view or clear both the samples and the profile at any time.

This module is pure storage + logic (no network, no LLM); the actual
summarisation lives in :func:`vibeflow.ai_format.build_persona_profile`, so the
rules here stay easy to unit-test.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

MAX_SAMPLES = 50          # rolling window of recent dictations we retain
REPROFILE_EVERY = 12      # re-summarise after this many *new* samples
MIN_SAMPLES = 5           # need at least this many before the first profile
MIN_SAMPLE_LEN = 25       # ignore trivially short dictations
MAX_SAMPLE_LEN = 2000     # and cap very long ones (privacy + prompt budget)


class Persona:
    """A capped sample window plus the distilled style profile, persisted."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.samples: list = []   # [{"t": ts, "text": str}, ...]
        self.profile: str = ""    # the distilled profile string
        self.profiled_count: int = 0  # number of samples at last profiling
        self._load()

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        try:
            if self.path and self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.samples = data.get("samples") or []
                self.profile = data.get("profile") or ""
                self.profiled_count = int(data.get("profiled_count") or 0)
        except Exception:
            self.samples, self.profile, self.profiled_count = [], "", 0

    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {
                        "samples": self.samples,
                        "profile": self.profile,
                        "profiled_count": self.profiled_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # -- sample collection ---------------------------------------------
    def add_sample(self, text: str) -> bool:
        """Record a finished transcript. Returns True if it was kept."""
        t = (text or "").strip()
        if not (MIN_SAMPLE_LEN <= len(t) <= MAX_SAMPLE_LEN):
            return False
        self.samples.append({"t": time.time(), "text": t})
        if len(self.samples) > MAX_SAMPLES:
            self.samples = self.samples[-MAX_SAMPLES:]
        return True

    def sample_texts(self) -> list:
        return [s.get("text", "") for s in self.samples]

    # -- profiling -----------------------------------------------------
    def needs_profile(self) -> bool:
        """Time to (re)build the profile?"""
        if len(self.samples) < MIN_SAMPLES:
            return False
        if not self.profile:
            return True
        return (len(self.samples) - self.profiled_count) >= REPROFILE_EVERY

    def set_profile(self, profile: str) -> None:
        self.profile = (profile or "").strip()
        self.profiled_count = len(self.samples)

    def profile_text(self) -> str:
        return self.profile

    # -- viewing / clearing --------------------------------------------
    def clear(self) -> None:
        self.samples = []
        self.profile = ""
        self.profiled_count = 0
