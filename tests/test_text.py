"""Tests for transcript text cleanup (pure functions)."""

from vibeflow.core.text import clean_transcript, expand_snippets, preview, with_trailing_space


def test_collapse_and_strip():
    assert clean_transcript("  hello    world  ") == "hello world"


def test_snippets_basic_and_noop():
    assert expand_snippets("hi", None) == "hi"
    assert expand_snippets("hi", {}) == "hi"
    assert expand_snippets("", {"a": "b"}) == ""
    snips = {"my email": "you@example.com"}
    assert expand_snippets("send to my email please", snips) == "send to you@example.com please"


def test_snippets_case_insensitive():
    assert expand_snippets("My Email", {"my email": "x@y.com"}) == "x@y.com"


def test_snippets_longest_first():
    snips = {"email": "E", "my email": "ME"}
    assert expand_snippets("my email", snips) == "ME"


def test_snippets_whole_phrase_only():
    # "email" must not fire inside "emails"; trigger needs word boundaries.
    assert expand_snippets("emails", {"email": "X"}) == "emails"
    assert expand_snippets("myemail", {"email": "X"}) == "myemail"


def test_snippets_replacement_with_special_chars():
    # Replacement containing regex-special chars ($, \) is inserted literally.
    assert expand_snippets("say sig", {"sig": r"Best, A\B $1"}) == r"say Best, A\B $1"


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
