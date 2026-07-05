"""Streaming transcription (opt-in) — commit stable text WHILE the user speaks,
so on release only a short tail remains and the paste is near-instant, instead of
transcribing the whole clip after stop.

Algorithm: **LocalAgreement-2** (whisper_streaming / UFAL). The growing audio
buffer is re-transcribed periodically; a word is COMMITTED only once two
consecutive re-transcriptions agree on it (their common prefix). Committed audio
is trimmed from the buffer so each pass stays cheap. This turns a batch model
(Whisper) into a stable low-latency streamer.

Opt-in (``model.streaming``) and fully defensive: any failure is raised out of
``finalize()`` so the caller falls back to a plain batch transcribe — streaming
can never break dictation. Whisper engine only (needs word timestamps).

Note: the benefit scales with how fast the model runs. If the model can't
transcribe faster than real time (e.g. large-v3 on a slow CPU), the worker falls
behind and most work happens in the final pass — still correct, just less of a
latency win. Faster models (small/medium) or a GPU get the full effect.
"""

from __future__ import annotations

import logging
import threading

_log = logging.getLogger("vibeflow")


class _HypothesisBuffer:
    """LocalAgreement-2: commit the longest prefix two successive hypotheses share."""

    def __init__(self) -> None:
        self.committed: list = []      # (start, end, word) confirmed for good
        self.buffer: list = []         # previous hypothesis' uncommitted tail
        self.new: list = []            # current hypothesis' uncommitted tail
        self.last_committed_time = 0.0

    def insert(self, words, offset: float) -> None:
        words = [(s + offset, e + offset, w) for (s, e, w) in words]
        # Keep only words at/after the committed frontier.
        self.new = [x for x in words if x[0] > self.last_committed_time - 0.1]
        # De-dup: if the head of `new` repeats the tail of what we already committed
        # (the re-transcribed window overlaps), drop the repeated words.
        if self.committed and self.new:
            for n in range(1, min(len(self.committed), len(self.new), 5) + 1):
                tail = " ".join(w for (_, _, w) in self.committed[-n:]).strip()
                head = " ".join(w for (_, _, w) in self.new[:n]).strip()
                if tail and tail == head:
                    del self.new[:n]
                    break

    def flush(self) -> list:
        """Commit the common prefix of the current and previous hypotheses."""
        committed = []
        while self.new and self.buffer:
            if self.new[0][2] == self.buffer[0][2]:
                w = self.new.pop(0)
                self.buffer.pop(0)
                committed.append(w)
                self.last_committed_time = w[1]
            else:
                break
        self.buffer = self.new
        self.new = []
        self.committed.extend(committed)
        return committed


class OnlineProcessor:
    """Feeds the growing audio into the transcriber and commits stable words."""

    def __init__(self, transcriber, prompt: str = "", sample_rate: int = 16000) -> None:
        self.t = transcriber
        self.prompt = prompt
        self.sr = int(sample_rate)
        self.audio = None            # numpy float32 — the uncommitted rolling window
        self.offset = 0.0            # seconds already trimmed away (committed)
        self.hyp = _HypothesisBuffer()
        # CTranslate2 models are NOT safe for concurrent transcribe() calls. The
        # worker and the final pass both touch the model, so serialize them.
        self._model_lock = threading.Lock()

    def insert_audio(self, chunk) -> None:
        import numpy as np

        self.audio = chunk.copy() if self.audio is None else np.append(self.audio, chunk)

    def process(self) -> None:
        if self.audio is None or len(self.audio) < self.sr // 2:  # <0.5 s → wait
            return
        with self._model_lock:
            words = self.t.transcribe_words(self.audio, prompt=self.prompt)
        self.hyp.insert(words, self.offset)
        committed = self.hyp.flush()
        if committed:
            self._trim(committed[-1][1])

    def _trim(self, at_time: float) -> None:
        cut = at_time - self.offset
        n = int(cut * self.sr)
        if 0 < n <= (0 if self.audio is None else len(self.audio)):
            self.audio = self.audio[n:]
            self.offset = at_time

    def finish(self) -> str:
        # Final pass on the remaining tail, then join committed + last hypothesis.
        try:
            if self.audio is not None and len(self.audio) > 0:
                with self._model_lock:
                    words = self.t.transcribe_words(self.audio, prompt=self.prompt)
                self.hyp.insert(words, self.offset)
                self.hyp.flush()
        except Exception as exc:
            _log.info("streaming: final pass failed (%s)", exc)
        allw = list(self.hyp.committed) + list(self.hyp.buffer)
        return "".join(w for (_, _, w) in allw).strip()


class StreamingSession:
    """Runs an OnlineProcessor worker against a live Recorder while the user speaks."""

    def __init__(self, transcriber, recorder, prompt: str = "", interval: float = 0.9) -> None:
        self.proc = OnlineProcessor(transcriber, prompt=prompt, sample_rate=recorder.sample_rate)
        self.recorder = recorder
        self.interval = float(interval)
        self._fed = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        snap = self.recorder.snapshot()
        if len(snap) > self._fed:
            self.proc.insert_audio(snap[self._fed:])
            self._fed = len(snap)

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._drain()
                self.proc.process()
                self._stop.wait(self.interval)
        except Exception as exc:  # a bad pass shouldn't crash the app
            self._error = exc
            _log.info("streaming: worker stopped (%s)", exc)

    def finalize(self) -> str:
        """Stop the worker, drain remaining audio, return the full transcript.
        Raises if the worker errored so the caller can fall back to batch."""
        self._stop.set()
        if self._thread:
            # Wait for the worker to finish its current (possibly slow) pass, so the
            # final pass never runs the model concurrently with it.
            self._thread.join(timeout=30)
        if self._error:
            raise self._error
        self._drain()
        return self.proc.finish()
