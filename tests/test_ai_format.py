"""Tests for the optional AI layer (no network calls)."""

from vibeflow import ai_format


class _Cfg:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


def test_disabled_by_default():
    cfg = _Cfg({})
    assert ai_format.is_enabled(cfg) is False
    # Disabled -> returns None without touching the network.
    assert ai_format.format_text("hello world", cfg) is None


def test_enabled_flag():
    assert ai_format.is_enabled(_Cfg({"ai.enabled": True})) is True


def test_empty_text_returns_none():
    # Empty input short-circuits before any network call, even when enabled.
    assert ai_format.format_text("", _Cfg({"ai.enabled": True})) is None
