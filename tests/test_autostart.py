"""Tests for the auto-start command construction (no registry writes)."""

from vibeflow import autostart


def test_command_is_quoted_and_runnable():
    cmd = autostart._command()
    assert isinstance(cmd, str) and cmd
    # Always launch via a quoted executable path.
    assert cmd.startswith('"')
    # From source it runs the package; frozen it runs the exe.
    assert ("-m vibeflow" in cmd) or cmd.lower().endswith('.exe"')
