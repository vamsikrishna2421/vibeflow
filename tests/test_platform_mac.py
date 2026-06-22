"""Tests for the pure macOS "hands" logic.

These cover only the platform-neutral pieces — the per-app catalog/resolver and
the Mac config-default overlay — which import nothing beyond the standard
library and ``vibeflow.core``/``vibeflow.config`` (no PyObjC / rumps). The GUI,
Accessibility, audio and keystroke layers are exercised manually on a Mac.
"""

from vibeflow import config as config_mod
from vibeflow.core.appmode import (
    AppIdentity,
    CASUAL,
    DEFAULT,
    EMAIL,
    PROFESSIONAL,
    VERBATIM,
)
from vibeflow.platform_mac import catalog, defaults, updater


def _cfg(overrides=None):
    return config_mod.Config(config_mod.deep_merge(config_mod.DEFAULTS, overrides or {}))


# --- Mac config defaults overlay -------------------------------------------
def test_mac_defaults_remap_windows_push_to_talk():
    cfg = _cfg()  # ships the Windows default "ctrl+win"
    defaults.apply_mac_defaults(cfg)
    assert cfg.get("hotkey.push_to_talk_key") == "cmd_r"
    assert cfg.get("hotkey.toggle_combo") == "cmd_r"
    assert cfg.get("text.modes.deliver_hotkey") == "cmd+shift+v"


def test_mac_defaults_preserve_user_choice():
    cfg = _cfg({"hotkey": {"push_to_talk_key": "f13"},
                "text": {"modes": {"deliver_hotkey": "cmd+alt+v"}}})
    defaults.apply_mac_defaults(cfg)
    assert cfg.get("hotkey.push_to_talk_key") == "f13"
    assert cfg.get("text.modes.deliver_hotkey") == "cmd+alt+v"


# --- Mac per-app resolver: built-in verbatim surfaces ----------------------
def test_terminals_and_editors_are_verbatim_by_bundle_id():
    for bundle in ("com.apple.terminal", "com.googlecode.iterm2",
                   "com.microsoft.vscode", "com.apple.dt.xcode",
                   "com.jetbrains.pycharm"):
        assert catalog.resolve_outcome(AppIdentity(exe=bundle), []) == VERBATIM


def test_terminals_and_editors_are_verbatim_by_name():
    # When a bundle id wasn't resolvable, the localized name still matches.
    for name in ("terminal", "iterm2", "code", "xcode", "sublime text"):
        assert catalog.resolve_outcome(AppIdentity(exe=name), []) == VERBATIM


def test_unknown_app_is_default():
    assert catalog.resolve_outcome(AppIdentity(exe="com.acme.notes"), []) == DEFAULT


def test_none_app_is_default():
    assert catalog.resolve_outcome(None, []) == DEFAULT


# --- user rules win over built-ins (specificity) ---------------------------
def test_user_rule_overrides_builtin_verbatim():
    rules = [{"match": {"by": "process", "value": "com.apple.terminal"},
              "outcome": PROFESSIONAL}]
    assert catalog.resolve_outcome(AppIdentity(exe="com.apple.terminal"), rules) \
        == PROFESSIONAL


# --- Starter Pack -----------------------------------------------------------
def test_starter_pack_email_and_chat():
    rules = catalog.starter_pack_rules()
    assert catalog.resolve_outcome(AppIdentity(exe="com.apple.mail"), rules) == EMAIL
    assert catalog.resolve_outcome(AppIdentity(exe="com.microsoft.outlook"), rules) == EMAIL
    assert catalog.resolve_outcome(
        AppIdentity(exe="com.tinyspeck.slackmacgap"), rules) == CASUAL
    assert catalog.resolve_outcome(AppIdentity(exe="com.hnc.discord"), rules) == CASUAL


def test_starter_pack_webmail_by_title():
    # Browser process is ambiguous; the OS-neutral title hint resolves it.
    rules = catalog.starter_pack_rules()
    app = AppIdentity(exe="com.google.chrome", title="Inbox - me@gmail.com - Gmail")
    assert catalog.resolve_outcome(app, rules) == EMAIL


# --- app_category (used to offer the Starter Pack in context) --------------
def test_app_category():
    assert catalog.app_category("com.apple.mail") == "email"
    assert catalog.app_category("slack") == "chat"
    assert catalog.app_category("com.hnc.discord") == "chat"
    assert catalog.app_category("com.acme.notes") is None


