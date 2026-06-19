"""Tests for the single-instance lock."""

import sys

import pytest

from vibeflow.single_instance import SingleInstance


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_instance_is_blocked():
    name = "Local\\VibeFlow_Test_Mutex_pytest"
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        assert second.already_running is True
    finally:
        first.release()
        second.release()


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_lock_is_reusable_after_release():
    name = "Local\\VibeFlow_Test_Mutex_pytest_2"
    a = SingleInstance(name)
    assert a.acquire() is True
    a.release()
    b = SingleInstance(name)
    try:
        assert b.acquire() is True  # freed, so a new instance can take it
    finally:
        b.release()
