"""Tests for silence detection — telling a blocked/muted mic (silent stream)
apart from a working mic that simply caught no recognisable speech."""

import numpy as np

from vibeflow.audio import SILENCE_PEAK, is_silent, peak_level


def test_peak_level_empty_or_invalid():
    assert peak_level(np.zeros(0, dtype="float32")) == 0.0
    assert peak_level(None) == 0.0
    assert peak_level([]) == 0.0


def test_peak_level_reports_loudest_sample():
    a = np.array([0.0, -0.3, 0.2, 0.5, -0.1], dtype="float32")
    assert peak_level(a) == 0.5


def test_silent_stream_is_silent():
    # A blocked/muted mic delivers exact zeros (or denormal noise) for a real
    # duration of audio — long enough to pass the "too short" gate.
    silent = np.zeros(16000, dtype="float32")  # 1.0s at 16 kHz, all zeros
    assert is_silent(silent) is True
    tiny = np.full(16000, 1e-6, dtype="float32")
    assert is_silent(tiny) is True


def test_real_signal_is_not_silent():
    # Even quiet speech/room tone from a live mic clears the threshold easily.
    quiet = np.full(16000, 5e-3, dtype="float32")
    assert is_silent(quiet) is False
    speech = (np.sin(np.linspace(0, 200, 16000)) * 0.2).astype("float32")
    assert is_silent(speech) is False
    assert peak_level(speech) >= SILENCE_PEAK


def test_threshold_boundary():
    assert is_silent(np.full(10, SILENCE_PEAK / 2, dtype="float32")) is True
    assert is_silent(np.full(10, SILENCE_PEAK * 2, dtype="float32")) is False
