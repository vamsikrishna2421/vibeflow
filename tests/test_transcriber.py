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


# --- Phonon-2 engine ----------------------------------------------------------
import sys  # noqa: E402
import types  # noqa: E402

import pytest  # noqa: E402

import vibeflow.transcriber as tr  # noqa: E402
from vibeflow import phonon  # noqa: E402


class _PhononResult:
    def __init__(self, text):
        self.text = text


class _FakeSpeech:
    """Stub of a loaded fermion speech model."""

    def __init__(self, text="Port eight four four three at245 PM, rose0 .8.", fail=None):
        self.text, self.fail, self.calls = text, fail, []

    def describe(self):
        return {"engine": "cpu"}

    def transcribe_array_detailed(self, audio, hotwords=None, **kw):
        self.calls.append({"audio": audio, "hotwords": hotwords})
        if self.fail:
            raise self.fail
        return _PhononResult(self.text)


def _no_engine_runtimes(monkeypatch):
    # The one-runtime-per-process guard looks at sys.modules: start clean.
    for name in ("torch", "ctranslate2"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def _fake_fermion(monkeypatch, speech=None, load_error=None, on_load=None):
    loads = []

    def load_speech(model, quiet=True):
        loads.append(model)
        if on_load:
            on_load()
        if load_error is not None:
            raise load_error
        return speech or _FakeSpeech()

    _no_engine_runtimes(monkeypatch)
    monkeypatch.setitem(sys.modules, "fermion", types.SimpleNamespace(load_speech=load_speech))
    monkeypatch.setattr(phonon, "prepare_env", lambda models_dir: None)
    monkeypatch.setattr(tr, "_lead_pad", lambda audio: ["pad"] + list(audio))
    return loads


def _fake_whisper(monkeypatch):
    class WhisperModel:
        def __init__(self, name, **kw):
            self.name = name

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(tr, "_cuda_available", lambda: False)


def test_engine_of_model_ids():
    assert tr._engine_of("phonon-2") == "phonon"
    assert tr._engine_of("Phonon-2.5-en") == "phonon"
    assert tr._engine_of("moonshine/base") == "moonshine"
    assert tr._engine_of("medium") == "whisper"
    assert tr._engine_of(None) == "whisper"


def test_phonon_transcribes_with_lead_pad_and_digits(monkeypatch):
    speech = _FakeSpeech()
    loads = _fake_fermion(monkeypatch, speech)
    t = Transcriber(size="phonon-2", language="en")
    t.load()
    assert loads == ["phonon-2"] and t._resolved == ("cpu", "phonon-2")
    out = t.transcribe([0.1, 0.2], prompt="Vocabulary: Kubernetes.")
    assert out == "Port 8443 at 2:45 PM, rose 0.8."  # digits respaced, spoken numbers converted
    call = speech.calls[0]
    assert call["audio"] == ["pad", 0.1, 0.2]  # the same lead-in as Whisper
    assert call["hotwords"] == []              # the Whisper prompt isn't used as hotwords


def test_phonon_refusal_falls_back_to_whisper(monkeypatch):
    # fermion refuses unsupported machines with SystemExit, not an Exception.
    _fake_fermion(monkeypatch, load_error=SystemExit("CPU speech is unavailable here"))
    _fake_whisper(monkeypatch)
    t = Transcriber(size="phonon-2", language="en", fallback_size="medium")
    t.load()
    assert (t.engine, t.size, t.fell_back_from) == ("whisper", "medium", "phonon-2")
    assert "unavailable" in t.fallback_reason
    assert t._resolved == ("cpu", "int8")
    assert t._model.name == "Systran/faster-whisper-medium"


def test_phonon_missing_package_falls_back(monkeypatch):
    _no_engine_runtimes(monkeypatch)
    monkeypatch.setitem(sys.modules, "fermion", None)  # import fermion -> ImportError
    _fake_whisper(monkeypatch)
    t = Transcriber(size="phonon-2", language="en")
    t.load()
    assert (t.engine, t.size) == ("whisper", tr.DEFAULT_FALLBACK)
    assert "fermion-research" in t.fallback_reason


def test_no_fallback_once_torch_is_loaded(monkeypatch):
    # A failure after PyTorch loaded: Whisper can't safely join it, so raise.
    fake_torch = types.ModuleType("torch")
    _fake_fermion(monkeypatch, load_error=RuntimeError("bad model file"),
                  on_load=lambda: monkeypatch.setitem(sys.modules, "torch", fake_torch))
    _fake_whisper(monkeypatch)
    t = Transcriber(size="phonon-2", language="en")
    with pytest.raises(tr.TranscriptionError):
        t.load()
    assert t.engine == "phonon" and t.fell_back_from is None


def test_phonon_failure_without_fallback_raises(monkeypatch):
    _fake_fermion(monkeypatch, load_error=SystemExit("no"))
    t = Transcriber(size="phonon-2", language="en", fallback_size=None)
    with pytest.raises(tr.TranscriptionError):
        t.load()
    assert t.engine == "phonon" and t.fell_back_from is None


def test_phonon_offline_load_needs_cached_model(monkeypatch):
    # The app's offline-first retry must not download, and must not fall back.
    loads = _fake_fermion(monkeypatch)
    monkeypatch.setattr(phonon, "is_cached", lambda size, models_dir=None: False)
    t = Transcriber(size="phonon-2", language="en")
    with pytest.raises(tr.TranscriptionError):
        t.load(allow_download=False)
    assert loads == [] and t.engine == "phonon"


def test_phonon_decode_error_is_wrapped(monkeypatch):
    _fake_fermion(monkeypatch, speech=_FakeSpeech(fail=SystemExit("out of memory")))
    t = Transcriber(size="phonon-2", language="en")
    with pytest.raises(tr.TranscriptionError):
        t.transcribe([0.0])


def test_phonon_is_cached_unknown_without_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "fermion", None)
    monkeypatch.setattr(phonon, "prepare_env", lambda models_dir: None)
    assert phonon.is_cached("phonon-2") is None


