"""Fully-managed, zero-touch local-LLM setup.

The user just picks an AI tier; this module handles *everything* behind the
scenes so they never have to know what "Ollama" is:

  1. find or silently install the Ollama runtime (winget on Windows; Homebrew
     or a bundled background download on macOS),
  2. start its local server,
  3. download the chosen model with progress,
  4. report readiness.

Standard library + the Ollama CLI/HTTP API only. Every step is defensive and
reports progress through a callback so the tray can show what's happening.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ENDPOINT = "http://127.0.0.1:11434"
# Official Ollama macOS bundle (contains Ollama.app + its bundled `ollama` CLI).
OLLAMA_MACOS_URL = "https://ollama.com/download/Ollama-darwin.zip"

# Friendly tiers -> (Ollama model, approx download size). Chosen by benchmark.
MODEL_TIERS = {
    "fast": ("qwen2.5:1.5b", "1 GB"),
    "balanced": ("qwen2.5:3b", "2 GB"),
    "best": ("gemma2:2b", "1.6 GB"),
}

_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008


def _noop(_message: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------
def _managed_runtime_dir() -> str:
    """A VibeFlow-owned directory that can hold a background-installed Ollama on
    macOS (used only when the user has no Homebrew/system Ollama)."""
    try:
        from .config import config_dir

        base = str(config_dir())
    except Exception:
        base = os.path.expanduser("~/.config/VibeFlow")
    path = os.path.join(base, "runtime")
    os.makedirs(path, exist_ok=True)
    return path


def _find_ollama_binary(root: str) -> str | None:
    """Locate the `ollama` CLI inside an extracted Ollama.app, whatever its layout."""
    if not os.path.isdir(root):
        return None
    for base, _dirs, files in os.walk(root):
        if "ollama" in files:
            candidate = os.path.join(base, "ollama")
            if os.path.isfile(candidate):
                return candidate
    return None


def ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    # Explicit locations — an app launched from Finder/Explorer has a minimal PATH,
    # so `which` alone misses Homebrew installs and app bundles.
    for candidate in (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        "/Applications/Ollama.app/Contents/Resources/ollama",
        os.path.expanduser("~/Applications/Ollama.app/Contents/Resources/ollama"),
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    # A VibeFlow-managed background install (macOS, no Homebrew).
    if sys.platform == "darwin":
        return _find_ollama_binary(_managed_runtime_dir())
    return None


def is_installed() -> bool:
    return ollama_exe() is not None


def server_up(timeout: float = 3) -> bool:
    try:
        urllib.request.urlopen(ENDPOINT + "/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def installed_models() -> list:
    try:
        with urllib.request.urlopen(ENDPOINT + "/api/tags", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in body.get("models", [])]
    except Exception:
        return []


def has_model(model: str) -> bool:
    names = installed_models()
    return model in names or (model + ":latest") in names


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------
def install_ollama(progress=_noop) -> bool:
    """Silently install the Ollama runtime (one-time), the right way per platform.
    Never touches a pre-existing install."""
    if is_installed():
        return True
    if sys.platform == "win32":
        return _install_ollama_windows(progress)
    if sys.platform == "darwin":
        return _install_ollama_macos(progress)
    return False  # Linux: leave runtime management to the user's package manager.


def _install_ollama_windows(progress=_noop) -> bool:
    progress("Installing the local AI runtime (one-time, ~1 GB)…")
    try:
        subprocess.run(
            [
                "winget", "install", "--id", "Ollama.Ollama", "-e", "--silent",
                "--accept-package-agreements", "--accept-source-agreements",
            ],
            check=False,
            capture_output=True,
            timeout=900,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        pass
    return is_installed()


def _install_ollama_macos(progress=_noop) -> bool:
    """Provision Ollama on macOS with zero user interaction and no terminal: reuse
    Homebrew if it happens to be present, otherwise download the official Ollama.app
    into a VibeFlow-managed folder and drive its bundled CLI headlessly. No admin
    rights, no installer windows, no mention of "Ollama" to the user."""
    brew = shutil.which("brew") or next(
        (c for c in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if os.path.exists(c)),
        None,
    )
    if brew:
        progress("Setting up the local AI runtime (one-time)…")
        try:
            subprocess.run(
                [brew, "install", "ollama"], check=False, capture_output=True, timeout=900
            )
        except Exception:
            pass
        if ollama_exe():
            return True
    return _install_ollama_macos_download(progress)


def _install_ollama_macos_download(progress=_noop) -> bool:
    """Brew-free path: download Ollama.app and unpack it into the managed folder.
    Uses `ditto` (not zipfile) so the bundle's symlinks and executable bits survive."""
    progress("Downloading the local AI runtime…")
    zip_path = os.path.join(tempfile.gettempdir(), "VibeFlow-Ollama-darwin.zip")
    try:
        req = urllib.request.Request(OLLAMA_MACOS_URL, headers={"User-Agent": "VibeFlow"})
        with urllib.request.urlopen(req, timeout=900) as resp, open(zip_path, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done, last = 0, -1
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = int(done / total * 100)
                    if pct != last:
                        last = pct
                        progress(f"Downloading the local AI runtime… {pct}%")
    except Exception:
        return False
    progress("Installing the local AI runtime…")
    dest = _managed_runtime_dir()
    try:
        shutil.rmtree(os.path.join(dest, "Ollama.app"), ignore_errors=True)
        subprocess.run(
            ["ditto", "-x", "-k", zip_path, dest],
            check=False, capture_output=True, timeout=300,
        )
    except Exception:
        return False
    binp = _find_ollama_binary(dest)
    if binp:
        try:
            os.chmod(binp, 0o755)
        except Exception:
            pass
        return True
    return False


def start_server(progress=_noop, timeout: float = 30) -> bool:
    """Ensure the local Ollama server is running."""
    if server_up():
        return True
    exe = ollama_exe()
    if not exe:
        return False
    progress("Starting the local AI server…")
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                [exe, "serve"],
                creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # POSIX: detach into its own session; the Windows creationflags are invalid here.
            subprocess.Popen(
                [exe, "serve"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_up():
            return True
        time.sleep(1)
    return server_up()


def pull_model(model: str, progress=_noop) -> bool:
    """Download a model via Ollama's streaming /api/pull, reporting % progress."""
    if has_model(model):
        progress(f"Model already downloaded ({model}).")
        return True
    progress(f"Downloading model {model}…")
    data = json.dumps({"name": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT + "/api/pull", data=data, headers={"Content-Type": "application/json"}
    )
    last_pct = -1
    try:
        with urllib.request.urlopen(req, timeout=2400) as resp:
            for raw in resp:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if obj.get("error"):
                    progress("Download error: " + str(obj["error"]))
                    return False
                total, done = obj.get("total"), obj.get("completed")
                if total and done:
                    pct = int(done / total * 100)
                    if pct != last_pct:
                        last_pct = pct
                        progress(f"Downloading {model}… {pct}%")
                elif obj.get("status"):
                    progress(str(obj["status"]))
        return has_model(model)
    except Exception as exc:
        progress(f"Download failed: {exc}")
        return False


def setup(model: str, progress=_noop) -> tuple[bool, str]:
    """Full managed setup. Returns (ok, message)."""
    if not install_ollama(progress):
        return False, (
            "Couldn't install the local AI runtime automatically. Install Ollama "
            "from https://ollama.com, then try again."
        )
    if not start_server(progress):
        return False, "The local AI runtime is installed but its server wouldn't start."
    if not pull_model(model, progress):
        return False, f"Couldn't download the model '{model}'."
    progress("AI is ready.")
    return True, f"AI formatting is ready (model: {model})."
