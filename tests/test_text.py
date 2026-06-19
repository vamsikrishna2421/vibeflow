"""Tests for transcript text cleanup (pure functions)."""

from vibeflow.text import clean_transcript, preview, with_trailing_space


def test_collapse_and_strip():
    assert clean_transcript("  hello    world  ") == "hello world"


def test_segment_join_leading_space():
    # Whisper segments often start with a leading space.
    assert clean_transcript(" Hello world.") == "Hello world."


def test_tabs_collapse():
    assert clean_transcript("a\t\tb") == "a b"


def test_capitalize_first():
    assert clean_transcript("hello", capitalize_first=True) == "Hello"


def test_capitalize_first_skips_leading_punctuation():
    assert clean_transcript('"quote', capitalize_first=True) == '"Quote'


def test_remove_trailing_period_single():
    assert clean_transcript("Okay.", remove_trailing_period=True) == "Okay"
    # only one period is removed
    assert clean_transcript("Wait...", remove_trailing_period=True) == "Wait.."


def test_empty_and_none():
    assert clean_transcript(None) == ""
    assert clean_transcript("") == ""
    assert clean_transcript("   ") == ""


def test_trailing_space_helper():
    assert with_trailing_space("hi", True) == "hi "
    assert with_trailing_space("hi ", True) == "hi "      # not doubled
    assert with_trailing_space("hi\n", True) == "hi\n"    # newline counts
    assert with_trailing_space("hi", False) == "hi"
    assert with_trailing_space("", True) == ""


def test_preview_flattens_and_truncates():
    assert preview("a  b\n c") == "a b c"
    long_text = "x" * 100
    assert len(preview(long_text, limit=10)) <= 10
