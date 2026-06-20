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


def test_parse_terms_basic():
    src = "Deploy to Kubernetes with kubectl and check the Grafana dashboard."
    assert ai_format._parse_terms("Kubernetes, kubectl, Grafana", src) == [
        "Kubernetes",
        "kubectl",
        "Grafana",
    ]


def test_parse_terms_none_and_empty():
    assert ai_format._parse_terms("NONE", "anything here") == []
    assert ai_format._parse_terms("", "anything here") == []


def test_parse_terms_drops_hallucinations():
    # Only terms that actually appear in the source text are kept.
    src = "we use Kubernetes in production"
    assert ai_format._parse_terms("Kubernetes, Docker, Helm", src) == ["Kubernetes"]


def test_extract_terms_empty_is_no_network():
    # Empty corrected text returns [] without touching the network.
    assert ai_format.extract_terms("", _Cfg({})) == []


def test_preserves_voice_guard():
    pv = ai_format._preserves_voice
    # First-person kept -> OK
    assert pv("I did a test", "I did a test.") is True
    # First-person -> rewritten as second person ("you") -> rejected
    assert pv("I did a test", "You conducted a test.") is False
    # First-person -> "the user" third person -> rejected
    assert pv("I did a test", "The user did a test.") is False
    # No first-person to begin with -> nothing to preserve -> OK
    assert pv("The build works fine", "The build works fine.") is True
    # "we/our" first person preserved
    assert pv("we should deploy our app", "We should deploy our app.") is True
