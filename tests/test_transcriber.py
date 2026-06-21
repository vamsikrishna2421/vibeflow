"""Tests for the transcriber's language handling (English-default, robust)."""

from vibeflow.transcriber import Transcriber


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Stub faster-whisper model; raises if asked for ``fail_on`` language."""

    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = []

    def transcribe(self, audio, language=None, **kw):
        self.calls.append(language)
        if language == self.fail_on:
            raise RuntimeError("invalid language code")
        return ([_Seg(" hello world")], None)


def _t(language, model):
    t = Transcriber(size="small", language=language)
    t._model = model  # skip loading a real model
    return t


def test_auto_maps_to_english():
    fm = _FakeModel()
    assert _t("auto", fm).transcribe([0.0]) == " hello world"
    assert fm.calls == ["en"]  # never passes None / "auto" to the engine


def test_empty_maps_to_english():
    fm = _FakeModel()
    _t("", fm).transcribe([0.0])
    assert fm.calls == ["en"]


def test_stray_label_maps_to_english():
    # The exact bug: the UI label "Auto-detect" must never reach the engine.
    fm = _FakeModel()
    _t("Auto-detect", fm).transcribe([0.0])
    assert fm.calls == ["en"]


def test_invalid_code_falls_back_to_english():
    fm = _FakeModel(fail_on="xx")
    assert _t("xx", fm).transcribe([0.0]) == " hello world"
    assert fm.calls == ["xx", "en"]  # tried it, fell back to English


def test_valid_configured_language_is_used():
    fm = _FakeModel()
    _t("es", fm).transcribe([0.0])
    assert fm.calls == ["es"]
