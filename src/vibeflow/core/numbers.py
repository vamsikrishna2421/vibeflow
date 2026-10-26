"""Spoken numbers -> digits for transcripts (English inverse text normalization).

Whisper writes "503" and "2.5 liters" by itself. Phonon-2 (a Parakeet-TDT model)
writes what was said -- "five hundred three", "two point five liters" -- so its
output goes through :func:`spoken_numbers_to_digits` to read like typed text.

Conservative by design, because a wrong digit is worse than a spelled-out number:

* Cardinals of two or more words, or ten and above, become digits
  ("two hundred and fifty" -> "250", "seventeen" -> "17"). A lone million /
  billion keeps its name ("three million" -> "3 million").
* Decimals and dotted numbers: "2.5", "0.8", "2.0", "192.168.0.14".
* Times: "2:45 PM", "11:30 AM" (with AM/PM, or after "at"), and "5 PM".
* Years: "1999", "2024", "2005" ("nineteen ninety nine", "twenty oh five").
* Spoken digit strings of three or more: "5558675309", "503".
* Ordinals in dates: "March 3rd", "the 17th", "the 3rd of May".
* Zero to nine stay words in prose ("one of them", "two kids") unless the
  context is numeric: percent, AM/PM, a decimal, or a cue such as "version",
  "port" or "page".
* Anything ambiguous ("two three", "fifty-fifty", "ten four") is left as spoken.

No thousands separators are added: ports, years and codes must not get commas.
Pure Python with no dependencies, so it is safe in the frozen app and in CI.
"""

from __future__ import annotations

import re

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine".split())}
_TEENS = {w: i + 10 for i, w in enumerate(
    "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen".split())}
_TENS = {w: (i + 2) * 10 for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9,
           "trillion": 10 ** 12}
