"""Tests for per-app formatting: the pure outcome resolver and helpers."""

from vibeflow.core.appmode import (
    AppIdentity,
    CASUAL,
    DEFAULT,
    PROFESSIONAL,
    VERBATIM,
    app_category,
    friendly_name,
    resolve_outcome,
    shadowed_by,
    starter_pack_rules,
)


def _rule(by, value, outcome):
    return {"match": {"by": by, "value": value}, "outcome": outcome}


# --- safety-first fallbacks -------------------------------------------------
def test_protected_target_is_always_verbatim():
    # An elevated/unidentifiable window must never be AI-rewritten.
    app = AppIdentity(window_class="consolewindowclass", protected=True)
    assert resolve_outcome(app, [_rule("window_class", "console", PROFESSIONAL)]) == VERBATIM


def test_no_target_is_default():
    assert resolve_outcome(AppIdentity(), []) == DEFAULT
    assert resolve_outcome(None, []) == DEFAULT


# --- built-in verbatim surfaces (terminals + editors) -----------------------
def test_terminal_by_class_is_verbatim():
    assert resolve_outcome(AppIdentity(window_class="cascadia_hosting_window_class"), []) == VERBATIM
    assert resolve_outcome(AppIdentity(window_class="consolewindowclass"), []) == VERBATIM


def test_terminal_by_exe_is_verbatim():
    assert resolve_outcome(AppIdentity(exe="powershell.exe", window_class="x"), []) == VERBATIM


def test_code_editor_is_verbatim_by_default():
    assert resolve_outcome(AppIdentity(exe="code.exe", window_class="chrome_widgetwin_1"), []) == VERBATIM
    assert resolve_outcome(AppIdentity(exe="idea64.exe"), []) == VERBATIM


def test_unknown_app_is_default():
    assert resolve_outcome(AppIdentity(exe="notepad.exe", window_class="notepad"), []) == DEFAULT


# --- user rules override built-ins ------------------------------------------
def test_user_rule_overrides_builtin_verbatim():
    # The user explicitly wants clean-up in VS Code -> honour it over the built-in.
    app = AppIdentity(exe="code.exe")
    assert resolve_outcome(app, [_rule("process", "code.exe", PROFESSIONAL)]) == PROFESSIONAL


def test_process_rule_matches_with_or_without_exe_suffix():
    app = AppIdentity(exe="outlook.exe")
    assert resolve_outcome(app, [_rule("process", "outlook", PROFESSIONAL)]) == PROFESSIONAL
    assert resolve_outcome(app, [_rule("process", "outlook.exe", PROFESSIONAL)]) == PROFESSIONAL


def test_casual_rule_for_chat():
    app = AppIdentity(exe="whatsapp.exe")
    assert resolve_outcome(app, [_rule("process", "whatsapp.exe", CASUAL)]) == CASUAL


# --- specificity: title > class > process -----------------------------------
def test_more_specific_rule_wins():
    app = AppIdentity(exe="chrome.exe", window_class="chrome_widgetwin_1", title="Inbox - Gmail")
    rules = [
        _rule("process", "chrome.exe", CASUAL),        # rank 1
        _rule("title_contains", "Gmail", PROFESSIONAL),  # rank 3 -> wins
    ]
    assert resolve_outcome(app, rules) == PROFESSIONAL


def test_class_beats_process():
    app = AppIdentity(exe="chrome.exe", window_class="special_class")
    rules = [
        _rule("process", "chrome.exe", CASUAL),
        _rule("window_class", "special_class", PROFESSIONAL),
    ]
    assert resolve_outcome(app, rules) == PROFESSIONAL


def test_first_match_wins_on_specificity_tie():
    app = AppIdentity(exe="chrome.exe", title="My Gmail and Slack")
    rules = [
        _rule("title_contains", "gmail", PROFESSIONAL),
        _rule("title_contains", "slack", CASUAL),
    ]
    assert resolve_outcome(app, rules) == PROFESSIONAL


def test_title_rule_no_match_falls_through_to_default():
    app = AppIdentity(exe="chrome.exe", window_class="chrome_widgetwin_1", title="News")
    assert resolve_outcome(app, [_rule("title_contains", "Gmail", PROFESSIONAL)]) == DEFAULT


def test_empty_or_malformed_rules_ignored():
    app = AppIdentity(exe="notepad.exe")
    assert resolve_outcome(app, [{}, {"match": {}}, _rule("process", "", PROFESSIONAL)]) == DEFAULT
    # An unknown outcome string is ignored, not applied.
    assert resolve_outcome(app, [_rule("process", "notepad.exe", "bogus")]) == DEFAULT


# --- friendly names ---------------------------------------------------------
def test_friendly_name_known_and_fallback():
    assert friendly_name("code.exe") == "VS Code"
    assert friendly_name("WINDOWSTERMINAL.EXE") == "Windows Terminal"
    assert friendly_name("my_cool_app.exe") == "My Cool App"
    assert friendly_name("") == "this app"


# --- shadow detection for the Manage UI -------------------------------------
def test_app_category():
    assert app_category("outlook.exe") == "email"
    assert app_category("SLACK.EXE") == "chat"
    assert app_category("notepad.exe") is None
    assert app_category("") is None


def test_starter_pack_rules_apply():
    rules = starter_pack_rules()
    assert resolve_outcome(AppIdentity(exe="outlook.exe"), rules) == PROFESSIONAL
    assert resolve_outcome(AppIdentity(exe="slack.exe"), rules) == CASUAL
    # Terminals stay verbatim (built-in) even with the pack applied.
    assert resolve_outcome(AppIdentity(exe="powershell.exe"), rules) == VERBATIM
    # An app not in the pack -> normal default.
    assert resolve_outcome(AppIdentity(exe="notepad.exe", window_class="notepad"), rules) == DEFAULT


def test_shadowed_by_detects_duplicate_broader_rule():
    rules = [_rule("process", "chrome.exe", CASUAL)]
    # Adding the same process rule again is shadowed by the existing one.
    hit = shadowed_by({"by": "process", "value": "chrome.exe"}, rules)
    assert hit is not None
    # A more specific (title) rule for the same app is NOT shadowed.
    assert shadowed_by({"by": "title_contains", "value": "Gmail"}, rules) is None
