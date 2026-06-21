"""Tests for the transcriber's language handling and auto-detect fallback."""

from vibeflow.transcriber import Transcriber


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Stub faster-whisper model: optionally fails when language is None (auto)."""

    def __init__(self, fail_on_none=True):
        self.fail_on_none = fail_on_none
        self.calls = []

    def transcribe(self, audio, language=None, **kw):
        self.calls.append(language)
        if language is None and self.fail_on_none:
            raise RuntimeError("language detection failed")
        return ([_Seg(" hello world")], None)


def _t(language, model):
    t = Transcriber(size="small", language=language)
    t._model = model  # skip loading a real model
    return t


def test_auto_falls_back_to_english_when_detection_fails():
    fm = _FakeModel(fail_on_none=True)
    out = _t("auto", fm).transcribe([0.0])
    assert out == " hello world"
    assert fm.calls == [None, "en"]  # tried auto, then fell back to English


def test_auto_success_does_not_fall_back():
    fm = _FakeModel(fail_on_none=False)
    out = _t("auto", fm).transcribe([0.0])
    assert out == " hello world"
    assert fm.calls == [None]  # auto worked; no retry


def test_fixed_language_never_falls_back():
    fm = _FakeModel(fail_on_none=True)  # would fail on None, but we ask for es
    out = _t("es", fm).transcribe([0.0])
    assert out == " hello world"
    assert fm.calls == ["es"]
