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


def test_parse_hold_combo():
    from vibeflow.hotkey import parse_hold_combo

    assert parse_hold_combo("ctrl+win") == ["ctrl", "cmd"]   # Win -> cmd
    assert parse_hold_combo("ctrl_r") == ["ctrl_r"]           # single key
    assert parse_hold_combo("alt+shift+a") == ["alt", "shift", "a"]
    assert parse_hold_combo("  ") == []


class _FakeListener:
    def __init__(self, on_press, on_release):
        _FakeListener.captured = (on_press, on_release)

    def start(self):
        pass

    def stop(self):
        pass


class _FakeKeyboard:
    Listener = _FakeListener


def _make_ptt(monkeypatch, physical):
    """Build a push-to-talk manager whose OS key-state is `physical`."""
    from vibeflow import hotkey as hk
    from vibeflow.hotkey import HotkeyManager

    monkeypatch.setattr(hk, "_os_modifier_down", lambda t: physical.get(t))
    starts, stops = [], []
    mgr = HotkeyManager(
        mode="push_to_talk",
        push_to_talk_key="ctrl+win",
        on_start=lambda: starts.append(1),
        on_stop=lambda: stops.append(1),
    )
    mgr._start_push_to_talk(_FakeKeyboard)
    press, release = _FakeListener.captured
    return press, release, starts, stops


def test_ptt_does_not_fire_on_ctrl_when_win_physically_up(monkeypatch):
    # The bug: Win got "stuck" in the tracked set, so plain Ctrl (e.g. Ctrl+C)
    # mis-fired a recording. The OS says Win is up, so it must NOT start.
    physical = {"ctrl": True, "cmd": False}
    press, release, starts, stops = _make_ptt(monkeypatch, physical)

    press(_Named("ctrl_l"))
    assert starts == []          # <-- no spurious trigger on Ctrl alone

    physical["cmd"] = True        # now the Windows key is really held too
    press(_Named("cmd"))
    assert starts == [1]          # both physically down -> start

    release(_Named("ctrl_l"))
    assert stops == [1]           # releasing a target stops


def test_ptt_fallback_to_tracked_set_when_os_unknown(monkeypatch):
    # On non-Windows (OS state unknown) it falls back to press/release tracking.
    physical = {"ctrl": None, "cmd": None}
    press, release, starts, stops = _make_ptt(monkeypatch, physical)

    press(_Named("ctrl_l"))
    assert starts == []           # only one of two targets held
    press(_Named("cmd"))
    assert starts == [1]          # both held -> start
