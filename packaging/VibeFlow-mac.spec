# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS VibeFlow.app (menu-bar agent).

Build with::

    pyinstaller --noconfirm --clean packaging/VibeFlow-mac.spec

Produces ``release/VibeFlow.app`` — an unsigned dev bundle. It is a menu-bar
*agent* (``LSUIElement`` = true → no Dock icon), declares its microphone usage
string, and carries the ``com.vibeflow.VibeFlow`` bundle id (matched by the
LaunchAgent in ``platform_mac/autostart.py``).

The speech model is **not** bundled (it's large); it downloads on first run into
``~/.config/VibeFlow/models`` and then runs fully offline — same as Windows.

Accessibility / Input Monitoring are TCC permissions granted in System Settings
(no Info.plist key exists for them); only Microphone takes a usage string here.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# SPECPATH is injected by PyInstaller (the directory of this .spec).
ROOT = os.path.dirname(SPECPATH)  # noqa: F821  (repo root: packaging/..)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
from vibeflow import __version__  # noqa: E402

datas, binaries, hiddenimports = [], [], []

# Heavy/native packages PyInstaller can't fully trace on its own.
for pkg in ("faster_whisper", "ctranslate2", "tokenizers", "av", "onnxruntime",
            "rumps", "llama_cpp"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass  # optional (e.g. onnxruntime) — skip if not installed

hiddenimports += collect_submodules("vibeflow")
datas += collect_data_files("vibeflow.resources")

# PyObjC bridges the Mac "hands" import (lazily) — name them so they're frozen in.
hiddenimports += [
    "objc", "AppKit", "Foundation", "Quartz",
    "ApplicationServices", "HIServices", "AVFoundation",
]

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "scripts", "launch_mac.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["comtypes", "win32api", "win32con", "win32gui", "pywin32"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VibeFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI/agent app — no terminal window
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VibeFlow",
)

app = BUNDLE(
    coll,
    name="VibeFlow.app",
    icon=os.path.join(ROOT, "build", "VibeFlow.icns"),
    bundle_identifier="com.vibeflow.VibeFlow",
    version=__version__,
    info_plist={
        "CFBundleName": "VibeFlow",
        "CFBundleDisplayName": "VibeFlow",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSUIElement": True,            # menu-bar agent: no Dock icon
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription":
            "VibeFlow records your voice so it can transcribe it into text on "
            "this Mac. Audio is processed locally and never leaves your computer.",
    },
)
