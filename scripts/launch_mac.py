"""macOS entry point — launches the menu-bar app.

Run from the repo root inside the venv::

    python scripts/launch_mac.py

(The packaged ``.app`` built in M5 uses this same entry point.) Kept tiny on
purpose, mirroring ``scripts/launch.py`` for the Windows build.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running straight from a checkout (mirrors the test suite's
# ``pythonpath = ["src"]``) without needing an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vibeflow.platform_mac.menubar import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
