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
import time
import urllib.request

ENDPOINT = "http://127.0.0.1:11434"

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
    """Silently install the Ollama runtime via winget (one-time)."""
    if is_installed():
        return True
    if sys.platform != "win32":
        return False
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
