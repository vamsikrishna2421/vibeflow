# 🛠️ VibeFlow Developer Guide

Technical documentation for building, running, testing, packaging, and extending
VibeFlow.

## Contents

- [Overview](#overview)
- [Project layout](#project-layout)
- [Architecture & data flow](#architecture--data-flow)
- [Module reference](#module-reference)
- [Run from source](#run-from-source)
- [Testing](#testing)
- [Building a standalone .exe](#building-a-standalone-exe)
- [Design decisions & trade-offs](#design-decisions--trade-offs)
- [Extending VibeFlow](#extending-vibeflow)
- [Mobile roadmap](#mobile-roadmap)

---

## Overview

VibeFlow is a Python tray application that performs **offline** speech-to-text
and routes the result either into the focused text field or onto the clipboard.

- **Language:** Python 3.9+
- **Speech engine:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (CTranslate2 backend; CPU `int8` or CUDA `float16`).
- **Primary platform:** Windows 10/11. The code is structured so audio,
  transcription, hotkeys, output, and config are cross-platform; only
  **focus detection** is Windows-specific (with safe fallbacks elsewhere).

Design goals: **private by default**, **never crash on a bad environment**
(every external interaction degrades gracefully), and **testable core logic**
(pure functions for the tricky decisions).

---

## Project layout

```
vibeflow/
├── Install-VibeFlow.bat      # double-click installer (delegates to scripts/)
├── Start-VibeFlow.bat        # double-click windowless launcher (pythonw)
├── README.md                 # friendly overview
├── CHANGELOG.md
├── LICENSE                   # MIT
├── pyproject.toml            # packaging, entry points, pytest config
├── requirements.txt          # runtime dependencies
│                             # (user settings live in %APPDATA%\VibeFlow at runtime)
├── src/
│   └── vibeflow/
│       ├── __init__.py        # version / app name
│       ├── __main__.py        # CLI: run, --doctor, --list-devices, ...
│       ├── app.py             # state machine + system-tray UI
│       ├── config.py          # load/merge/save YAML settings
│       ├── text.py            # pure transcript cleanup helpers
│       ├── audio.py           # microphone capture (sounddevice)
│       ├── transcriber.py     # faster-whisper wrapper
│       ├── hotkey.py          # global hotkeys + key parsing (pynput)
│       ├── focus_detect.py    # is the focused element editable? (UIA/Win32)
│       ├── output.py          # route + insert text (paste/keystroke/clipboard)
│       ├── notifier.py        # short beeps (winsound)
│       └── resources/
│           └── default_config.yaml   # commented settings template
├── scripts/
│   ├── install.ps1            # venv + install + model download
│   ├── run.ps1               # run with a console (pass-through args)
│   ├── build_exe.ps1         # PyInstaller build
│   └── launch.py             # PyInstaller entry script
├── tests/                    # pytest unit tests (no mic/model/GUI needed)
└── docs/
    ├── USER_GUIDE.md
    └── DEVELOPERS.md
```

---

## Architecture & data flow

```
   ┌──────────┐   press/hold trigger    ┌──────────────────────────┐
   │ hotkey.py │ ──────────────────────► │ app.py  (state machine)  │
   └──────────┘   release/toggle         └────────────┬─────────────┘
                                                       │ start/stop
                                                       ▼
                                              ┌──────────────────┐
                                              │ audio.py Recorder │  16kHz mono float32
                                              └─────────┬────────┘
                                                        │ numpy audio
                                                        ▼
                                            ┌────────────────────────┐
                                            │ transcriber.py (Whisper)│  offline
                                            └───────────┬────────────┘
                                                        │ raw text
                                                        ▼
                                              ┌──────────────────┐
                                              │ text.py cleanup   │
                                              └─────────┬────────┘
                                                        │ clean text
                              focus_detect.py           ▼
                          (editable? )──────►  ┌──────────────────┐
                                               │ output.py deliver │
                                               └───────┬───────────┘
                                        type at cursor │ or │ copy to clipboard
                                                       ▼     ▼
```

**Threading model:**

- The tray icon (`pystray`) owns the main thread (`icon.run`).
- `pynput` listeners run on their own threads and invoke `start_recording` /
  `stop_recording`.
- Transcription runs on a short-lived **worker thread** so the hotkey/UI threads
  never block. State transitions are guarded by a `threading.Lock`.
- The model is **preloaded** in the background at startup to minimise first-use
  latency.

---

## Module reference

| Module | Responsibility | Heavy imports (lazy) |
|--------|----------------|----------------------|
| `text.py` | Normalise transcripts; previews | none (pure) |
| `config.py` | Defaults, deep-merge, dotted get/set, YAML/JSON I/O | `yaml` |
| `focus_detect.py` | `EDITABLE` / `NON_EDITABLE` / `UNKNOWN` | `comtypes`, `ctypes` |
| `output.py` | `decide_target` (pure) + insert/paste/clipboard | `pyperclip`, `pynput` |
| `audio.py` | `Recorder`, device listing | `sounddevice`, `numpy` |
| `transcriber.py` | `Transcriber` (load + transcribe), device resolution | `faster_whisper`, `ctranslate2` |
| `hotkey.py` | `HotkeyManager`, combo/key parsing (pure) | `pynput` |
| `notifier.py` | Start/stop/error beeps | `winsound` |
| `app.py` | Orchestration, tray menu, notifications | `pystray`, `PIL` |
| `__main__.py` | CLI / self-test | — |

> **Convention:** every module keeps *only standard-library imports at the top*.
> Third-party libraries are imported inside functions/methods. This keeps the
> package importable (and the test-suite runnable) on machines that don't have
> the audio/ML stack installed, and makes failures explicit and friendly.

---

## Run from source

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (use source .venv/bin/activate on *nix)
pip install -e ".[dev]"

python -m vibeflow --doctor      # environment self-test
python -m vibeflow --list-devices
python -m vibeflow               # start the tray app
```

Useful flags: `--config PATH`, `--model small`, `--mode push_to_talk`,
`--language en`, `--print-config`, `--download-model`.

---

## Testing

The unit tests cover the pure, high-value logic — transcript cleanup, config
merging, output routing, and hotkey parsing — and require **no microphone,
model, or GUI**.

```bash
pytest               # or: python -m pytest -q
```

`pyproject.toml` adds `src/` to the path (`tool.pytest.ini_options.pythonpath`),
and `tests/conftest.py` does the same when running tests directly, so no install
is needed to run them.

When adding features, keep decision logic in pure functions (like
`decide_target` and `clean_transcript`) and unit-test those; mock or isolate the
I/O at the edges.

---

## Building a standalone .exe

For distributing to machines without Python:

```powershell
scripts\build_exe.ps1
# output: release\VibeFlow\VibeFlow.exe
```

This uses PyInstaller with `--collect-all` for `faster_whisper`, `ctranslate2`,
`tokenizers`, `av`, and `onnxruntime`, and bundles `vibeflow.resources`.

**Notes & caveats:**

- The **speech model is not bundled** (it's large and license-friendly to fetch
  at runtime). It downloads on first use into `%APPDATA%\VibeFlow\models`.
- The resulting folder is large (hundreds of MB) due to the ML runtime.
- Packaging native ML wheels is inherently finicky; if a hidden import is
  missing at runtime, add it via `--hidden-import` / `--collect-all`.
- For most users the **installer script is the recommended distribution** — it's
  smaller, faster, and easier to update.

---

## Design decisions & trade-offs

- **faster-whisper over openai-whisper / whisper.cpp.** Pure-Python install,
  strong CPU performance via CTranslate2 (`int8`), GPU support, and accepts a
  numpy array directly. whisper.cpp would be lighter to ship but adds a native
  build/binding burden.
- **Paste-based insertion by default.** Setting the clipboard and sending
  `Ctrl+V` is far more reliable for long text and Unicode than simulating each
  keystroke, and it respects keyboard layout/IME. We save and restore the user's
  previous clipboard. A `keystroke` mode is available for apps that block paste.
- **UI Automation for focus detection.** Classic Win32 child-window checks fail
  for Chromium/Electron/UWP apps. UIA's `GetFocusedElement` + control-type/value
  pattern works across modern apps; Win32 `GetGUIThreadInfo` is the fallback.
- **"Unknown focus → clipboard."** When we can't *confirm* an editable target, we
  default to the clipboard (configurable via `output.auto_fallback`). This
  matches the requested behaviour and avoids dumping text into the wrong place.
- **Lazy heavy imports.** Keeps the package importable and testable in minimal
  environments and turns missing dependencies into clear, actionable messages.

---

## Extending VibeFlow

- **New trigger styles:** extend `HotkeyManager` (e.g. double-tap detection).
- **Post-processing / commands:** add steps in `text.py` (e.g. spoken-command
  mapping, custom vocabulary, replacements) and call them from `app._process`.
- **Streaming/partial results:** swap the batch `transcribe` for a streaming loop
  in `transcriber.py` and emit interim text.
- **Cross-platform output:** implement `focus_detect` for macOS (AXUIElement) and
  Linux (AT-SPI); `decide_target` already abstracts the decision.
- **Settings UI:** the tray already exposes the common toggles; a small settings
  window could edit `config.yaml` and call the existing reload path.

---

## Mobile roadmap

The user request mentioned phones. Being straight about it: **this Python tray
app cannot run as-is on Android or iOS** — mobile platforms use different
languages, sandboxing, and input systems. A real mobile app is a **separate
project**. Here are the honest, concrete options, easiest first:

### Option A — Use built-in offline dictation today (no app needed)
Both major mobile keyboards already do offline voice typing, which covers the
"talk anywhere on mobile" need immediately:
- **Android (Gboard):** Settings → *Voice typing* → enable **"Faster voice
  typing"/on-device** to dictate offline into any text field via the mic key.
- **iOS:** **Dictation** runs on-device for many languages and types into any
  field via the mic key on the keyboard.

This is the pragmatic recommendation for users *right now*.

### Option B — A dedicated Android app (shares the concept, not the code)
The most realistic custom build:
- **STT engine:** `whisper.cpp` compiled for Android (ARM NEON), or a
  TensorFlow-Lite Whisper build, running fully on-device.
- **System-wide insertion:** implement an **Input Method Editor (IME / custom
  keyboard)** so dictated text lands in any app — the mobile equivalent of
  VibeFlow's "type anywhere". A floating-button **Accessibility Service** is an
  alternative for insertion.
- **Trigger:** a keyboard mic button, a quick-settings tile, or an Assistant
  shortcut (mobile OSes don't allow global hardware-hotkey capture like desktop).
- **Clipboard fallback:** identical idea — if insertion isn't possible, copy and
  notify.
- **UI:** Kotlin + Jetpack Compose; package the model in assets or download once.

### Option C — Cross-platform shell (Flutter/React Native)
A Flutter/RN front-end calling a native Whisper module via FFI. Shares UI across
Android/iOS, but **system-wide insertion still requires native IME/Accessibility
work** per platform, so the savings are mostly in the UI layer.

### Why not "just reuse the Python code"?
Tools like BeeWare/Kivy can run Python on Android, but they **cannot provide a
system-wide keyboard/IME or global hotkeys**, which are the core of this product.
You'd end up writing the native insertion layer anyway — so a native Android app
(Option B) is the right architecture for a true mobile version.

**Suggested path:** ship the Windows tool now (this repo), recommend Option A to
mobile users immediately, and scope Option B as a follow-up project that reuses
VibeFlow's *concepts* (trigger → record → on-device STT → smart insert/clipboard)
rather than its Python code.
