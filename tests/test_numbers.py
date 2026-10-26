"""Tests for spoken-number -> digit conversion (Phonon-2 output post-processing).

The first group are real Phonon-2 transcripts of the ASR benchmark clips; the
rest pin down the conservative rules (prose numbers stay words).
"""

import pytest

from vibeflow.core.numbers import spoken_numbers_to_digits as itn


@pytest.mark.parametrize("spoken, typed", [
    # --- real Phonon-2 output from benchmarks/asr_cases.json ---------------
    ("The server at one nine two one six eight zero one four returned HDP error "
     "five hundred three after four thousand five hundred milliseconds.",
     "The server at 192168014 returned HDP error 503 after 4500 milliseconds."),
    ("The patient was prescribed two hundred and fifty milligrams of amoxicillin.",
     "The patient was prescribed 250 milligrams of amoxicillin."),
    ("The meeting on march third at two forty five PM was rescheduled to the "
     "seventeenth at eleven thirty AM.",
     "The meeting on march 3rd at 2:45 PM was rescheduled to the 17th at 11:30 AM."),
    ("Add two point five liters of water and heated to three hundred fifty "
     "degrees Fahrenheit for twenty five minutes.",
     "Add 2.5 liters of water and heated to 350 degrees Fahrenheit for 25 minutes."),
    ("Third quarter revenue grew eighteen point seven percent to four point two "
     "million dollars year over year.",
     "Third quarter revenue grew 18.7 percent to 4.2 million dollars year over year."),
    ("The Nasdaq fell two point three percent while the S and P five hundred rose "
     "zero point eight percent on Friday.",
     "The Nasdaq fell 2.3 percent while the S and P 500 rose 0.8 percent on Friday."),
    ("Call me at five five five eight six seven five three zero nine or dial "
     "extension forty two anytime after five PM.",
     "Call me at 5558675309 or dial extension 42 anytime after 5 PM."),
    ("The API uses our oath two point zero with JWT tokens.",
     "The API uses our oath 2.0 with JWT tokens."),
    ("Doctor Smith said the dosage should not exceed three thousand milligrams per day.",
     "Doctor Smith said the dosage should not exceed 3000 milligrams per day."),
    # --- times, years, dates ----------------------------------------------
    ("Meet me at five fifteen.", "Meet me at 5:15."),
    ("The call is at eleven oh five AM.", "The call is at 11:05 AM."),
    ("She was born in nineteen ninety nine and moved in twenty twenty four.",
     "She was born in 1999 and moved in 2024."),
    ("In twenty oh five we left.", "In 2005 we left."),
    ("The twenty first century started in two thousand one.",
     "The 21st century started in 2001."),
    ("The third of May and May fifth, but you may first check.",
     "The 3rd of May and May 5th, but you may first check."),
    ("the one hundred and first time", "the 101st time"),
    # --- digit strings, decimals, scales ----------------------------------
    ("The error was five oh three and four oh four.", "The error was 503 and 404."),
    ("The IP is one nine two point one six eight point zero point one four.",
     "The IP is 192.168.0.14."),
    ("It costs one million dollars, about three point five million euros.",
     "It costs 1 million dollars, about 3.5 million euros."),
    ("Rated ninety nine percent, then five percent.", "Rated 99 percent, then 5 percent."),
    ("Two hundred people came.", "200 people came."),
    ("a twenty-five-year-old", "a 25-year-old"),
    ("Use Python three and version two of the API.", "Use Python 3 and version 2 of the API."),
])
def test_converts_numbers(spoken, typed):
    assert itn(spoken) == typed


@pytest.mark.parametrize("prose", [
    "One of the best things is that no one knows, and someone said one thing.",
    "I have two kids and three dogs, and we walked one mile.",
    "Wait a second, the first time was fine.",
    "It was a hundred times better and a thousand thanks.",
    "We want fifty-fifty odds, ten four.",
    "Schedule the job for zero thirty four every Sunday.",  # ambiguous: left as spoken
    "port eight four hundred and forty three",               # ambiguous: left as spoken
    "The point is two points.",
    "We're at two point",
    "I am five. Am I?",
    "two\nthree",
    "Version 2.5 is out already.",
    "Hello world.",
    "",
])
def test_leaves_prose_and_ambiguous_numbers(prose):
    assert itn(prose) == prose


def test_none_and_whitespace_are_passed_through():
    assert itn(None) is None
    assert itn("   ") == "   "


# --- spacing Phonon-2 puts around digits it writes itself ---------------------
from vibeflow.core.numbers import tidy_digits  # noqa: E402


@pytest.mark.parametrize("raw, fixed", [
    # real Phonon-2 outputs (benchmark passage, various window lengths)
    ("The server at192168014 returned", "The server at 192168014 returned"),
    ("was prescribed250 milligrams", "was prescribed 250 milligrams"),
    ("on March3rd at245 PM", "on March 3rd at 2:45 PM"),
    ("on March3 rd at", "on March 3rd at"),
    ("job for034 every", "job for 034 every"),
    ("hundred rose0 .8 percent", "hundred rose 0.8 percent"),
    ("uses Off2 .0 with", "uses Off 2.0 with"),
    ("error503 after4 ,500 milliseconds", "error 503 after 4,500 milliseconds"),
    ("grew 18 .7 % to", "grew 18.7% to"),
    # Phonon-2.5 English writes clock times without the colon
    ("at 2 45 p.m. was moved to 1130 a.m.", "at 2:45 p.m. was moved to 11:30 a.m."),
])
def test_tidy_digits_repairs_spacing(raw, fixed):
    assert tidy_digits(raw) == fixed


@pytest.mark.parametrize("kept", [
    "OAuth2 and iOS17 on x86 with B2B, k8s, MP3 and H264.",
    "The year 2024 was good, version 2.5 at 5 PM on the 3rd.",
    "It is 11:30 AM and 4,500 items cost 18.7%.",
    "Two hundred rose by 3 percent; 2 rd is not an ordinal.",
    "",
])
def test_tidy_digits_leaves_written_text(kept):
    assert tidy_digits(kept) == kept
