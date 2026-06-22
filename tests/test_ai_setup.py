"""Tests for Ollama install orchestration: winget first, then the official
installer download as a winget-free fallback (fresh PCs often lack winget)."""

import vibeflow.ai_setup as ais


def test_already_installed_short_circuits(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: True)
    tried = []
    monkeypatch.setattr(ais, "_install_ollama_winget", lambda p=ais._noop: tried.append("w") or True)
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: tried.append("d") or True)
    assert ais.install_ollama() is True
    assert tried == []  # nothing attempted when already present


def test_non_windows_returns_false(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: False)
    monkeypatch.setattr(ais.sys, "platform", "darwin")
    assert ais.install_ollama() is False


def test_winget_success_skips_download(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: False)
    monkeypatch.setattr(ais.sys, "platform", "win32")
    monkeypatch.setattr(ais, "_install_ollama_winget", lambda p=ais._noop: True)
    monkeypatch.setattr(ais, "_tidy_ollama_gui", lambda p=ais._noop: None)  # don't taskkill
    dl = []
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: dl.append(1) or True)
    assert ais.install_ollama() is True
    assert dl == []  # download fallback not reached


def test_falls_back_to_download_when_winget_fails(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: False)
    monkeypatch.setattr(ais.sys, "platform", "win32")
    monkeypatch.setattr(ais, "_install_ollama_winget", lambda p=ais._noop: False)
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: True)
    tidied = []
    monkeypatch.setattr(ais, "_tidy_ollama_gui", lambda p=ais._noop: tidied.append(1))
    assert ais.install_ollama() is True
    assert tidied == [1]  # after WE install, we tidy Ollama's GUI/auto-start


def test_tidy_ollama_gui_noop_off_windows(monkeypatch):
    monkeypatch.setattr(ais.sys, "platform", "darwin")
    ais._tidy_ollama_gui()  # must be a harmless no-op, never raise


def test_all_paths_fail_returns_false(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: False)
    monkeypatch.setattr(ais.sys, "platform", "win32")
    monkeypatch.setattr(ais, "_install_ollama_winget", lambda p=ais._noop: False)
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: False)
    assert ais.install_ollama() is False


def test_winget_helper_absent(monkeypatch):
    monkeypatch.setattr(ais.shutil, "which", lambda name: None)
    assert ais._install_ollama_winget() is False  # no winget -> don't claim success


class _Resp:
    """Minimal urlopen stand-in: streams a few bytes then EOF."""

    headers = {"Content-Length": "8"}

    def __init__(self):
        self._chunks = [b"abcd", b"efgh", b""]

    def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_install_success(monkeypatch, tmp_path):
    monkeypatch.setattr(ais.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(ais.urllib.request, "urlopen", lambda req, timeout=0: _Resp())
    ran = {}
    monkeypatch.setattr(ais.subprocess, "run", lambda *a, **k: ran.setdefault("argv", a[0]))
    monkeypatch.setattr(ais, "is_installed", lambda: True)  # silent install "took"
    assert ais._install_ollama_download() is True
    assert (tmp_path / "VibeFlow-OllamaSetup.exe").exists()
    assert ran["argv"][1] == "/SP-" and "/VERYSILENT" in ran["argv"]  # Inno silent flags


class _JsonResp:
    def __init__(self, body):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_model_list_parses_tags(monkeypatch):
    import json

    body = json.dumps({"models": [
        {"name": "qwen2.5:3b", "size": 1900000000},
        {"name": "qwen2.5:1.5b", "size": 1000000000},
    ]}).encode()
    monkeypatch.setattr(ais.urllib.request, "urlopen", lambda u, timeout=0: _JsonResp(body))
    ml = ais.model_list()
    assert {m["name"] for m in ml} == {"qwen2.5:3b", "qwen2.5:1.5b"}
    assert dict((m["name"], m["size"]) for m in ml)["qwen2.5:3b"] == 1900000000


def test_model_list_unreachable_is_empty(monkeypatch):
    def boom(*a, **k):
        raise OSError("no server")

    monkeypatch.setattr(ais.urllib.request, "urlopen", boom)
    assert ais.model_list() == []


def test_delete_model_success(monkeypatch):
    monkeypatch.setattr(ais.urllib.request, "urlopen", lambda req, timeout=0: _JsonResp(b"{}"))
    monkeypatch.setattr(ais, "installed_models", lambda: [])  # gone afterward
    assert ais.delete_model("qwen2.5:3b") is True


def test_delete_model_404_is_success(monkeypatch):
    def fake(req, timeout=0):
        raise ais.urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(ais.urllib.request, "urlopen", fake)
    monkeypatch.setattr(ais, "installed_models", lambda: [])
    assert ais.delete_model("ghost") is True


def test_delete_model_field_fallback(monkeypatch):
    import json

    seen = []

    def fake(req, timeout=0):
        payload = json.loads(req.data.decode())
        seen.append(payload)
        if "model" in payload:  # an older Ollama wants {"name": ...}
            raise ais.urllib.error.HTTPError(req.full_url, 400, "bad", {}, None)
        return _JsonResp(b"{}")

    monkeypatch.setattr(ais.urllib.request, "urlopen", fake)
    monkeypatch.setattr(ais, "installed_models", lambda: [])
    assert ais.delete_model("qwen2.5:3b") is True
    assert {"model": "qwen2.5:3b"} in seen and {"name": "qwen2.5:3b"} in seen


def test_delete_model_still_present_is_failure(monkeypatch):
    monkeypatch.setattr(ais.urllib.request, "urlopen", lambda req, timeout=0: _JsonResp(b"{}"))
    monkeypatch.setattr(ais, "installed_models", lambda: ["qwen2.5:3b"])  # still there
    assert ais.delete_model("qwen2.5:3b") is False


def test_download_network_failure_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ais.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(ais.urllib.request, "urlopen", boom)
    assert ais._install_ollama_download() is False
