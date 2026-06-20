"""Check GitHub Releases for a newer VibeFlow, and update to it.

Stdlib only. The tray runs a quiet check shortly after startup and offers a
manual "Check for updates"; when a newer release is found it can download that
release's ``VibeFlowSetup.exe`` and launch it (the installer closes the running
copy, installs the new version, and relaunches it).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.request

from . import __version__

REPO = "vamsikrishna2421/vibeflow"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


def _ver_tuple(s: str):
    parts = re.findall(r"\d+", (s or "").lstrip("vV"))
    return tuple(int(p) for p in parts[:4]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return _ver_tuple(latest) > _ver_tuple(current)


def check():
    """Return info about the latest release, or ``None`` if it can't be reached.

    ``{"version", "tag", "page_url", "installer_url", "newer"}``.
    """
    try:
        req = urllib.request.Request(
            API_LATEST,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "VibeFlow"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name") or ""
    installer = None
    for asset in data.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "setup" in name:
            installer = asset.get("browser_download_url")
            break
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "page_url": data.get("html_url") or RELEASES_PAGE,
        "installer_url": installer,
        "newer": is_newer(tag),
    }


def download_installer(url: str, progress=lambda _m: None):
    """Download the release installer to a temp file. Returns its path or None."""
    if not url:
        return None
    dst = os.path.join(tempfile.gettempdir(), "VibeFlowSetup-update.exe")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VibeFlow"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(dst, "wb") as f:
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
                        progress(f"Downloading update… {pct}%")
        return dst
    except Exception:
        return None


def run_installer(path: str) -> bool:
    """Launch the downloaded installer (visible wizard; it closes & relaunches
    VibeFlow). Returns True if it started."""
    try:
        subprocess.Popen([path])  # no silent flags: user sees it; [Run] relaunches
        return True
    except Exception:
        return False
