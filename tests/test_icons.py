"""Tests for the logo/icon renderer (skipped if Pillow isn't installed)."""

import pytest


def test_render_logo_sizes_and_mode():
    pytest.importorskip("PIL")
    from vibeflow.icons import make_tray_image, render_logo

    img = render_logo(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"

    for state in ("idle", "recording", "busy"):
        tray = make_tray_image(state, 32)
        assert tray.size == (32, 32)
        assert tray.mode == "RGBA"


def test_flow_color_endpoints():
    from vibeflow.icons import _BLUE, _ORANGE, _flow_color

    assert _flow_color(0.0) == _BLUE
    assert _flow_color(1.0) == _ORANGE
