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
    dl = []
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: dl.append(1) or True)
    assert ais.install_ollama() is True
    assert dl == []  # download fallback not reached


def test_falls_back_to_download_when_winget_fails(monkeypatch):
    monkeypatch.setattr(ais, "is_installed", lambda: False)
    monkeypatch.setattr(ais.sys, "platform", "win32")
    monkeypatch.setattr(ais, "_install_ollama_winget", lambda p=ais._noop: False)
    monkeypatch.setattr(ais, "_install_ollama_download", lambda p=ais._noop: True)
    assert ais.install_ollama() is True


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
    assert ran["argv"][1] == "/VERYSILENT"  # invoked the silent installer


def test_download_network_failure_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ais.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(ais.urllib.request, "urlopen", boom)
    assert ais._install_ollama_download() is False
