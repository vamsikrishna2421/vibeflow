"""Render the VibeFlow logo as tray icons and a Windows .ico.

The brand mark is reproduced with Pillow (no SVG renderer dependency) so the
exact same artwork is used for the system-tray icon, the packaged executable,
and the installer. Everything is drawn on a 256x256 canvas and downscaled with
high-quality resampling for crisp small icons.
"""

from __future__ import annotations

# Brand palette (from resources/logos/vibeflow-icon.svg).
_BG_TOP = (27, 42, 74)     # #1B2A4A
_BG_BOTTOM = (14, 23, 48)  # #0E1730
_BLUE = (59, 111, 232)     # #3B6FE8
_PURPLE = (138, 92, 246)   # #8A5CF6
_ORANGE = (245, 165, 36)   # #F5A524

# Waveform bars: (centre_x, half_height) in the 256 coordinate space.
_BARS = ((72, 22), (110, 50), (148, 74), (186, 40))
_STROKE = 18               # bar/curve thickness
_CENTER_Y = 128
_GRAD_X0, _GRAD_X1 = 64, 200

# State accent dots.
_STATE_COLORS = {
    "recording": (220, 50, 50),
    "busy": (230, 170, 40),
}


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _flow_color(t: float):
    """Sample the blue -> purple -> orange flow gradient at 0..1."""
    t = max(0.0, min(1.0, t))
    if t <= 0.55:
        return _lerp(_BLUE, _PURPLE, t / 0.55)
    return _lerp(_PURPLE, _ORANGE, (t - 0.55) / 0.45)


def _bar_color(x: int):
    return _flow_color((x - _GRAD_X0) / (_GRAD_X1 - _GRAD_X0))


def _cubic(p0, p1, p2, p3, t):
    mt = 1 - t
    x = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0]
         + 3 * mt * t**2 * p2[0] + t**3 * p3[0])
    y = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1]
         + 3 * mt * t**2 * p2[1] + t**3 * p3[1])
    return x, y


def render_logo(size: int = 256):
    """Return an RGBA PIL image of the VibeFlow icon at ``size`` pixels."""
    from PIL import Image, ImageDraw

    scale = 4 if size <= 128 else 1          # supersample small icons
    s = 256 * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Rounded-square background with a vertical gradient.
    gradient = Image.new("RGBA", (s, s))
    gpix = gradient.load()
    for y in range(s):
        color = _lerp(_BG_TOP, _BG_BOTTOM, y / (s - 1)) + (255,)
        for x in range(s):
            gpix[x, y] = color
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=58 * scale, fill=255)
    img.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    r = (_STROKE // 2) * scale

    # Waveform bars (each a vertical capsule in a sampled gradient colour).
    for x, half in _BARS:
        cx = x * scale
        y0 = (_CENTER_Y - half) * scale
        y1 = (_CENTER_Y + half) * scale
        draw.rounded_rectangle([cx - r, y0 - r, cx + r, y1 + r], radius=r,
                               fill=_bar_color(x) + (255,))

    # Orange flourish (cubic bezier drawn as a round brush stroke).
    p0, p1, p2, p3 = (204, 128), (220, 128), (222, 110), (234, 100)
    steps = 48
    for i in range(steps + 1):
        x, y = _cubic(p0, p1, p2, p3, i / steps)
        cx, cy = x * scale, y * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_ORANGE + (255,))

    if scale != 1:
        img = img.resize((256, 256), Image.LANCZOS)
    if size != 256:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def make_tray_image(state: str = "idle", size: int = 64):
    """Return the tray icon for a given state (idle / recording / busy)."""
    from PIL import ImageDraw

    img = render_logo(size).copy()
    accent = _STATE_COLORS.get(state)
    if accent:
        draw = ImageDraw.Draw(img)
        d = max(8, round(size * 0.40))
        x1, y1 = size - 1, size - 1
        x0, y0 = x1 - d, y1 - d
        draw.ellipse([x0 - 2, y0 - 2, x1, y1], fill=(14, 23, 48, 255))  # dark ring
        draw.ellipse([x0, y0, x1 - 2, y1 - 2], fill=accent + (255,))
    return img


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Write a multi-resolution Windows .ico of the logo to ``path``."""
    base = render_logo(256)
    base.save(str(path), format="ICO", sizes=[(s, s) for s in sizes])
