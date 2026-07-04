"""macOS self-update from GitHub Releases — the **mac-** release channel.

Mac and Windows ship INDEPENDENT releases from the same repo, distinguished by
tag prefix (``mac-vX.Y.Z`` / ``win-vX.Y.Z``; legacy bare ``vX.Y.Z`` = Windows).
This updater only ever considers **Mac** releases, so the two platforms never
mask each other and never raise a false "update available". See
``docs/UPDATE_PROTOCOL.md`` for the full cross-platform contract.

Channel identity is decided EXCLUSIVELY by the ``mac-`` tag prefix; the
``VibeFlow-mac.zip`` asset only decides *eligibility* (is there something to
download). Selection is by **max parsed version** over eligible releases (not
list order), so out-of-order/backport publishes never cause a downgrade and a
release whose asset is still uploading transparently falls through to the last
good one.

Security: an update is installed only if the downloaded bundle is notarized
**and signed by our own Team ID** (notarization alone just proves "some Apple
developer"). The download is restricted to GitHub HTTPS hosts, extracted into a
private temp dir, version-bound to its tag, and swapped in by a detached helper
that re-verifies the installed bundle and rolls back on failure.
"""

from __future__ import annotations

import os
import platform
import plistlib
import re
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse

from .. import __app_name__, __version__
from ..update_check import REPO, RELEASES_PAGE

API_LIST = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
_MAC_ASSET = f"vibeflow-mac-{platform.machine().lower()}.zip"   # arch-aware (compared lowercased)
_TEAM_ID = "CJ8SV692GN"                  # pin self-updates to OUR Developer ID
# GitHub-controlled hosts. `_host_ok` also matches any subdomain, so
# "githubusercontent.com" covers release-assets / objects / codeload /raw.* —
# GitHub serves release-asset downloads from release-assets.githubusercontent.com.
_ALLOWED_HOSTS = ("github.com", "githubusercontent.com")
_MAX_PAGES = 10


# ---------------------------------------------------------------------------
# Version parsing (anchored, prefix-stripped) — never coerce a junk tag
# ---------------------------------------------------------------------------
def _parse_version(tag: str):
    """``mac-v1.2.0`` → ``(1,2,0,0)``; junk → ``None``. Padded to 4 for compare.

    A pre-release/build suffix (``-rc1`` / ``+build``) contributes no digits, so
    ``mac-v1.2.0-rc1`` == ``(1,2,0,0)`` — never greater than ``mac-v1.2.0``.
    """
    t = re.sub(r"^(mac|win)-", "", tag or "", count=1)
    t = re.sub(r"^[vV]", "", t, count=1)
    m = re.match(r"^(\d+(?:\.\d+){0,3})(?:[-+].*)?$", t)
    if not m:
        return None
    nums = [int(x) for x in m.group(1).split(".")]
    nums += [0] * (4 - len(nums))
    return tuple(nums[:4])


def _version_str(tag: str) -> str:
    """User-facing numeric version: strip a ``mac-``/``win-`` prefix and one ``v``."""
    t = re.sub(r"^(mac|win)-", "", tag or "", count=1)
    return re.sub(r"^[vV]", "", t, count=1)


def _host_ok(host: str | None) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def _bundle_path() -> str | None:
    """Absolute path to the running ``.app`` bundle, or ``None`` if not frozen."""
    if not getattr(sys, "frozen", False):
        return None
    exe = os.path.realpath(sys.executable)
    marker = ".app/Contents/MacOS/"
    idx = exe.find(marker)
    return exe[: idx + len(".app")] if idx != -1 else None


# ---------------------------------------------------------------------------
# Release selection (pure; unit-tested without network)
# ---------------------------------------------------------------------------
def _find_mac_asset(release: dict):
    for asset in release.get("assets", []) or []:
        if (asset.get("name") or "").lower() == _MAC_ASSET:
            return asset.get("browser_download_url")
    return None


def _no_update() -> dict:
    return {"version": "", "tag": "", "page_url": RELEASES_PAGE,
            "zip_url": None, "newer": False}


def _select_mac(releases: list) -> dict:
    """Pick the newest eligible Mac release from a GitHub releases list.

    Returns the public 5-key dict (``version``/``tag``/``page_url``/``zip_url``/
    ``newer``). Never returns ``None`` (that's reserved for transport failure in
    :func:`check`).
    """
    best = None  # ((ver, published_at, id), zip_url, tag, html_url)
    for r in releases or []:
        if not isinstance(r, dict):
            continue
        if r.get("draft") or r.get("prerelease"):
            continue
        tag = r.get("tag_name") or ""
        if not tag.startswith("mac-"):           # channel = tag prefix ONLY
            continue
        ver = _parse_version(tag)
        if ver is None:
            continue
        zip_url = _find_mac_asset(r)              # eligibility = usable asset
        if not zip_url:
            continue
        key = (ver, r.get("published_at") or "", r.get("id") or 0)
        if best is None or key > best[0]:
            best = (key, zip_url, tag, r.get("html_url") or RELEASES_PAGE)

    if best is None:
        return _no_update()
    (ver, _pub, _id), zip_url, tag, html = best
    current = _parse_version(__version__) or (0, 0, 0, 0)
    return {
        "version": _version_str(tag),
        "tag": tag,
        "page_url": html,
        "zip_url": zip_url,
        "newer": ver > current,
    }


def _http_get_json(url: str):
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": __app_name__}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        import json
        data = json.loads(resp.read().decode("utf-8"))
        link = resp.headers.get("Link") or ""
    return data, link


def _next_page(link_header: str):
    for part in (link_header or "").split(","):
        bits = part.split(";")
        if len(bits) >= 2 and 'rel="next"' in bits[1]:
            return bits[0].strip().strip("<>")
    return None


