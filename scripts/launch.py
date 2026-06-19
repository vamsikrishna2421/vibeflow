"""PyInstaller entry point.

PyInstaller needs a plain script (not ``python -m package``) as its entry. This
imports and runs VibeFlow's real entry point. Kept tiny on purpose.
"""

from vibeflow.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
