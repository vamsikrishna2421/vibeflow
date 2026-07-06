"""System (Windows) light/dark theme detection + a palette for the Tk windows.

Each manager window (Settings, Vocabulary, Personalized AI) runs as its own
process, so it reads the Windows app theme once at startup and themes itself to
match — the user asked for "Match Windows". Falls back to the dark palette when
the theme can't be read (older behaviour), so nothing ever looks broken.
"""

from __future__ import annotations

DARK = {
    "bg": "#0E1730",
    "card": "#16213E",
    "fg": "#F2F4F8",
    "muted": "#9AA4B2",
    "accent": "#5B8DEF",
    "field": "#16223F",
    "field_fg": "#F2F4F8",
    "danger": "#FF8A8A",
}
LIGHT = {
    "bg": "#F3F3F3",
    "card": "#FFFFFF",
    "fg": "#1A1A1A",
    "muted": "#5F6B7A",
    "accent": "#2563EB",
    "field": "#FFFFFF",
    "field_fg": "#1A1A1A",
    "danger": "#C0392B",
}


def is_dark() -> bool:
    """True if Windows apps are in dark mode. Defaults to dark if we can't tell."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return int(value) == 0
    except Exception:
        return True


def palette() -> dict:
    """The colour palette matching the current Windows app theme, but with the
    VibeFlow brand accent (iris) — so Settings/Models/Persona/Vocabulary share the
    same accent as the hero dialogs instead of the OS-blue (one accent = coherent
    product; the design review's #1 fix). Background stays OS-adaptive."""
    pal = dict(DARK if is_dark() else LIGHT)
    try:
        from . import theme
        pal["accent"] = theme.BRAND
    except Exception:
        pass
    return pal


def style_ttk(root, pal: dict) -> None:
    """Theme the ttk widgets (Combobox, Scrollbar) to match ``pal``. Best-effort."""
    try:
        from tkinter import ttk

        style = ttk.Style(root)
        try:
            style.theme_use("clam")  # the most colour-themable built-in ttk theme
        except Exception:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=pal["field"],
            background=pal["card"],
            foreground=pal["field_fg"],
            arrowcolor=pal["fg"],
            bordercolor=pal["muted"],
            lightcolor=pal["card"],
            darkcolor=pal["card"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", pal["field"])],
            foreground=[("readonly", pal["field_fg"])],
            selectbackground=[("readonly", pal["field"])],
            selectforeground=[("readonly", pal["field_fg"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=pal["card"],
            troughcolor=pal["bg"],
            arrowcolor=pal["fg"],
            bordercolor=pal["bg"],
        )
    except Exception:
        pass
