"""Tests for the offline Stage-4 curation (pure functions)."""

from vibeflow.curate import curate


def test_empty_and_none():
    assert curate("") == ""
    assert curate(None) == ""


def test_capitalize_sentences():
    assert curate("hello world. how are you?") == "Hello world. How are you?"


def test_lone_i_pronoun():
    assert curate("i think i am right") == "I think I am right"


def test_i_contractions():
    assert curate("i'm sure i've tried and i'll win") == "I'm sure I've tried and I'll win"


def test_spoken_new_line():
    assert curate("line one new line line two") == "Line one\nLine two"


def test_spoken_new_paragraph():
    assert curate("intro new paragraph body") == "Intro\n\nBody"


def test_punctuation_spacing():
    assert curate("hello ,world .next thing") == "Hello, world. Next thing"


def test_decimal_not_split():
    assert curate("it is 3.5 meters tall") == "It is 3.5 meters tall"


def test_toggles_off():
    # With everything off, only whitespace strip happens.
    assert curate(
        "i said new line ok",
        spoken_commands=False,
        capitalize_sentences=False,
        fix_pronoun_i=False,
    ) == "i said new line ok"
