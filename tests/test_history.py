"""Tests for the optional local dictation history (storage + HTML render)."""

from vibeflow.core import history


def test_append_and_load_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    assert history.load(p) == []
    history.append("hello world", "Outlook", path=p)
    history.append("second one", "Slack", path=p)
    entries = history.load(p)
    assert [e["text"] for e in entries] == ["hello world", "second one"]
    assert entries[0]["app"] == "Outlook"
    assert isinstance(entries[0]["ts"], int)


def test_append_caps_to_max(tmp_path):
    p = tmp_path / "h.json"
    for i in range(10):
        history.append(f"line {i}", path=p, max_entries=3)
    entries = history.load(p)
    assert [e["text"] for e in entries] == ["line 7", "line 8", "line 9"]


def test_append_ignores_empty(tmp_path):
    p = tmp_path / "h.json"
    history.append("   ", path=p)
    history.append("", path=p)
    assert history.load(p) == []


def test_clear(tmp_path):
    p = tmp_path / "h.json"
    history.append("x", path=p)
    history.clear(p)
    assert history.load(p) == []
    # Clearing a missing file is a no-op, not an error.
    history.clear(p)


def test_load_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("{not json", encoding="utf-8")
    assert history.load(p) == []


def test_render_html_escapes_and_contains_text():
    out = history.render_html([{"ts": 0, "app": "VS Code", "text": "a <script> & b"}])
    assert "<!DOCTYPE html>" in out
    # User text/app are HTML-escaped (no raw <script>).
    assert "&lt;script&gt;" in out
    assert "<script> &" not in out
    assert "VS Code" in out


def test_render_html_empty():
    out = history.render_html([])
    assert "No dictations recorded yet." in out