_NAMED_SCALES = ("million", "billion", "trillion")  # kept as words: "3 million"
_ORD_UNITS = {w: i + 1 for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth".split())}
_ORD_TEENS = {w: i + 10 for i, w in enumerate(
    "tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth "
    "seventeenth eighteenth nineteenth".split())}
_ORD_TENS = {w: (i + 2) * 10 for i, w in enumerate(
    "twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth "
    "ninetieth".split())}
_ORDINALS = {**_ORD_UNITS, **_ORD_TEENS, **_ORD_TENS}
_MONTHS = frozenset(
    "january february march april may june july august september october "
    "november december".split())

# Words right before a lone zero..nine that make it a number ("version 2").
# Not "no" / "number": "no one", "the number one priority" are prose.
_CUE_WORDS = frozenset(
    "version v extension ext port room floor page chapter step level "
    "option line row column item figure table section episode season volume "
    "round phase stage tier gate channel track python ios macos windows android "
    "java gen generation grade apartment apt suite unit platform terminal "
    "building bus route".split())

_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*|\s+|.", re.S)
_AMPM = re.compile(r"\s*(?:AM|PM|pm|[AaPp]\.[Mm]\.)(?![A-Za-z])")
_PERCENT = re.compile(r"\s*(?:%|per ?cent\b)", re.I)
_OF_MONTH = re.compile(
    r"\s+of\s+(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\b", re.I)


def _kind(word: str) -> str | None:
    if word in _UNITS:
        return "unit"
    if word in _TEENS:
        return "teen"
    if word in _TENS:
        return "tens"
    if word == "hundred":
        return "hundred"
    if word in _SCALES:
        return "scale"
    if word in _ORD_UNITS:
        return "ord_unit"
    if word in _ORD_TEENS or word in _ORD_TENS:
        return "ord_big"
    return None


_STARTS = ("unit", "teen", "tens", "ord_unit", "ord_big")
_CARDINAL_SMALL = ("unit", "teen", "tens")


class _Group:
    """One parsed number inside a run of number words."""

    __slots__ = ("value", "digits", "words", "ordinal", "named")

    def __init__(self, value: int, digits: str | None, words: int,
                 ordinal: bool = False, named: str | None = None) -> None:
        self.value = value      # numeric value
        self.digits = digits    # set for a lone zero..nine ("5") or "oh five" ("05")
        self.words = words      # how many spoken words it used
        self.ordinal = ordinal  # "third", "twenty first"
        self.named = named      # "3 million": the scale word to keep, if any


# ---------------------------------------------------------------- collecting
def _collect(toks: list, i: int) -> list:
    """The run of number words starting at token ``i``, as (word, token index).

    Words are joined by plain spaces or a hyphen. "and", "oh" and "point" join
    a run only where they belong to the number ("two hundred and fifty",
    "eleven oh five", "two point five"); an ordinal always ends the run.
    """
    run: list = []
    k = i
    after_point = False
    while k < len(toks):
        w = toks[k].lower()
        prev = run[-1][0] if run else None
        pk = _kind(prev) if prev else None
        nxt = _next_word(toks, k)
        nk = _kind(nxt) if nxt else None
        if after_point:
            ok = w in _UNITS or w == "oh" or (w == "point" and nxt in _UNITS)
        elif w == "and":
            ok = pk in ("hundred", "scale") and nk in _STARTS
        elif w == "oh":
            ok = pk in _CARDINAL_SMALL and nk == "unit"
        elif w == "point":
            ok = pk in ("unit", "teen", "tens", "hundred", "scale") and (
                nk == "unit" or nxt == "oh")
        else:
            kind = _kind(w)
            if kind in _CARDINAL_SMALL:
                ok = True
            elif kind == "hundred":
                ok = pk in _CARDINAL_SMALL
            elif kind == "scale":
                ok = pk in ("unit", "teen", "tens", "hundred")
            elif kind in ("ord_unit", "ord_big"):
                ok = prev is None or pk in ("hundred", "scale") or prev == "and" or (
                    kind == "ord_unit" and pk == "tens")
            else:
                ok = False
        if not ok:
            break
        run.append((w, k))
        if w == "point":
            after_point = True
        if _kind(w) in ("ord_unit", "ord_big"):
            break
        sep = _separator_end(toks, k + 1)
        if sep is None:
            break
        k = sep
    while run and run[-1][0] in ("and", "oh", "point"):  # never end on a joiner
        run.pop()
    return run


def _separator_end(toks: list, k: int) -> int | None:
    """Index of the next word if ``toks[k]`` is a run separator, else None."""
    if k >= len(toks):
        return None
    t = toks[k]
    if t == "-" or (t.isspace() and "\n" not in t):
        if k + 1 < len(toks) and toks[k + 1][:1].isalpha():
            return k + 1
    return None


def _next_word(toks: list, k: int) -> str | None:
    nxt = _separator_end(toks, k + 1)
    return toks[nxt].lower() if nxt is not None else None


# ------------------------------------------------------------------- parsing
def _parse_groups(words: list) -> list | None:
    """Split run words (without "point") into numbers; None if malformed."""
    groups = []
    i = 0
    while i < len(words):
        group, j = _parse_one(words, i)
        if j == i:
            return None
        groups.append(group)
        i = j
    return groups


def _parse_one(words: list, i: int) -> tuple:
    if words[i] == "oh":  # "oh five" inside a run -> "05"
        if i + 1 < len(words) and words[i + 1] in _UNITS:
            d = _UNITS[words[i + 1]]
            return _Group(d, "0%d" % d, 2), i + 2
        return None, i
    start = i
    total = cur = 0
    last = None
    cap = None          # the last scale used; a later scale must be smaller
    scales = 0
    head = 0            # the multiplier of a single trailing named scale
    ordinal = False
    while i < len(words):
        w = words[i]
        kind = _kind(w)
        if kind == "unit" and last in (None, "tens", "hundred", "scale", "and"):
            cur += _UNITS[w]
        elif kind == "teen" and last in (None, "hundred", "scale", "and"):
            cur += _TEENS[w]
        elif kind == "tens" and last in (None, "hundred", "scale", "and"):
            cur += _TENS[w]
        elif kind == "hundred" and last in _CARDINAL_SMALL and 0 < cur < 100:
            cur *= 100
        elif kind == "scale" and last in ("unit", "teen", "tens", "hundred") \
                and cur > 0 and (cap is None or _SCALES[w] < cap):
            head = cur
            total += cur * _SCALES[w]
            cur = 0
            cap = _SCALES[w]
            scales += 1
        elif w == "and" and last in ("hundred", "scale"):
            pass
        elif kind == "ord_unit" and last in (None, "tens", "hundred", "scale", "and"):
            cur += _ORD_UNITS[w]
            ordinal = True
            i += 1
            break
        elif kind == "ord_big" and last in (None, "hundred", "scale", "and"):
            cur += _ORDINALS[w]
            ordinal = True
            i += 1
            break
        else:
            break
        last = "and" if w == "and" else kind
        i += 1
    used = i - start
    if used == 0:
        return None, i
    value = total + cur
    digits = str(value) if used == 1 and words[start] in _UNITS else None
    named = None
    if scales == 1 and cur == 0 and last == "scale" and words[i - 1] in _NAMED_SCALES:
        named = words[i - 1]
        value = head  # rendered as "<head> million"
    return _Group(value, digits, used, ordinal, named), i


# ----------------------------------------------------------------- rendering
def _suffix(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _cardinal(g: _Group) -> str:
    return "%d %s" % (g.value, g.named) if g.named else str(g.value)


def _numeric_cue(prev: str, rest: str) -> bool:
    return (prev.lower() in _CUE_WORDS or bool(_PERCENT.match(rest))
            or bool(_AMPM.match(rest)))


def _ordinal_context(value: int, prev: str, rest: str) -> bool:
    p = prev.lower()
    if p in _MONTHS and (p != "may" or prev == "May"):
        return True
    if _OF_MONTH.match(rest):
        return True
    return p == "the" and value >= 10


def _two_digit(g: _Group) -> str | None:
    """Minutes or a year's last two digits: "forty five" -> "45", "oh five" -> "05"."""
    if g.ordinal or g.named:
        return None
    if g.digits and len(g.digits) == 2:
        return g.digits
    if g.digits is None and 10 <= g.value <= 99 and g.words <= 2:
        return "%02d" % g.value
    return None


def _as_time(groups: list, prev: str, rest: str) -> str | None:
    h, m = groups
    if h.ordinal or h.named or h.words != 1 or not 1 <= h.value <= 12:
        return None
    mm = _two_digit(m)
    if mm is None or int(mm) > 59:
        return None
    if _AMPM.match(rest) or prev.lower() == "at":
        return "%d:%s" % (h.value, mm)
    return None


def _as_year(groups: list) -> str | None:
    a, b = groups
    if a.ordinal or a.named or a.words != 1 or a.value not in (19, 20):
        return None
    yy = _two_digit(b)
    return "%d%s" % (a.value, yy) if yy else None


def _render(words: list, prev: str, rest: str) -> str | None:
    """Digits for one run of number words, or None to keep it as spoken."""
    segments: list = [[]]
    for w in words:
        if w == "point":
            segments.append([])
        else:
            segments[-1].append(w)
    groups = _parse_groups(segments[0])
    if not groups or any(g.ordinal for g in groups[:-1]):
        return None

    if len(segments) > 1:  # decimal or dotted number
        if any(g.ordinal or g.named for g in groups) or any(not s for s in segments[1:]):
            return None
        tails = ["".join("0" if w == "oh" else str(_UNITS[w]) for w in seg)
                 for seg in segments[1:]]
        if len(groups) > 1 and all(g.digits for g in groups):
            head = "".join(g.digits for g in groups)
        elif len(groups) == 1:
            head = str(groups[0].value)
        else:
            return None
        return head + "." + ".".join(tails)

    if len(groups) == 2:
        clock = _as_time(groups, prev, rest)
        if clock:
            return clock
        year = _as_year(groups)
        if year:
            return year
    if len(groups) > 1:
        if all(g.digits for g in groups):
            joined = "".join(g.digits for g in groups)
            return joined if len(joined) >= 3 else None
        return None  # mixed runs ("ten four", "fifty-fifty") stay as spoken

    g = groups[0]
    if g.ordinal:
        return "%d%s" % (g.value, _suffix(g.value)) if _ordinal_context(
            g.value, prev, rest) else None
    if g.words >= 2 or g.value >= 10:
        return _cardinal(g)
    return _cardinal(g) if _numeric_cue(prev, rest) else None


# Phonon-2's digit and punctuation pieces carry no word-boundary marker, and the
# separate boundary piece often lands one place late, in every decode path:
# "prescribed250", "rose0 .8", "after4 ,500", "March3 rd", "at245 PM".
_SPACE_IN_NUMBER = re.compile(r"(?<=\d) ([.,:])(?=\d)")
_SPACE_BEFORE_PERCENT = re.compile(r"(?<=\d) %")
# A lowercase word (2+ letters) or a Capitalized one (3+) glued to digits. Keeps
# x86, B2B, k8s, MP3, H264, OAuth2 and iOS17, which are written that way.
_GLUED_WORD = re.compile(r"\b([a-z]{2,}|[A-Z][a-z]{2,})(?=\d)")
_SPLIT_ORDINAL = re.compile(r"\b(\d+) (st|nd|rd|th)\b")
_CLOCK = re.compile(
    r"\b(1[0-2]|[1-9])[ :]?([0-5]\d) ?(AM|PM|am|pm|[AaPp]\.[Mm]\.)(?![A-Za-z])")


def tidy_digits(text: str) -> str:
    """Repair the spacing Phonon-2 puts around digits it writes itself.

    "at245 PM" -> "at 2:45 PM", "rose0 .8" -> "rose 0.8", "after4 ,500" ->
    "after 4,500", "March3 rd" -> "March 3rd".
    """
    if not text:
        return text
    out = _SPACE_IN_NUMBER.sub(r"\1", text)
    out = _SPACE_BEFORE_PERCENT.sub("%", out)
    out = _GLUED_WORD.sub(r"\1 ", out)
    out = _SPLIT_ORDINAL.sub(
        lambda m: m.group(1) + m.group(2)
        if _suffix(int(m.group(1))) == m.group(2) else m.group(0), out)
    return _CLOCK.sub(lambda m: "%s:%s %s" % m.groups(), out)


def spoken_numbers_to_digits(text: str) -> str:
    """Rewrite spoken numbers in ``text`` as digits (see the module docstring)."""
    if not text:
        return text
    toks = _TOKEN.findall(text)
    out: list = []
    prev = ""
    i = 0
    while i < len(toks):
        t = toks[i]
        if t[:1].isalpha() and _kind(t.lower()) in _STARTS:
            run = _collect(toks, i)
            if run:
                stop = run[-1][1] + 1
                rest = "".join(toks[stop:stop + 12])
                rendered = _render([w for w, _ in run], prev, rest)
                if rendered is not None:
                    out.append(rendered)
                else:
                    out.extend(toks[i:stop])
                prev = toks[stop - 1]
                i = stop
                continue
        out.append(t)
        if t[:1].isalpha():
            prev = t
        elif not t.isspace():
            prev = ""
        i += 1
    return "".join(out)
