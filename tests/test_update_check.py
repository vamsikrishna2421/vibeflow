"""Tests for the Windows updater's release selection (cross-platform protocol).

The Windows updater must only ever update to a *Windows* release (``win-*`` or
legacy bare ``vX.Y.Z``), never a macOS (``mac-*``) one, and never raise a false
"update available". These tests mock the release list — no network.
"""

import vibeflow.update_check as uc


def _rel(tag, assets=("VibeFlowSetup.exe",), draft=False, prerelease=False,
         html="https://example/r", pub="2026-01-01T00:00:00Z", id=1):
    return {
        "tag_name": tag, "draft": draft, "prerelease": prerelease,
        "html_url": html, "published_at": pub, "id": id,
        "assets": [{"name": a, "browser_download_url": f"https://github.com/x/{a}"}
                   for a in assets],
    }


def _list(monkeypatch, releases):
    monkeypatch.setattr(uc, "_list_releases", lambda: releases)


def _current(monkeypatch, v="1.16.0"):
    monkeypatch.setattr(uc, "__version__", v)


# --- pure helpers -----------------------------------------------------------
def test_is_windows_tag_allowlist():
    assert uc._is_windows_tag("win-v1.17.0")
    assert uc._is_windows_tag("v1.16.0")          # legacy bare, v-prefixed
    assert uc._is_windows_tag("1.16.0")           # legacy bare, no v
    assert not uc._is_windows_tag("mac-v1.17.0")  # other channel
    assert not uc._is_windows_tag("win")          # no dash, not numeric
    assert not uc._is_windows_tag("release-2026")


def test_parse_version_anchored():
    assert uc._parse_version("win-v1.17.0") == (1, 17, 0)
    assert uc._parse_version("v1.16.0") == (1, 16, 0)
    assert uc._parse_version("1.16.0") == (1, 16, 0)
    assert uc._parse_version("mac-v2.0.0") == (2, 0, 0)        # parses; channel filter rejects elsewhere
    assert uc._parse_version("win-v1.17.0-rc1") == (1, 17, 0)  # suffix has no digits
    assert uc._parse_version("win-vbeta") is None              # never coerced
    assert uc._parse_version("nightly") is None
    assert uc._parse_version("") is None


def test_version_string_strips_prefix_and_v():
    assert uc._version_string("win-v1.17.0") == "1.17.0"
    assert uc._version_string("v1.16.0") == "1.16.0"
    assert uc._version_string("1.16.0") == "1.16.0"
    assert uc._version_string("mac-v1.5.0") == "1.5.0"


def test_next_link():
    h = '<https://api.github.com/r?page=2>; rel="next", <https://api/r?page=5>; rel="last"'
    assert uc._next_link(h) == "https://api.github.com/r?page=2"
    assert uc._next_link('<https://api/r?page=5>; rel="last"') is None
    assert uc._next_link("") is None


def test_setup_asset_selection():
    r = _rel("win-v1.0.0", assets=("VibeFlow-mac.zip", "VibeFlowSetup.exe"))
    assert uc._setup_asset_url(r).endswith("VibeFlowSetup.exe")
    assert uc._setup_asset_url(_rel("x", assets=("notes.txt",))) is None


# --- check(): the protocol --------------------------------------------------
def test_win_and_bare_both_update(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("win-v1.17.0", id=2)])
    info = uc.check()
    assert info["version"] == "1.17.0" and info["tag"] == "win-v1.17.0"
    assert info["newer"] is True and info["installer_url"]
    _list(monkeypatch, [_rel("v1.18.0", id=3)])           # legacy bare still updates
    info = uc.check()
    assert info["version"] == "1.18.0" and info["newer"] is True


def test_mac_ignored_even_if_higher(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [
        _rel("mac-v2.0.0", assets=("VibeFlow-mac.zip",), id=5),  # higher, but macOS
        _rel("win-v1.17.0", id=4),
    ])
    info = uc.check()
    assert info["tag"] == "win-v1.17.0" and info["version"] == "1.17.0"


def test_mac_tag_rejected_even_with_setup_exe(monkeypatch):
    # Channel is decided by the tag, independent of the (mis-)attached asset.
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("mac-v3.0.0", assets=("VibeFlowSetup.exe",), id=9),
                        _rel("win-v1.17.0", id=1)])
    assert uc.check()["tag"] == "win-v1.17.0"


def test_mac_only_repo_returns_no_update_dict_not_none(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("mac-v2.0.0", assets=("VibeFlow-mac.zip",))])
    info = uc.check()
    assert info == {"version": "", "tag": "", "page_url": uc.RELEASES_PAGE,
                    "installer_url": None, "newer": False}


def test_prerelease_and_draft_skipped(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("win-v1.30.0", prerelease=True),
                        _rel("win-v1.29.0", draft=True),
                        _rel("win-v1.17.0", id=2)])
    assert uc.check()["tag"] == "win-v1.17.0"


def test_asset_still_uploading_falls_through(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("win-v1.18.0", assets=(), id=9),   # no setup.exe yet
                        _rel("win-v1.17.0", id=8)])
    assert uc.check()["tag"] == "win-v1.17.0"


def test_numeric_not_lexical_compare(monkeypatch):
    _current(monkeypatch, "1.0.0")
    _list(monkeypatch, [_rel("win-v1.9.0", id=1), _rel("win-v1.10.0", id=2)])
    assert uc.check()["version"] == "1.10.0"     # 1.10 > 1.9


def test_out_of_order_picks_max(monkeypatch):
    _current(monkeypatch, "1.0.0")
    _list(monkeypatch, [_rel("win-v1.5.0", id=1), _rel("win-v1.20.0", id=2),
                        _rel("win-v1.12.0", id=3)])
    assert uc.check()["version"] == "1.20.0"


def test_equal_version_is_not_newer(monkeypatch):
    _current(monkeypatch, "1.17.0")
    _list(monkeypatch, [_rel("win-v1.17.0")])
    info = uc.check()
    assert info["version"] == "1.17.0" and info["newer"] is False


def test_unparseable_win_tag_skipped(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("win-vnightly", id=2), _rel("win-v1.17.0", id=1)])
    assert uc.check()["tag"] == "win-v1.17.0"


def test_transport_failure_returns_none(monkeypatch):
    def boom():
        raise OSError("no network")
    monkeypatch.setattr(uc, "_list_releases", boom)
    assert uc.check() is None


def test_return_contract_keys(monkeypatch):
    _current(monkeypatch, "1.16.0")
    _list(monkeypatch, [_rel("win-v1.17.0")])
    info = uc.check()
    assert set(info) == {"version", "tag", "page_url", "installer_url", "newer"}
    assert info["version"]  # always present (subscript-safe for app.py)


def test_importable_names_for_mac_module():
    # The Mac updater imports REPO and RELEASES_PAGE; keep these importable.
    assert uc.REPO == "vamsikrishna2421/vibeflow"
    assert uc.RELEASES_PAGE.endswith("/releases")
    assert uc.API_LATEST and callable(uc.is_newer)
