"""Fully-managed, zero-touch local-LLM setup.

The user just picks an AI tier; this module handles *everything* behind the
scenes so they never have to know what "Ollama" is:

  1. find or silently install the Ollama runtime (via winget),
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
# Official signed Windows installer — the winget-free fallback path.
OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"

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
def ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    candidate = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"
    )
    return candidate if os.path.exists(candidate) else None


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
    """Install the Ollama runtime (one-time). Returns True once it is present.

    Tries winget first (no extra download); if winget is missing or fails — common
    on fresh PCs with no/outdated App Installer — falls back to downloading the
    official signed installer from ollama.com and running it.
    """
    if is_installed():
        return True  # already present — never touch the user's existing install
    if sys.platform != "win32":
        return False
    if _install_ollama_winget(progress) or _install_ollama_download(progress):
        _tidy_ollama_gui(progress)  # we installed it: stop its window + boot auto-start
        return True
    return False


def _tidy_ollama_gui(progress=_noop) -> None:
    """After VibeFlow installs Ollama, stop its desktop app and remove its boot
    auto-start, so it doesn't pop a window or launch on every sign-in — VibeFlow
    only needs ``ollama serve`` (which it starts itself, hidden). Best-effort and
    never fatal. Only called when WE performed the install, never for a
    pre-existing Ollama the user manages themselves.
    """
    if sys.platform != "win32":
        return
    # Close the Ollama desktop/tray app window (image "ollama app.exe"); this is
    # NOT the "ollama.exe" server VibeFlow relies on.
    try:
        subprocess.run(
            ["taskkill", "/IM", "ollama app.exe", "/F"],
            check=False, capture_output=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        pass
    # Remove the Startup shortcut Ollama drops so it stops auto-launching at boot.
    try:
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
        )
        if os.path.isdir(startup):
            for name in os.listdir(startup):
                low = name.lower()
                if low.startswith("ollama") and low.endswith(".lnk"):
                    try:
                        os.remove(os.path.join(startup, name))
                    except Exception:
                        pass
    except Exception:
        pass


def _install_ollama_winget(progress=_noop) -> bool:
    """Install via winget. False if winget is absent or the install didn't take."""
    if not shutil.which("winget"):
        return False
    progress("Installing the local AI runtime (one-time)…")
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
        return False
    return is_installed()


def _install_ollama_download(progress=_noop) -> bool:
    """Download the official Ollama installer and run it (winget-free path).

    Installs silently when the installer honours ``/VERYSILENT``; if it instead
    shows its window, we wait for the user to finish it, then detect it. Any
    failure leaves AI off and dictation untouched.
    """
    progress("Downloading the local AI runtime…")
    dst = os.path.join(tempfile.gettempdir(), "VibeFlow-OllamaSetup.exe")
    try:
        req = urllib.request.Request(OLLAMA_SETUP_URL, headers={"User-Agent": "VibeFlow"})
        with urllib.request.urlopen(req, timeout=600) as resp, open(dst, "wb") as f:
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
    try:
        subprocess.run(
            [dst, "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            check=False, timeout=900, creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        pass
    # OllamaSetup.exe is an Inno Setup installer that honours these silent flags,
    # but it finalizes *asynchronously*: ollama.exe / the registry can take a
    # second or two to appear after the process exits. Poll before concluding it
    # failed — otherwise we'd prematurely relaunch the installer in a visible
    # window (the "second window" users saw).
    deadline = time.time() + 15
    while time.time() < deadline:
        if is_installed():
            return True
        time.sleep(1)

    # Silent install genuinely didn't take: open the installer for the user to
    # finish, then wait (bounded) for it to appear.
    try:
        subprocess.Popen([dst])
    except Exception:
        return False
    progress("Finish the Ollama installer window — it will continue automatically…")
    deadline = time.time() + 300
    while time.time() < deadline:
        if is_installed():
            return True
        time.sleep(2)
    return is_installed()


def start_server(progress=_noop, timeout: float = 30) -> bool:
    """Ensure the local Ollama server is running."""
    if server_up():
        return True
    exe = ollama_exe()
    if not exe:
        return False
    progress("Starting the local AI server…")
    try:
        subprocess.Popen(
            [exe, "serve"],
            creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
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
