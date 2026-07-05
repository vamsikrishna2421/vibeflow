"""Streaming transcription (opt-in) — transcribe COMPLETE speech chunks at full
batch quality WHILE you speak, so on release only the last chunk remains and the
paste is near-instant, instead of transcribing the whole clip after you stop.

Approach: **capped-segment streaming.** As audio accumulates, whenever there's
~SEG_SECONDS of un-transcribed speech we cut at the quietest point in the last
few seconds (a between-word micro-gap, so we don't slice a word) and transcribe
that chunk with the normal beam-search model — i.e. *batch quality*, not the
fragile word-level agreement games. Committed chunks are final; on stop only the
tail (since the last cut) is transcribed. The wait is bounded by the segment
length (~a few seconds), NOT the clip length — a 5-minute dictation no longer
means a 5-minute wait.

Opt-in (``model.streaming``) and fully defensive: any failure is raised out of
``finalize()`` so the caller falls back to a plain batch transcribe. The benefit
needs a model that runs faster than real time (small on CPU; medium on a fast
CPU/GPU) — otherwise it falls behind and the tail grows, and the caller's
short-output safety net re-does it as batch.
"""

from __future__ import annotations

import logging
import threading

_log = logging.getLogger("vibeflow")

SEG_SECONDS = 12.0        # cut a chunk once this much un-transcribed speech piles up
CUT_SEARCH_SECONDS = 3.0  # look for the quietest frame in this trailing window
MIN_SEG_SECONDS = 4.0     # never cut a chunk shorter than this
_FRAME = 0.03             # 30 ms silence-search frames


class StreamingSession:
    """Transcribes ~SEG_SECONDS speech chunks against a live Recorder while the
    user speaks; finalize() returns the full transcript."""

    def __init__(self, transcriber, recorder, prompt: str = "", interval: float = 0.7) -> None:
        self.t = transcriber
        self.recorder = recorder
        self.prompt = prompt
        self.sr = int(recorder.sample_rate)
        self.interval = float(interval)
        self._boundary = 0        # samples already transcribed (committed)
        self._parts: list = []    # committed chunk texts, in order
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None
        # CTranslate2 models aren't safe for concurrent transcribe() — the worker
        # and the final pass share this lock.
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # -- cutting ------------------------------------------------------------
    def _find_cut(self, audio, start: int) -> int:
        """Quietest 30 ms frame in the last CUT_SEARCH_SECONDS of the segment window
        — a between-word micro-gap, so we don't slice mid-word."""
        import numpy as np

        end = start + int(SEG_SECONDS * self.sr)
        lo = max(start + int(MIN_SEG_SECONDS * self.sr), end - int(CUT_SEARCH_SECONDS * self.sr))
        seg = audio[lo:end]
        fn = int(_FRAME * self.sr)
        m = (len(seg) // fn) * fn
        if m <= 0:
            return end
        rms = np.sqrt((seg[:m].reshape(-1, fn).astype("float64") ** 2).mean(axis=1))
        return lo + int(rms.argmin()) * fn

    def _transcribe(self, audio, a: int, b: int) -> None:
        chunk = audio[a:b]
        if len(chunk) < int(0.2 * self.sr):
            return
        with self._lock:
            txt = self.t.transcribe(chunk, prompt=self.prompt)
        txt = (txt or "").strip()
        if txt:
            self._parts.append(txt)

    # -- worker -------------------------------------------------------------
    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                snap = self.recorder.snapshot()
                # Emit as many full segments as have accumulated.
                while len(snap) - self._boundary >= int(SEG_SECONDS * self.sr):
                    cut = self._find_cut(snap, self._boundary)
                    if cut <= self._boundary:
                        break
                    self._transcribe(snap, self._boundary, cut)
                    self._boundary = cut
                self._stop.wait(self.interval)
        except Exception as exc:  # a bad pass must never crash the app
            self._error = exc
            _log.info("streaming: worker stopped (%s)", exc)

    def finalize(self, final_audio=None) -> str:
        """Stop the worker, transcribe the final tail, return the full transcript.
        Raises if the worker errored so the caller can fall back to batch.

        ``final_audio`` MUST be the full recording (from recorder.stop()). By the
        time we're called the live recorder has been stopped and its buffer cleared,
        so recorder.snapshot() would be empty and the tail (last segment) would be
        lost — the cause of the "missing last line" truncation."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=60)  # let the current chunk finish (no concurrency)
        if self._error:
            raise self._error
        snap = final_audio if final_audio is not None else self.recorder.snapshot()
        self._transcribe(snap, self._boundary, len(snap))  # the tail since the last cut
        self._boundary = len(snap)
        return " ".join(p for p in self._parts if p).strip()