def check():
    """Latest **Mac** release info, or ``None`` on transport failure.

    Returns ``{"version","tag","page_url","zip_url","newer"}``. A reachable repo
    with no eligible Mac release returns a dict with ``newer=False`` (NOT
    ``None``) so the UI honestly says "you're on the latest".
    """
    try:
        releases, url, pages = [], API_LIST, 0
        while url and pages < _MAX_PAGES:
            data, link = _http_get_json(url)
            if not isinstance(data, list):
                break
            releases.extend(data)
            url = _next_page(link)
            pages += 1
    except Exception:
        return None  # network / HTTP / JSON failure only
    return _select_mac(releases)


# ---------------------------------------------------------------------------
# Download (GitHub-HTTPS-only, truncation-checked, unique temp path)
# ---------------------------------------------------------------------------
class _GitHubOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or not _host_ok(u.hostname):
            return None  # refuse to follow off-GitHub / non-HTTPS redirects
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_zip(url: str, progress=lambda _m: None):
    """Download the release zip to a unique temp file. Returns its path or None."""
    if not url:
        return None
    u = urlparse(url)
    if u.scheme != "https" or not _host_ok(u.hostname):
        return None
    fd, dst = tempfile.mkstemp(prefix="VibeFlow-update-", suffix=".zip")
    os.close(fd)
    opener = urllib.request.build_opener(_GitHubOnlyRedirect())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": __app_name__})
        with opener.open(req, timeout=300) as resp, open(dst, "wb") as f:
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
        if total and done != total:
            os.remove(dst)
            return None  # truncated
        return dst
    except Exception:
        try:
            os.remove(dst)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Verify + install
# ---------------------------------------------------------------------------
def _find_app_bundle(root: str):
    for base, dirs, _files in os.walk(root):
        for d in dirs:
            if d.endswith(".app"):
                return os.path.join(base, d)
    return None


def _verify_signed(app_path: str) -> bool:
    """True only if notarized AND signed by OUR Team ID (pinned)."""
    try:
        if subprocess.run(["spctl", "--assess", "--type", "execute", app_path],
                          capture_output=True, timeout=60).returncode != 0:
            return False  # not notarized / Gatekeeper-rejected
        if subprocess.run(["codesign", "--verify", "--deep", "--strict", app_path],
                          capture_output=True, timeout=60).returncode != 0:
            return False
        r = subprocess.run(["codesign", "-dvv", app_path],
                          capture_output=True, text=True, timeout=30)
        blob = (r.stderr or "") + (r.stdout or "")
        return f"TeamIdentifier={_TEAM_ID}" in blob
    except Exception:
        return False


def _bundle_plist_version(app_path: str):
    try:
        with open(os.path.join(app_path, "Contents", "Info.plist"), "rb") as f:
            return (plistlib.load(f) or {}).get("CFBundleShortVersionString")
    except Exception:
        return None


# A detached swap helper. Paths arrive as $1/$2/$3 (argv) — NOT interpolated into
# the script body — so nothing the download controls is ever shell-evaluated.
_SWAP_HELPER = r"""#!/bin/bash
NEW="$1"; TARGET="$2"; PID="$3"
for _ in $(seq 1 150); do kill -0 "$PID" 2>/dev/null || break; sleep 0.1; done
BACKUP="${TARGET}.bak"
rm -rf "$BACKUP" 2>/dev/null
[ -d "$TARGET" ] && mv "$TARGET" "$BACKUP"
if /usr/bin/ditto "$NEW" "$TARGET"; then
  if /usr/sbin/spctl --assess --type execute "$TARGET" >/dev/null 2>&1; then
    /usr/bin/xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
    rm -rf "$BACKUP" 2>/dev/null
  else
    rm -rf "$TARGET" 2>/dev/null
    [ -d "$BACKUP" ] && mv "$BACKUP" "$TARGET"
  fi
else
  [ -d "$BACKUP" ] && [ ! -d "$TARGET" ] && mv "$BACKUP" "$TARGET"
fi
/usr/bin/open "$TARGET"
"""


def apply_update(zip_path: str, expected_version: str | None = None) -> bool:
    """Verify the downloaded build and swap it in, then relaunch.

    Returns ``True`` if the swap-and-relaunch helper was launched (the caller
    should then quit so the helper can replace the bundle); ``False`` if anything
    fails verification — the running app is left untouched.
    """
    target = _bundle_path()
    if not target or not zip_path or not os.path.exists(zip_path):
        return False

    work = tempfile.mkdtemp(prefix="vibeflow-update-")
    try:
        os.chmod(work, 0o700)
    except Exception:
        pass
    try:
        # ditto safely expands a notarized bundle (incl. its internal framework
        # symlinks); tampering/path-escape is caught by the strict codesign verify.
        subprocess.run(["ditto", "-x", "-k", zip_path, work], check=True, timeout=180)
    except Exception:
        return False

    new_app = _find_app_bundle(work)
    if not new_app:
        return False
    # Must be exactly our bundle, contained within the work dir.
    if os.path.basename(new_app) != "VibeFlow.app":
        return False
    if not os.path.realpath(new_app).startswith(os.path.realpath(work) + os.sep):
        return False
    # Signed by us + notarized.
    if not _verify_signed(new_app):
        return False
    # Downgrade defense: the bundle's own version must match the tag we trusted.
    if expected_version:
        plist_ver = _bundle_plist_version(new_app)
        if plist_ver and str(plist_ver) != str(expected_version):
            return False

    helper = os.path.join(work, "swap.sh")
    try:
        with open(helper, "w", encoding="utf-8") as f:
            f.write(_SWAP_HELPER)
        os.chmod(helper, 0o755)
        subprocess.Popen(
            ["/bin/bash", helper, new_app, target, str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False