# --- macOS self-updater: version parsing -----------------------------------
def test_parse_version_anchored():
    assert updater._parse_version("mac-v1.17.0") == (1, 17, 0, 0)
    assert updater._parse_version("mac-1.17.0") == (1, 17, 0, 0)
    assert updater._parse_version("v1.16.0") == (1, 16, 0, 0)
    # 1.10 must outrank 1.9 (numeric, not lexical)
    assert updater._parse_version("mac-v1.10.0") > updater._parse_version("mac-v1.9.0")
    # a pre-release suffix contributes no digits → equal, never greater
    assert updater._parse_version("mac-v1.2.0-rc2") == (1, 2, 0, 0)
    # junk → None (never coerced into a candidate)
    assert updater._parse_version("garbage") is None
    assert updater._parse_version("") is None


# --- macOS self-updater: mac-channel release selection ---------------------
def _rel(tag, assets=None, draft=False, prerelease=False, pub="2026-01-01T00:00:00Z",
         rid=1):
    return {
        "tag_name": tag, "draft": draft, "prerelease": prerelease,
        "published_at": pub, "id": rid, "html_url": f"https://x/{tag}",
        "assets": [{"name": n, "browser_download_url": u} for n, u in (assets or [])],
    }


_ZIP = [("VibeFlow-mac.zip", "https://objects.githubusercontent.com/z")]
_EXE = [("VibeFlowSetup.exe", "https://objects.githubusercontent.com/e")]


def test_select_mac_ignores_windows_and_legacy():
    out = updater._select_mac([
        _rel("mac-v1.18.0", _ZIP),
        _rel("win-v2.0.0", _EXE),     # newer number, but Windows → ignored
        _rel("v1.16.0", _EXE),        # legacy bare → Windows → ignored
        _rel("mac-v1.17.0", _ZIP),
    ])
    assert out["version"] == "1.18.0"
    assert out["tag"] == "mac-v1.18.0"
    assert out["zip_url"] == "https://objects.githubusercontent.com/z"
    assert out["newer"] is True


def test_select_mac_no_mac_release_is_no_update_not_none():
    out = updater._select_mac([_rel("win-v2.0.0", _EXE), _rel("v1.16.0", _EXE)])
    assert out is not None
    assert out["newer"] is False
    assert out["version"] == "" and out["zip_url"] is None
    # contract: all 5 keys always present
    assert set(out) == {"version", "tag", "page_url", "zip_url", "newer"}


def test_select_mac_skips_prerelease():
    out = updater._select_mac([
        _rel("mac-v1.18.0", _ZIP, prerelease=True),
        _rel("mac-v1.17.0", _ZIP),
    ])
    assert out["tag"] == "mac-v1.17.0"


def test_select_mac_falls_through_assetless_top_release():
    out = updater._select_mac([
        _rel("mac-v1.18.0", assets=[]),   # asset still uploading / missing
        _rel("mac-v1.17.0", _ZIP),
    ])
    assert out["tag"] == "mac-v1.17.0"
    assert out["zip_url"] == "https://objects.githubusercontent.com/z"
    assert out["newer"] is True


def test_select_mac_picks_max_version_not_list_order():
    out = updater._select_mac([
        _rel("mac-v1.17.0", _ZIP, pub="2026-05-01T00:00:00Z"),  # published later, listed first
        _rel("mac-v1.18.0", _ZIP, pub="2026-01-01T00:00:00Z"),
    ])
    assert out["tag"] == "mac-v1.18.0"


def test_select_mac_equal_version_is_not_newer():
    out = updater._select_mac([_rel("mac-v1.16.0", _ZIP)])  # == __version__
    assert out["newer"] is False
    assert out["version"] == "1.16.0"


def test_download_host_allowlist():
    # GitHub serves release assets from release-assets.githubusercontent.com — the
    # downloader must accept it (and other GitHub hosts), reject everything else.
    assert updater._host_ok("github.com")
    assert updater._host_ok("release-assets.githubusercontent.com")
    assert updater._host_ok("objects.githubusercontent.com")
    assert updater._host_ok("codeload.github.com")
    assert not updater._host_ok("evil.com")
    assert not updater._host_ok("githubusercontent.com.evil.com")
    assert not updater._host_ok("")
