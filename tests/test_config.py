"""Tests for configuration loading, merging and persistence."""

import json

from vibeflow.config import DEFAULTS, Config, deep_merge, load_config


def test_per_app_modes_defaults():
    modes = DEFAULTS["text"]["modes"]
    assert modes["enabled"] is True
    assert modes["rules"] == []
    assert modes["starter_pack_offered"] is False
    assert modes["deliver_hotkey"] == "ctrl+shift+v"
    assert modes["deliver_on_ctrl_v"] is False
    assert modes["pending_timeout"] == 60


def test_modes_merge_keeps_user_rules_and_default_keys():
    # A user who only sets a rule still gets all the other mode defaults.
    user = {"text": {"modes": {"rules": [{"match": {"by": "process",
            "value": "outlook.exe"}, "outcome": "professional"}]}}}
    merged = deep_merge(DEFAULTS, user)
    m = merged["text"]["modes"]
    assert m["enabled"] is True  # default preserved
    assert m["deliver_hotkey"] == "ctrl+shift+v"
    assert m["rules"][0]["outcome"] == "professional"


def test_deep_merge_is_recursive_and_nondestructive():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 20, "z": 30}, "c": 4}
    out = deep_merge(base, override)
    assert out == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3, "c": 4}
    # originals untouched
    assert base["a"] == {"x": 1, "y": 2}


def test_dotted_get_and_set():
    cfg = Config(deep_merge(DEFAULTS, {}))
    assert cfg.get("model.size") == "base"
    cfg.set("model.size", "small")
    assert cfg.get("model.size") == "small"
    cfg.set("new.section.flag", True)
    assert cfg.get("new.section.flag") is True
    assert cfg.get("missing.key", "fallback") == "fallback"


def test_load_overlays_user_on_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"model": {"size": "small"}, "output": {"mode": "clipboard"}})
    )
    cfg = load_config(path)
    assert cfg.get("model.size") == "small"        # overridden
    assert cfg.get("model.language") == "en"       # default preserved
    assert cfg.get("output.mode") == "clipboard"   # overridden
    assert cfg.get("output.insertion") == "paste"  # default preserved


def test_save_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({}))
    cfg = load_config(path)
    cfg.set("hotkey.mode", "push_to_talk")
    cfg.save()
    reloaded = load_config(path)
    assert reloaded.get("hotkey.mode") == "push_to_talk"


def test_malformed_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not valid json")
    cfg = load_config(path)
    assert cfg.get("model.size") == "base"
