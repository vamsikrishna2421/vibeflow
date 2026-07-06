"""
Shared visual language for VibeFlow's Tk windows — ONE source of truth so every
dialog reads as the same product (the design review flagged a two-palette split:
Settings was blue/OS-adaptive while onboarding/license/update were a different
hardcoded purple, on the wrong font on macOS).

Tokens here are the deliberately-dark "branded" surface used by the hero dialogs
(onboarding / update / license). The accent — a signature iris, not the generic
"AI lavender" — is the brand and should be the accent everywhere, including the
OS-adaptive Settings window (inject BRAND into winteme). One warm accent (LIVE)
is reserved exclusively for "VibeFlow is hearing you".

Copied to both platform branches (like audio.py); keep them identical.
"""
from __future__ import annotations

import sys

# -- palette -----------------------------------------------------------------
BG = "#0D0A18"      # blue-black ground (deeper + less muddy than the old #141020)
CARD = "#191527"    # elevated surface
CARD_HI = "#221C36"  # hover / raised
LINE = "#2A2440"    # hairline border on cards (the subtle "elevated" edge)
INK = "#F4F2FB"     # primary text
SOFT = "#B4AECF"    # secondary text
FAINT = "#7C769A"   # tertiary / captions
BRAND = "#7C5CFF"   # signature iris (replaces the AI-default #8b6dff)
BRAND_HI = "#9B80FF"  # brand hover
LIVE = "#FFB454"    # warm amber — ONLY for the listening / "hearing you" state
OK = "#3ED598"
ERR = "#FF6B6B"
ON_BRAND = "#FFFFFF"  # text on a filled brand button

# -- type scale --------------------------------------------------------------
DISPLAY, TITLE, BODY, LABEL, CAPTION = 22, 16, 13, 11, 10


def font(size: int, weight: str = "normal"):
    """Platform-correct UI font (Segoe on Windows, Helvetica Neue on macOS —
    never hardcode Segoe on the Mac, where it silently falls back off-brand)."""
    family = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
    return (family, size, weight) if weight != "normal" else (family, size)


# Monochrome glyphs (real text, not colour emoji — emoji were the "unfinished"
# tell). Tint them with the palette at the call site.
G_CHECK = "✓"
G_WARN = "⚠"
G_UP = "↑"
G_DOWN = "↓"
G_REFRESH = "↻"
G_DOT = "●"


def primary_button(parent, text: str, command, width: int = 168, height: int = 40):
    """A filled iris 'primary' button drawn on a Canvas — reliable and on-brand on
    both platforms (bare tk.Button renders native-grey, especially on macOS). Use
    exactly one per window for the single most important action."""
    import tkinter as tk

    c = tk.Canvas(parent, width=width, height=height, bg=parent["bg"],
                  highlightthickness=0, cursor="hand2")
    r = height // 2

    def _round(fill):
        c.delete("all")
        c.create_oval(0, 0, height, height, fill=fill, outline="")
        c.create_oval(width - height, 0, width, height, fill=fill, outline="")
        c.create_rectangle(r, 0, width - r, height, fill=fill, outline="")
        c.create_text(width / 2, height / 2, text=text, fill=ON_BRAND,
                      font=font(BODY, "bold"))

    _round(BRAND)
    c.bind("<Enter>", lambda e: _round(BRAND_HI))
    c.bind("<Leave>", lambda e: _round(BRAND))
    c.bind("<Button-1>", lambda e: command())
    return c


def rounded_card(parent, **pack):
    """A card frame with a hairline border for the subtle 'elevated surface' look.
    (Tk frames can't round corners; the 1px LINE border is the affordable premium
    cue.) Returns the inner frame to pack content into."""
    import tkinter as tk

    outer = tk.Frame(parent, bg=LINE)
    outer.pack(**pack)
    inner = tk.Frame(outer, bg=CARD)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return inner
