"""Tests for silence detection — telling a blocked/muted mic (silent stream)
apart from a working mic that simply caught no recognisable speech."""

import numpy as np

from vibeflow.audio import (
    SILENCE_PEAK,
    _normalize_device,
    input_devices,
    is_silent,
    peak_level,
)


def test_normalize_device():
    # "default"/blank/None -> None (let the backend pick the Windows default).
    assert _normalize_device("default") is None
    assert _normalize_device("") is None
    assert _normalize_device(None) is None
    # A numeric string or int -> an index; a name -> kept as a substring match.
    assert _normalize_device(3) == 3
    assert _normalize_device("5") == 5
    assert _normalize_device("Microphone Array (Realtek)") == "Microphone Array (Realtek)"


def _mock_devices(monkeypatch, devices):
    import sys

    class _SD:
        @staticmethod
        def query_devices():
            return devices

    monkeypatch.setitem(sys.modules, "sounddevice", _SD)


def test_builtin_mic_prefers_internal_over_bluetooth(monkeypatch):
    import vibeflow.audio as a

    _mock_devices(monkeypatch, [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Headset Hands-Free (realme)", "max_input_channels": 1},
        {"name": "Microphone Array (Intel Smart Sound)", "max_input_channels": 2},
        {"name": "Microphone Array (Intel Smart Sound)", "max_input_channels": 2},
    ])
    assert a._builtin_mic_index() == 2  # the internal mic, never the headset


def test_builtin_mic_fallback_then_none(monkeypatch):
    import vibeflow.audio as a

    # No obviously-built-in device, but a plain USB mic -> use it (first non-avoided).
    _mock_devices(monkeypatch, [
        {"name": "Headset Hands-Free", "max_input_channels": 1},
        {"name": "USB Audio Device", "max_input_channels": 1},
    ])
    assert a._builtin_mic_index() == 1
    # Only avoided devices (BT / loopback) -> None, so the OS default decides.
    _mock_devices(monkeypatch, [
        {"name": "Bluetooth Hands-Free (AirPods)", "max_input_channels": 1},
        {"name": "Stereo Mix", "max_input_channels": 2},
    ])
    assert a._builtin_mic_index() is None


def test_resolve_input_device_modes(monkeypatch):
    import vibeflow.audio as a

    _mock_devices(monkeypatch, [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Microphone Array (Intel)", "max_input_channels": 2},     # idx 1
        {"name": "Microphone Array (Intel)", "max_input_channels": 2},     # idx 2 (dup)
        {"name": "Headset Hands-Free (realme)", "max_input_channels": 1},  # idx 3
    ])
    # auto / default / blank / None -> the built-in mic, NEVER the headset.
    for v in ("auto", "default", "", None):
        assert a._resolve_input_device(v) == 1
    # system / windows -> None (follow the OS default).
    assert a._resolve_input_device("system") is None
    assert a._resolve_input_device("windows") is None
    # explicit index / name.
    assert a._resolve_input_device(7) == 7
    assert a._resolve_input_device("7") == 7
    assert a._resolve_input_device("Microphone Array (Intel)") == 1  # first match
    assert a._resolve_input_device("Headset") == 3
    assert a._resolve_input_device("No Such Mic") is None


def test_input_devices_is_a_list():
    devs = input_devices()
    assert isinstance(devs, list)
    for entry in devs:
        assert isinstance(entry, tuple) and isinstance(entry[0], int) and isinstance(entry[1], str)


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
