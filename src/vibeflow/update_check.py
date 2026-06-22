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
# API_LATEST is the repo-wide "latest" — kept importable for back-compat, but no
# longer used by check(): it can return the *other* platform's release. We list
# all releases and filter to the Windows channel instead (see check()).
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_LIST = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


def _ver_tuple(s: str):
    parts = re.findall(r"\d+", (s or "").lstrip("vV"))
    return tuple(int(p) for p in parts[:4]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return _ver_tuple(latest) > _ver_tuple(current)


# ---------------------------------------------------------------------------
# Cross-platform release protocol (see docs hand-off): Mac and Windows ship
# independent releases from one repo. The channel is decided ONLY by the tag
# prefix; the Windows updater must consider Windows releases only, so a
# macOS-only ("mac-*") release can never mask a Windows update or raise a false
# "update available" the user can't install.
#   win-vX.Y.Z  -> Windows     (asset: VibeFlowSetup.exe)
#   vX.Y.Z      -> Windows     (legacy bare tags, frozen at <= v1.16.0)
#   mac-vX.Y.Z  -> macOS only  (ignored here)
# ---------------------------------------------------------------------------
_PREFIX_RE = re.compile(r"^(?:mac|win)-")
_LEADING_V_RE = re.compile(r"^v")
# A legacy Windows tag is a bare numeric version, optionally "v"-prefixed.
_BARE_WIN_RE = re.compile(r"^v?\d+(?:\.\d+)*$")
# Anchored version core: 1-4 dotted integers, optional -rc/+build suffix (no digits).
_VERSION_RE = re.compile(r"^(\d+(?:\.\d+){0,3})(?:[-+].*)?$")


def _is_windows_tag(tag: str) -> bool:
    """Allowlist: only ``win-*`` tags and legacy bare numeric tags are Windows."""
    return tag.startswith("win-") or bool(_BARE_WIN_RE.match(tag or ""))


def _parse_version(tag: str):
    """Anchored version parse: strip one ``mac-``/``win-`` then one ``v``, then
    require ``N(.N){0,3}``. Returns an int tuple, or ``None`` (never coerced)."""
    if not tag:
        return None
    rest = _LEADING_V_RE.sub("", _PREFIX_RE.sub("", tag, count=1), count=1)
    m = _VERSION_RE.match(rest)
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def _version_string(tag: str) -> str:
    """Display version: tag minus a ``win-``/``mac-`` prefix AND one leading ``v``
    (``win-v1.17.0`` -> ``1.17.0``)."""
    return _LEADING_V_RE.sub("", _PREFIX_RE.sub("", tag or "", count=1), count=1)


def _setup_asset_url(release) -> str | None:
    """URL of the release's ``*setup*.exe`` asset (the Windows installer), or None."""
    for asset in release.get("assets", []) or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "setup" in name:
            return asset.get("browser_download_url")
    return None


def _next_link(link_header: str):
    """Extract the ``rel="next"`` URL from a GitHub ``Link`` header, or None."""
    for part in (link_header or "").split(","):
        if 'rel="next"' in part:
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1)
    return None


def _list_releases():
    """All releases via the LIST endpoint, following ``Link: rel="next"`` (cap 10
    pages). Raises on transport/JSON failure so :func:`check` returns ``None``."""
    url = RELEASES_LIST
    out = []
    for _ in range(10):
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json", "User-Agent": "VibeFlow"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = json.loads(resp.read().decode("utf-8"))
            link = resp.headers.get("Link") or ""
        if not isinstance(page, list):
            break
        out.extend(page)
        url = _next_link(link)
        if not url:
            break
    return out


def check():
    """Return info about the newest **Windows** release, or ``None`` if the repo
    can't be reached.

    ``{"version", "tag", "page_url", "installer_url", "newer"}`` — ``version`` is
    always present (``""`` when there's no update).

    Lists every release (paginated), keeps only the Windows channel (``win-*`` and
    legacy bare ``vX.Y.Z`` tags), requires a ``VibeFlowSetup.exe`` asset, and
    selects the **maximum** version — so a macOS-only (``mac-*``) release can never
    mask a Windows update or raise a false "update available". Returns ``None``
    **only** on a network/HTTP/JSON failure; a reachable repo with no eligible
    Windows release returns a dict with ``newer=False``.
    """
    try:
        releases = _list_releases()
    except Exception:
        return None

    current = _parse_version(__version__) or (0,)
    best = None  # (sort_key, tag, page_url, installer_url, version_tuple)
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = rel.get("tag_name") or ""
        if not _is_windows_tag(tag):
            continue
        version = _parse_version(tag)
        if version is None:
            continue
        installer = _setup_asset_url(rel)
        if not installer:  # eligibility: nothing to download (e.g. still uploading)
            continue
        # Select by max version; deterministic tie-break on (version, date, id).
        sort_key = (version, rel.get("published_at") or "", rel.get("id") or 0)
        if best is None or sort_key > best[0]:
            best = (sort_key, tag, rel.get("html_url") or RELEASES_PAGE, installer, version)

    if best is None:
        return {"version": "", "tag": "", "page_url": RELEASES_PAGE,
                "installer_url": None, "newer": False}

    _key, tag, page_url, installer, version = best
    return {
        "version": _version_string(tag),
        "tag": tag,
        "page_url": page_url,
        "installer_url": installer,
        "newer": version > current,
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
    """Launch the downloaded installer silently and return immediately.

    The installer force-closes the running VibeFlow (PrepareToInstall) and
    relaunches it after a silent install, so the whole update is hands-free —
    no wizard, no "couldn't close the app" prompt.
    """
    try:
        subprocess.Popen(
            [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False