def test_prepare_env_points_cache_at_models_dir(monkeypatch, tmp_path):
    import os

    for name in ("FERMION_CACHE_DIR", "HF_HUB_DISABLE_PROGRESS_BARS"):
        monkeypatch.setenv(name, "x")  # recorded, so teardown restores the real state
        monkeypatch.delenv(name)
    phonon.prepare_env(tmp_path)
    assert os.environ["FERMION_CACHE_DIR"] == str(tmp_path)
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    phonon.prepare_env(tmp_path / "other")  # an existing value wins
    assert os.environ["FERMION_CACHE_DIR"] == str(tmp_path)


# --- one engine family per process -------------------------------------------
def test_whisper_never_joins_pytorch_in_one_process(monkeypatch):
    _no_engine_runtimes(monkeypatch)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    _fake_whisper(monkeypatch)
    assert tr.needs_restart("small") and not tr.needs_restart("phonon-2")
    with pytest.raises(tr.EngineRestartRequired):
        Transcriber(size="small", language="en").load()


def test_phonon_never_joins_ctranslate2_in_one_process(monkeypatch):
    loads = _fake_fermion(monkeypatch)
    monkeypatch.setitem(sys.modules, "ctranslate2", types.ModuleType("ctranslate2"))
    assert tr.needs_restart("phonon-2") and not tr.needs_restart("medium")
    with pytest.raises(tr.EngineRestartRequired):
        Transcriber(size="phonon-2", language="en").load()
    assert loads == []  # never even tried


@pytest.mark.parametrize("frozen, expected", [
    (True, ["VibeFlow.exe", "--config", "c.yaml"]),
    (False, ["python", "-m", "vibeflow", "--config", "c.yaml"]),
])
def test_relaunch_command(monkeypatch, frozen, expected):
    import subprocess

    import vibeflow.__main__ as entry

    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setattr(sys, "executable", "VibeFlow.exe" if frozen else "python")
    monkeypatch.setattr(sys, "argv", ["launcher", "--config", "c.yaml"])
    if frozen:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
    else:
        monkeypatch.delattr(sys, "frozen", raising=False)
    entry._relaunch()
    assert started == [expected]


# --- signed Mac app: fermion's kernel pins -----------------------------------
def _fake_kernel_modules(monkeypatch, tmp_path):
    kernels = types.ModuleType("fermion._speech._engine_phonon2_cpu")
    kernels.HERE = tmp_path
    (tmp_path / "libphonon2_tdt-macos-x86_64.dylib").write_bytes(b"re-signed bytes")
    kernels._pins = lambda: {"libphonon2_tdt-macos-x86_64.dylib": "original-pin",
                             "libphonon2_cpu-linux-x86_64.so": "not-in-this-bundle"}
    gate = types.ModuleType("fermion._speech.gate_cpu")
    calls = []
    gate.binary_path = lambda *, verify=True: calls.append(verify) or tmp_path
    speech = types.ModuleType("fermion._speech")
    speech._engine_phonon2_cpu, speech.gate_cpu = kernels, gate
    for name, mod in (("fermion", types.ModuleType("fermion")), ("fermion._speech", speech),
                      ("fermion._speech._engine_phonon2_cpu", kernels),
                      ("fermion._speech.gate_cpu", gate)):
        monkeypatch.setitem(sys.modules, name, mod)
    return kernels, gate, calls


def test_signed_mac_app_trusts_its_bundled_kernels(monkeypatch, tmp_path):
    import hashlib

    kernels, gate, calls = _fake_kernel_modules(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    phonon._trust_signed_bundle()
    want = hashlib.sha256(b"re-signed bytes").hexdigest()
    assert kernels._pins() == {"libphonon2_tdt-macos-x86_64.dylib": want}
    gate.binary_path(verify=True)
    assert calls == [False]  # Apple Silicon's CPU-engine check skips the old pin


def test_pins_untouched_outside_the_signed_mac_app(monkeypatch, tmp_path):
    kernels, gate, _ = _fake_kernel_modules(monkeypatch, tmp_path)
    original = kernels._pins
    monkeypatch.delattr(sys, "frozen", raising=False)
    phonon._trust_signed_bundle()
    assert kernels._pins is original
