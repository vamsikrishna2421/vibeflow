# VibeFlow auto-update — cross-platform release protocol

Mac and Windows ship **independent releases at independent paces** from the one
repo (`vamsikrishna2421/vibeflow`). Each app's in-app updater only ever updates
to **its own** newest release — never the other platform's, and never a false
"update available". This doc is the contract both sides follow.

> **Status:** the **Mac** side (`src/vibeflow/platform_mac/updater.py`) is
> implemented to this spec. The **Windows** side (`src/vibeflow/update_check.py`)
> still uses the old repo-wide `/releases/latest` and needs the change in §5.

---

## 1. Release convention (the single source of truth)

Channel is decided **only by the tag prefix**. The asset only decides
*eligibility* (is there something to download).

| Tag            | Channel            | Required asset                 |
|----------------|--------------------|--------------------------------|
| `mac-vX.Y.Z`   | macOS              | `VibeFlow-mac.zip` (notarized) |
| `win-vX.Y.Z`   | Windows            | `VibeFlowSetup.exe`            |
| bare `vX.Y.Z`  | Windows (legacy)   | `VibeFlowSetup.exe`            |

Invariants (ideally enforced in CI):
- **No new bare `vX.Y.Z` tags.** Bare tags are frozen to the historical set
  (≤ v1.16.0) and remain Windows-only. New releases are always prefixed.
- A `mac-*` release must **not** attach a `*setup*.exe`; a `win-*`/bare release
  must **not** attach `VibeFlow-mac*.zip`. (Keeps the two channels disjoint.)
- Versions are **independent monotonic spaces per channel**. Windows continues
  from `win-v1.17.0`+, Mac from `mac-v1.16.0`+ — never renumber below an already
  shipped version, or installed users get stranded.
- A built binary's `__version__` must equal the numeric core of its tag.

## 2. Updater algorithm (identical shape on both platforms)

1. `GET https://api.github.com/repos/<REPO>/releases?per_page=100` — the **LIST**,
   never `/releases/latest` (that's repo-wide and lets one platform mask the
   other). Paginate via the `Link: rel="next"` header (cap ~10 pages).
2. Skip any release with `draft` or `prerelease` true.
3. Keep only **this channel's** releases (by tag prefix — see §1).
4. Parse the version with an **anchored** parser: strip one `^(mac|win)-`, one
   `^v?`, then require `^\d+(\.\d+){0,3}` (a `-rc`/`+build` suffix contributes no
   digits); a tag that doesn't match is skipped, never coerced.
5. **Eligibility:** the release must carry this platform's asset; otherwise skip
   it (so a top release whose asset is still uploading falls through to the last
   good one).
6. **Select by max parsed version** over eligible releases — never by list order.
   Tie-break: `(version, published_at, id)`.
7. `newer` = selected version > the running `__version__` (compare prefix-free
   numeric cores).

