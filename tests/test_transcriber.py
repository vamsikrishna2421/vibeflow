"""Tests for the transcriber's language handling (English-default, robust)
and its device selection / GPU→CPU fallback."""

import vibeflow.transcriber as tr
from vibeflow.transcriber import Transcriber, _resolve_device


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


# --- device selection -------------------------------------------------------
def test_auto_uses_gpu_only_when_runtime_loadable(monkeypatch):
    # GPU present but no CUDA runtime (cuBLAS won't load) -> CPU, not a crash.
    monkeypatch.setattr(tr, "_cuda_available", lambda: False)
    assert _resolve_device("auto", "auto") == ("cpu", "int8")
    # GPU present AND runtime loadable -> GPU with float16.
    monkeypatch.setattr(tr, "_cuda_available", lambda: True)
    assert _resolve_device("auto", "auto") == ("cuda", "float16")


def test_explicit_devices_and_unknown_fallback():
    assert _resolve_device("cpu", "auto") == ("cpu", "int8")
    assert _resolve_device("cuda", "auto") == ("cuda", "float16")
    assert _resolve_device("cuda", "int8") == ("cuda", "int8")
    assert _resolve_device("metal", "auto") == ("cpu", "int8")  # unknown -> cpu


def test_cuda_available_requires_loadable_runtime(monkeypatch):
    # Even with a CUDA device, an unloadable cuBLAS means "not available".
    monkeypatch.setattr(tr, "_cuda_runtime_loadable", lambda: False)

    class _CT:
        @staticmethod
        def get_cuda_device_count():
            return 1

    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", _CT)
    assert tr._cuda_available() is False
    monkeypatch.setattr(tr, "_cuda_runtime_loadable", lambda: True)
    assert tr._cuda_available() is True


def test_gpu_inference_failure_falls_back_to_cpu():
    # Model loaded on CUDA, inference fails; transcribe() rebuilds on CPU + retries.
    cuda_model = _FakeModel(fail_on="en")  # the GPU model: every (en) call fails
    cpu_model = _FakeModel()               # the rebuilt CPU model: works
    t = Transcriber(size="small", language="en", device="cuda")
    t._model = cuda_model
    t._resolved = ("cuda", "float16")

    def fake_reload():
        t._model = cpu_model
        t._resolved = ("cpu", "int8")
        t.device, t.compute_type = "cpu", "int8"
        return True

    t._reload_on_cpu = fake_reload
    assert t.transcribe([0.0]) == " hello world"
    assert t._resolved == ("cpu", "int8") and t.device == "cpu"


def test_no_fallback_loop_when_already_cpu():
    # On CPU, a transcription failure is a real error, not a fallback trigger.
    import pytest

    t = Transcriber(size="small", language="en")
    t._model = _FakeModel(fail_on="en")
    t._resolved = ("cpu", "int8")
    with pytest.raises(tr.TranscriptionError):
        t.transcribe([0.0])
