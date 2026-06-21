"""Configuration loading, merging and persistence for VibeFlow.

Settings live in a single human-editable YAML file in the user's app-data
folder (``%APPDATA%\\VibeFlow\\config.yaml`` on Windows). On first run the file
is created from a commented template. Loading always starts from a complete set
of defaults and overlays the user's file on top, so upgrades that add new
settings keep working without the user editing anything.

Only the standard library is imported at module load time. PyYAML is imported
lazily inside the functions that need it, which keeps the pure logic (deep
merge, dotted get/set) testable without any third-party packages installed.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults — the single source of truth for the *shape* of the config. The
# shipped ``resources/default_config.yaml`` mirrors this with friendly comments.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    "model": {
        "size": "base",          # tiny | base | small | medium | large-v3
        "language": "en",        # English by default (unknown values fall back to English)
        "device": "auto",        # auto | cpu | cuda
        "compute_type": "auto",  # auto | int8 | int8_float16 | float16 | float32
    },
    "hotkey": {
        "mode": "push_to_talk",            # push_to_talk only (toggle disabled for now)
        "toggle_combo": "ctrl+win",        # (unused while toggle is disabled)
        "push_to_talk_key": "ctrl+win",    # hold to talk; release to transcribe
    },
    "output": {
        "mode": "auto",              # auto | type | clipboard
        "insertion": "paste",        # paste | keystroke
        "restore_clipboard": True,   # put your old clipboard back after pasting
        "trailing_space": True,      # add a space after inserted text
        "auto_fallback": "clipboard",  # when focus is unknown: clipboard | type
    },
    "audio": {
        "sample_rate": 16000,
        "input_device": "default",   # "default" or a device name/substring/index
        "min_seconds": 0.4,          # ignore accidental ultra-short recordings
        "max_seconds": 120,          # safety cap on a single recording
    },
    "feedback": {
        "sounds": True,          # short beeps on start/stop
        "notifications": True,   # tray pop-up messages
        "overlay": True,         # on-screen status (Listening/Transcribing/Done)
    },
    "text": {
        "strip": True,
        "capitalize_sentences": True,   # capitalise the start of each sentence
        "spoken_commands": True,        # "new line" / "new paragraph" become breaks
        "strip_fillers": False,         # OPT-IN: remove fillers (LLM when AI on, else regex)
        "fillers": [],                  # custom filler list ([] = built-in um/uh/...)
        "capitalize_first": False,
        "remove_trailing_period": False,
        "vocabulary": [],               # domain terms (grows via teach-back; editable)
        "teach_back": True,             # learn from your edits (copy/cut corrected text)
        "ai_learning": False,           # OPT-IN: use a local LLM to spot technical terms
        "teach_back_model": "qwen2.5:3b",  # model used for background term extraction
        "persona": True,                # core feature: learn your domain/tone (on; toggle off in tray)
        "debug_log": False,             # OPT-IN: log raw transcript + correction text for troubleshooting
        # Per-app formatting: adapt the output to the destination app. Only true
        # terminals and code editors are "leave as spoken" out of the box; every
        # other app is unchanged until you add a rule (or accept the Starter Pack).
        "modes": {
            "enabled": True,                 # master switch for per-app formatting
            "rules": [],                     # [{match:{by,value}, outcome}] — your rules override built-ins
            "starter_pack_offered": False,   # has the one-click setup been offered yet
            "deliver_hotkey": "ctrl+shift+v",  # "Deliver here" key (armed only while a dictation is pending)
            "deliver_on_ctrl_v": False,      # OPT-IN: also deliver a pending dictation on Ctrl+V
            "pending_timeout": 60,           # seconds a no-focus dictation waits before it's discarded
        },
        # Text snippets: spoken shortcuts that expand to canonical text. Empty by
        # default (a no-op). Example: {"my email": "you@example.com"}.
        "snippets": {},
        # Dictation history (OPT-IN): keep a local, capped, searchable log of your
        # dictations. Off by default; nothing is stored until you turn it on.
        "history": {
            "enabled": False,   # OPT-IN: record delivered dictations locally
            "max": 500,         # keep only the most recent N entries
        },
    },
    "ai": {
        "enabled": False,            # voice-to-text + AI formatting (needs a local LLM)
        "provider": "ollama",        # ollama (local, runs on your machine)
        "endpoint": "http://127.0.0.1:11434",
        "model": "qwen2.5:3b",       # best at keeping your exact words (1.5b paraphrases)
        "timeout": 20,
        "prompt": "",                # empty = use the built-in formatting prompt
    },
}

APP_DIR_NAME = "VibeFlow"
CONFIG_FILENAME = "config.yaml"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def config_dir() -> Path:
    """Return the per-user directory where settings and logs live."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    """Full path to the user's config file."""
    return config_dir() / CONFIG_FILENAME


def models_dir() -> Path:
    """Where downloaded speech models are cached (kept with the app data)."""
    return config_dir() / "models"


# ---------------------------------------------------------------------------
# Merge helpers (pure)
# ---------------------------------------------------------------------------
def deep_merge(base: dict, override: dict) -> dict:
    """Recursively overlay ``override`` onto a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ---------------------------------------------------------------------------
# Serialisation (YAML for the real file, JSON understood for convenience/tests)
# ---------------------------------------------------------------------------
def _load_file(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).lower().endswith(".json"):
        return json.loads(text) or {}
    import yaml  # lazy: only needed for real YAML files

    return yaml.safe_load(text) or {}


def _dump_file(data: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if str(path).lower().endswith(".json"):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return
    import yaml  # lazy

    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _template_text() -> str:
    """Return the commented YAML template shipped with the package."""
    try:
        from importlib.resources import files

        return (
            files("vibeflow.resources")
            .joinpath("default_config.yaml")
            .read_text(encoding="utf-8")
        )
    except Exception:
        # Fallback: generate from DEFAULTS (loses comments, still valid).
        import yaml

        return yaml.safe_dump(DEFAULTS, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Config object
# ---------------------------------------------------------------------------
class Config:
    """A loaded configuration with dotted access and persistence."""

    def __init__(self, data: dict, path: Path | None = None) -> None:
        self.data = data
        self.path = Path(path) if path else None

    # -- dotted access -----------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError(f"Cannot set '{dotted}': '{part}' is not a section")
        node[parts[-1]] = value

    # -- persistence -------------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            target = config_path()
            self.path = target
        _dump_file(self.data, target)
        return target

    def as_dict(self) -> dict:
        return copy.deepcopy(self.data)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def ensure_user_config(path: Path | None = None) -> Path:
    """Create the user's config file from the template if it doesn't exist."""
    target = Path(path) if path else config_path()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template_text(), encoding="utf-8")
    return target


def load_config(path: Path | None = None, *, create: bool = True) -> Config:
    """Load settings: defaults overlaid with the user's file.

    Args:
        path: Optional explicit config path. Defaults to the per-user location.
        create: If True (default) and the user file is missing, seed it from
            the template before loading.

    Returns:
        A :class:`Config`. Invalid or unreadable files fall back to defaults so
        the app always starts.
    """
    target = Path(path) if path else config_path()
    if create:
        try:
            ensure_user_config(target)
        except Exception:
            pass  # read-only filesystem etc. — fall back to in-memory defaults

    user: dict = {}
    if target.exists():
        try:
            loaded = _load_file(target)
            if isinstance(loaded, dict):
                user = loaded
        except Exception:
            user = {}  # malformed file — ignore and use defaults

    merged = deep_merge(DEFAULTS, user)
    return Config(merged, target)
