"""Tests for the offline Stage-4 curation (pure functions)."""

from vibeflow.curate import curate, remove_fillers


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


def test_strip_fillers_basic():
    assert curate("um so the build uh failed", strip_fillers=True) == "So the build failed"
    assert (
        curate("I think um we should uh ship it", strip_fillers=True)
        == "I think we should ship it"
    )


def test_strip_fillers_consecutive_fixpoint():
    assert remove_fillers("ship um uh now") == "ship now"
    assert remove_fillers("go um uh um home") == "go home"


def test_strip_fillers_comma_bracketed_preserved():
    # Comma-bracketed fillers are deliberately LEFT (list-vs-disfluency undecidable):
    # never merges a list, never strands a comma.
    assert remove_fillers("buy milk, um, eggs, and bread") == "buy milk, um, eggs, and bread"
    assert remove_fillers("a, um, uh, b") == "a, um, uh, b"
    assert remove_fillers("send, um, EUR 12,50") == "send, um, EUR 12,50"


def test_strip_fillers_boundary_protected():
    # whitespace-anchored: hyphen/quote/paren/period/word block the match
    for s in ("uh-huh", "uh-uh", "(um)", '"um"', "um.", "git-er-done", "scrum", "metoprolol er twice"):
        assert remove_fillers(s) == s


def test_strip_fillers_f1_trailing_glued_comma():
    # F1: a trailing filler after a glued comma must not strand the comma.
    assert remove_fillers("ship it, um") == "ship it"
    assert remove_fillers("done, uh") == "done"
    assert remove_fillers("done um  ") == "done"


def test_strip_fillers_newlines_and_filler_only_lines():
    assert remove_fillers("first um\nsecond uh third") == "first\nsecond third"
    assert remove_fillers("a\num\nb") == "a\nb"          # filler-only line dropped
    assert remove_fillers("a\n\nb") == "a\n\nb"          # intentional blank line kept
    assert remove_fillers("second uh\r\nthird um\r\n") == "second\nthird\n"  # CRLF


def test_strip_fillers_preserves_case_bearing_tokens():
    # The capitalize guard must not corrupt iOS / pH / eBay at a sentence start.
    assert curate("um iOS crashed", strip_fillers=True) == "iOS crashed"
    assert curate("uh pH dropped", strip_fillers=True) == "pH dropped"


def test_strip_fillers_preserves_real_words():
    # 'like', 'better' must NOT be touched (only vocalized fillers).
    text = "I like it and the weather is better today."
    assert curate(text, strip_fillers=True) == text


def test_strip_fillers_off_by_param():
    assert "um" in curate("um hello", strip_fillers=False).lower()


def test_toggles_off():
    # With everything off, only whitespace strip happens.
    assert curate(
        "i said new line ok",
        spoken_commands=False,
        capitalize_sentences=False,
        fix_pronoun_i=False,
    ) == "i said new line ok"
