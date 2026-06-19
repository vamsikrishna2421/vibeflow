"""Tests for the output routing decision (type vs clipboard)."""

from vibeflow.focus_detect import EDITABLE, NON_EDITABLE, UNKNOWN
from vibeflow.output import decide_target


def test_explicit_type_always_types():
    assert decide_target("type", UNKNOWN) == "type"
    assert decide_target("type", NON_EDITABLE) == "type"


def test_explicit_clipboard_always_copies():
    assert decide_target("clipboard", EDITABLE) == "clipboard"


def test_auto_editable_types():
    assert decide_target("auto", EDITABLE) == "type"


def test_auto_non_editable_copies():
    assert decide_target("auto", NON_EDITABLE) == "clipboard"


def test_auto_unknown_defaults_to_clipboard():
    assert decide_target("auto", UNKNOWN) == "clipboard"
    assert decide_target("auto", UNKNOWN, auto_fallback="clipboard") == "clipboard"


def test_auto_unknown_can_fall_back_to_type():
    assert decide_target("auto", UNKNOWN, auto_fallback="type") == "type"


def test_mode_is_case_insensitive():
    assert decide_target("AUTO", EDITABLE) == "type"
    assert decide_target("Clipboard", EDITABLE) == "clipboard"