**Return contract** (both `check()` functions): return `None` **only** on
network/HTTP/JSON failure; a reachable repo with no eligible release returns a
dict with `newer=False` (so the UI says "you're on the latest", not "no
internet"). The dict's `version` key is always present (use `""` for no-update).

## 3. Mac side — DONE (`platform_mac/updater.py`)

- `check()` lists releases (+pagination), filters to `mac-` tags, selects the
  max eligible version requiring an asset named exactly `VibeFlow-mac.zip`.
  Returns `{version, tag, page_url, zip_url, newer}` (note: **`zip_url`**, not
  `installer_url` — that's `menubar.py`'s contract).
- **Security:** installs only if the downloaded bundle is notarized **and**
  `TeamIdentifier == CJ8SV692GN` (our Developer ID — notarization alone only
  proves "some Apple developer"). Download is restricted to GitHub HTTPS hosts,
  truncation-checked, written to a unique temp path; the bundle is version-bound
  to its tag (`CFBundleShortVersionString` must match), and swapped in by a
  detached helper (paths passed as argv, no shell interpolation) that
  re-verifies the installed bundle and rolls back on failure.
- Wired into the menu bar: quiet check on startup, "Check for updates" /
  "⬆ Install update (x.y.z)" menu item.
- Pure selection logic is unit-tested (`tests/test_platform_mac.py`).

## 4. How to cut a Mac release

```bash
VIBEFLOW_NOTARIZE=1 ./scripts/build_mac_app.sh    # signs + notarizes → ~/Desktop/VibeFlow-mac.zip
```
Then on GitHub: create a release tagged **`mac-vX.Y.Z`** (matching the build's
`__version__`), attach **`VibeFlow-mac.zip`**, publish (not draft/prerelease).
The in-app updater picks it up. Windows releases are completely separate.

---

## 5. Windows side — TODO (hand this section to the Windows Claude Code)

> Implement on the Windows build. **Scope: change only the body of `check()` in
> `src/vibeflow/update_check.py`** (you may add private helpers + a LIST URL
> constant). Do **not** edit `app.py` or `__init__.py`. Do **not** change
> `download_installer`/`run_installer` signatures or the silent-install flags.
> **Keep `RELEASES_PAGE`, `is_newer`, and `API_LATEST` importable** — the Mac
> module imports `REPO` and `RELEASES_PAGE` from this file; do not remove those.

**Why:** today `check()` hits `/releases/latest` (repo-wide). The day Mac ships
`mac-v1.17.0` (a `.zip`-only release), `/releases/latest` returns it; the old
code finds no `setup.exe` (`installer_url=None`) but still computes
`newer=True` from `1.17.0` vs `1.16.0` → every Windows user gets a stuck "update
available" they can't install. Move to the LIST endpoint + a Windows filter.

**Exact rule `check()` must implement:**
1. `GET https://api.github.com/repos/vamsikrishna2421/vibeflow/releases?per_page=100`,
   same headers as today, paginate via `Link: rel="next"` (cap ~10 pages).
   `try/except` → return `None` **only** on transport/JSON failure.
2. Skip releases where `draft` or `prerelease` is truthy.
3. **Windows channel match (allowlist):** `tag.startswith("win-")` **or**
   `re.match(r"^v?\d+(\.\d+)*$", tag)` (legacy bare numeric). Reject everything
   else (`mac-*`, mistyped prefixes).
4. **Anchored version parse** (do NOT reuse `re.findall(r"\d+", s.lstrip("vV"))`):
   strip `^(mac|win)-`, then `^v?`, then require
   `^(\d+(?:\.\d+){0,3})(?:[-+].*)?$` → int tuple, else skip the release.
5. **Eligibility:** require an asset where
   `name.lower().endswith(".exe") and "setup" in name.lower()`; use its
   `browser_download_url` as `installer_url`. No such asset → skip the release.
6. **Select by max parsed version** (not list order). Tie-break
   `(version, published_at, id)`.
7. `newer` = selected version > parsed `__version__` (1.16.0), prefix-free.
8. No candidate after filtering → return the no-update dict with `newer=False`
   (**not** `None`).

**Return contract — preserve exactly** (keys `app.py` depends on):
`{version, tag, page_url, installer_url, newer}`.
- `version` = numeric string: tag minus a `win-`/`mac-` prefix **and** one
  leading `v` (e.g. `win-v1.17.0` → `"1.17.0"`). Do **not** use
  `tag.lstrip("vV")` (leaves `win-` → users would see "win-1.17.0"). Always
  present (`""` for no-update — `app.py` reads `info['version']` by subscript).
- `tag` = raw selected tag. `page_url` = selected release `html_url` (else
  `RELEASES_PAGE`). `installer_url` = the setup.exe url or `None`.
- Transport failure → `None`. No Windows release matched → `{"version":"",
  "tag":"", "page_url":RELEASES_PAGE, "installer_url":None, "newer":False}`.

**Test checklist:** legacy bare + `win-` both update; `mac-*` ignored even if
higher; mac-only repo → no-update dict (not None); prerelease skipped;
asset-still-uploading falls through; `1.10 > 1.9`; out-of-order picks max;
`mac-v…`/`win-v…` import line still works.

---

## 6. Residual risks / future work
- **Windows download path is not integrity-checked** (no Authenticode pin / no
  SHA-256 / fixed temp path). This protocol only changes Windows *selection*;
  hardening the Windows *download/install* is a separate task (the Mac side is
  already hardened — Team-ID pin, host allowlist, version binding, safe swap).
- **CI enforcement** of the §1 invariants (no new bare tags, asset disjointness,
  `__version__ == tag`) is recommended but not yet implemented — until then a
  mistagged/mis-asseted release can violate the disjointness the updaters assume.
- **Team-ID pin** is hardcoded (`CJ8SV692GN`); if the signing identity ever
  rotates, update `_TEAM_ID` in `updater.py` or Mac self-update silently stops.
- GitHub release metadata is mutable/unsigned; the version↔Info.plist binding +
  Team-ID pin reduce but don't fully eliminate a downgrade-to-old-signed-build
  attack. A detached signature over `{version, sha256}` would close it fully.
