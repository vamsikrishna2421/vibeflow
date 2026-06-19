"""Tests for hotkey string parsing and key matching (pure helpers)."""

import pytest

from vibeflow.hotkey import (
    _matches,
    canonical_token,
    normalize_key_name,
    to_pynput_combo,
)


def test_combo_basic():
    assert to_pynput_combo("ctrl+alt+space") == "<ctrl>+<alt>+<space>"


def test_combo_keeps_single_letters_bare():
    assert to_pynput_combo("ctrl+shift+d") == "<ctrl>+<shift>+d"


def test_combo_resolves_aliases_and_whitespace():
    assert to_pynput_combo("control+win+a") == "<ctrl>+<cmd>+a"
    assert to_pynput_combo("  CTRL + ALT + SPACE ") == "<ctrl>+<alt>+<space>"


def test_combo_function_key():
    assert to_pynput_combo("f9") == "<f9>"


def test_combo_ctrl_win_default():
    # Default toggle combo: Ctrl + Windows key -> pynput "<ctrl>+<cmd>".
    assert to_pynput_combo("ctrl+win") == "<ctrl>+<cmd>"


def test_combo_empty_raises():
    with pytest.raises(ValueError):
        to_pynput_combo("   ")


def test_normalize_key_name():
    assert normalize_key_name("right ctrl") == "ctrl_r"
    assert normalize_key_name("Ctrl_R") == "ctrl_r"
    assert normalize_key_name("F8") == "f8"
    assert normalize_key_name("a") == "a"


def test_canonical_token_aliases():
    assert canonical_token("PgUp") == "page_up"
    assert canonical_token("escape") == "esc"
    assert canonical_token("rshift") == "shift_r"


class _Char:
    def __init__(self, c):
        self.char = c


class _Named:
    def __init__(self, name):
        self.name = name
        self.char = None


def test_matches_character_key():
    assert _matches(_Char("a"), "a")
    assert not _matches(_Char("b"), "a")


def test_matches_named_key():
    assert _matches(_Named("ctrl_r"), "ctrl_r")
    assert not _matches(_Named("f8"), "ctrl_r")


def test_matches_modifier_family():
    assert _matches(_Named("ctrl_l"), "ctrl")
    assert _matches(_Named("ctrl_r"), "ctrl")
    assert not _matches(_Named("alt_l"), "ctrl")
