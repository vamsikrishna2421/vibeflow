"""Tests for configuration loading, merging and persistence."""

import json

from vibeflow.config import DEFAULTS, Config, deep_merge, load_config


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
    assert cfg.get("model.language") == "auto"     # default preserved
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
