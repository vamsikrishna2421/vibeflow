# VibeFlow — macOS port spec

A working plan for bringing VibeFlow to macOS by **reusing `vibeflow.core`** and
writing only the thin macOS "hands." Read this first, then build.

> **Golden rule:** do **not** modify anything under `src/vibeflow/core/`. That is
> the shared, platform-agnostic brain (Windows already depends on it). The Mac
> app *imports* it. If you find you need to change core, stop and extract the
> change so it stays platform-neutral.

---

## 0. Set up the dev environment (new Mac)

**Prerequisites — install once:**

```bash
# Homebrew (skip if already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Toolchain: Node (for the ruflo / claude-flow CLI via npx), git, Python
brew install node git python@3.12

# Claude Code — native installer (recommended; no Node needed for Claude itself):
curl -fsSL https://claude.ai/install.sh | bash
#   …or via npm:                 npm install -g @anthropic-ai/claude-code
#   …or the macOS desktop app:   https://claude.ai/download
```

Then authenticate (first run opens your browser to log in — needs a Claude
Pro/Max plan or Anthropic API access):

```bash
claude            # start it once to sign in; `claude doctor` to verify the setup
```

**Get the project:**

```bash
git clone https://github.com/vamsikrishna2421/vibeflow
cd vibeflow
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip        # IMPORTANT: old pip tries to *compile*
                                            # pyobjc (a pynput dep) and fails on new
                                            # clang — new pip just grabs the wheel
pip install -r requirements.txt
git checkout -b macos
```

> **`pip install` fails building `pyobjc-core` / `clang failed with exit code 1`?**
> Your pip is too old and is compiling pyobjc from source. Fix: `python -m pip
> install --upgrade pip` then retry. If it persists, recreate the venv on Python
> 3.11/3.12 (`brew install python@3.12` → `python3.12 -m venv .venv`). pyobjc is
> only needed on macOS (it's how `pynput` and the AX/menu-bar layers talk to
> Cocoa).

**ruflo / claude-flow** (the MCP coordination layer this project uses). The
config — `CLAUDE.md` — **already ships in the repo**, so you only need the
*runtime*. From the repo root, run the same three commands as the project's
`CLAUDE.md` "Setup" section:

```bash
# The first word after "claude mcp add" is the SERVER NAME (a label you choose).
# Name it "ruflo" so it matches this project's CLAUDE.md (which calls the tools
# `ruflo`); the package behind it is @claude-flow/cli either way.
claude mcp add ruflo -- npx -y @claude-flow/cli@latest         # register (shows up as "ruflo")
npx @claude-flow/cli@latest daemon start                       # start the daemon
npx @claude-flow/cli@latest doctor --fix                       # health-check
claude mcp list                                                # verify "ruflo" is listed
```

> ⚠️ **Do NOT run `ruflo init` / `claude-flow init` in this repo** — it
> regenerates `CLAUDE.md` and would overwrite the project's customised version
> that just cloned with the code. You only re-init when starting a *brand-new*
> project.

ruflo is **optional** for building the Mac app — Claude Code + this repo is
enough on its own. It just adds the swarm / memory / hooks tooling the project's
`CLAUDE.md` describes (the MCP server appears as `ruflo`). If you originally
installed it a different way on Windows, use that same method here.

---

## 1. Principle: brain vs. hands

- **Brain — reuse as-is** (`src/vibeflow/core/`): the intelligence. No OS / GUI /
  audio / speech-engine deps (stdlib + `urllib` only).
- **Hands — write for macOS**: mic capture, the speech engine binding, text
  insertion, the trigger/hotkey, and the menu-bar UI.

The Windows "hands" already exist as the top-level modules in `src/vibeflow/`
(`app.py`, `hotkey.py`, `output.py`, `focus_detect.py`, `audio.py`,
`autostart.py`, the tray/overlay/notifier). Use each as the **reference
behaviour** for its Mac counterpart.

---

## 2. What ports unchanged (the brain)

| Module | Reuse | Notes |
|---|---|---|
| `core/curate` | ✅ as-is | deterministic cleanup / filler removal |
| `core/text` | ✅ as-is | helpers + snippet expansion |
| `core/ai_format` | ✅ as-is | talks to Ollama over HTTP — **Ollama runs on Mac**, no change |
| `core/vocabulary` | ✅ as-is | file-backed; uses `config_dir()` |
| `core/persona` | ✅ as-is | file-backed |
| `core/history` | ✅ as-is | local capped JSON + HTML viewer |
| `vibeflow.config` | ✅ as-is | already resolves XDG/`~/.config` paths on non-Windows |
| `core/appmode` | ⚠️ **partial** | the **resolver** (`resolve_outcome`, `AppIdentity`, outcomes, specificity, `starter_pack_rules`, `app_category`, `shadowed_by`, `EMAIL_TITLE_HINTS`) ports as-is. The **detection** (`target_app`, `foreground_hwnd`) is Win32 and returns an empty identity off-Windows, and the app **catalogs** (`_TERMINAL_EXES`, `_EDITOR_EXES`, `EMAIL_EXES`, `CHAT_EXES`, `_FRIENDLY`) hold Windows `.exe` names. See §4. |

`core/transcriber`? — `transcriber.py` is **not** in core (it's the engine
binding) but it's already cross-platform (`faster-whisper`). Reuse it directly;
see §5.

---

## 3. The macOS "hands" to build

Recommended stack: **Python + PyObjC + rumps** (maximises reuse — the whole brain
and `transcriber`/`audio`/`ai_format` are already Python). A native Swift app is
an option but throws away that reuse; only choose it if perf/UX demands it later.

| Layer | Windows file (reference) | macOS approach |
|---|---|---|
| **Menu-bar app + orchestration** | `app.py` (pystray tray + the `_process` pipeline) | **`rumps`** `NSStatusItem` menu-bar app. Keep the *exact* `_process` flow (transcribe → curate → per-app outcome → snippets → deliver → history → teach-back). |
| **Text insertion** | `output.py` (`pyperclip` + Ctrl+V / keystrokes) | Clipboard: `pyperclip` works (`pbcopy`/`pbpaste`). Paste: **Cmd+V** (not Ctrl+V) via `pynput` or Quartz `CGEventPost`. Keep the always-copy-then-paste design and the focus re-verify. |
| **Focus detection** ("is a text field focused?") | `focus_detect.py` (UIA / Win32) | **Accessibility API** via PyObjC: `AXUIElementCreateSystemWide()` → `kAXFocusedUIElementAttribute` → role in {`AXTextField`, `AXTextArea`, `AXComboBox`} and not read-only. Requires Accessibility permission. |
| **Foreground app identity** (`target_app`/`foreground_hwnd`) | inside `core/appmode` | `NSWorkspace.sharedWorkspace().frontmostApplication()` → `localizedName`, `bundleIdentifier`, `processIdentifier`. Build an `AppIdentity` from that. **Do not put this in core** — make a `vibeflow/<mac>/appdetect.py` that returns a `core.appmode.AppIdentity`. |
| **Hotkey / push-to-talk** | `hotkey.py` (`pynput` hold-combo + Win32 `DeliveryHotkey`) | `pynput` `keyboard.Listener` works on macOS (needs Input Monitoring + Accessibility). Pick a Mac-friendly PTT (e.g. hold **Right Cmd** or **Fn**). For the contextual delivery hotkey suppression, use pynput's **`darwin_intercept`** (the macOS analogue of `win32_event_filter`) — default key **Cmd+Shift+V**. |
| **Autostart** | `autostart.py` (registry Run key) | A **LaunchAgent**: write `~/Library/LaunchAgents/com.vibeflow.VibeFlow.plist` with `RunAtLoad`; `launchctl load`/`unload`. |
| **Notifications / overlay** | `notifier.py`, `overlay.py` | `rumps.notification(...)` (or `UNUserNotification`). Overlay: a small borderless floating `NSPanel`, or just menu-bar title/notification for v1. |
| **Single instance** | `single_instance.py` | A lock file in `config_dir()` or an `NSRunningApplication` check. |
| **Audio capture** | `audio.py` (`sounddevice`) | `sounddevice` works on macOS — reuse; needs Microphone permission. |

**Modifier conventions:** Windows Ctrl↔ macOS Cmd. Paste is **Cmd+V**; the
delivery hotkey is **Cmd+Shift+V**. The PTT default `ctrl+win` should map to a
Mac default (e.g. `cmd_r` hold). Make these the Mac config defaults.

---

## 4. Per-app formatting on macOS

The resolver is identical; supply Mac **data + detection**:

1. **Detection** — `vibeflow/<mac>/appdetect.py`: `target_app()` builds an
   `AppIdentity(exe=<bundle id or app name>, window_class="", title=<focused
   window title via AX>, protected=False)`. There is no "elevated process" notion
   on macOS; `protected` stays False (the safety fallback is unused on Mac).
2. **Catalogs** — provide Mac equivalents of the Windows catalogs (by **app name**
   or **bundle id** instead of `.exe`):
   - Terminals/verbatim: `Terminal`, `iTerm2`, `Warp`, `Alacritty`, `kitty`,
     `WezTerm`, and editors `Code`, `Xcode`, JetBrains apps, `Sublime Text`.
   - Email: `Mail` (`com.apple.mail`), `Microsoft Outlook`, `Spark`, `Airmail`;
     keep the browser-title hints (`gmail`, `outlook.com`, …) — they're OS-neutral.
   - Chat: `Slack`, `Microsoft Teams`, `Discord`, `WhatsApp`, `Telegram`,
     `Messages`.
   Cleanest: a small `mac_catalog.py` and a thin `resolve_outcome` wrapper that
   matches on app name/bundle id. (Longer term, consider splitting `core/appmode`
   into a pure `core/modes` resolver + per-platform detection+catalog — but don't
   do that as part of the first Mac milestone; keep core stable.)

---

## 5. Speech engine on macOS

- **Start with `faster-whisper`** (already in `requirements.txt`,
  `transcriber.py` unchanged): `ctranslate2` runs CPU/int8 on Apple Silicon and
  is plenty fast for `base`/`small`. Lowest-effort path to a working app.
- **Optimise later if needed** to **whisper.cpp + CoreML/Metal** (via
  `pywhispercpp`) for max speed/efficiency on M-series — swap only the
  `transcriber` binding; the pipeline is unchanged.
- **AI formatting**: `core/ai_format` already speaks to **Ollama** over HTTP, and
  Ollama runs natively on macOS — no change. (`ai.endpoint` stays
  `http://127.0.0.1:11434`.)

---

## 6. Permissions (macOS gates these; the app must guide the user)

Grant in **System Settings → Privacy & Security**:
- **Microphone** — to record.
- **Accessibility** — to read the focused element and inject keystrokes.
- **Input Monitoring** — for the global hotkey listener.

First-run UX: detect missing permissions and deep-link the user to the right
pane (`x-apple.systempreferences:com.apple.preference.security?Privacy_*`).

---

## 7. Project structure (monorepo, shared core)

```
src/vibeflow/
  core/                 # SHARED brain — untouched
  config.py             # shared (cross-platform paths)
  transcriber.py        # shared (faster-whisper)
  audio.py              # shared (sounddevice)
  app.py, hotkey.py, output.py, focus_detect.py, autostart.py, ...   # Windows hands
  <mac>/                # NEW: macOS hands  (e.g. `platform_mac/`)
    menubar.py          # rumps app + the _process orchestration
    output.py           # Cmd+V paste / typing / clipboard
    focus_detect.py     # AX focused-element role check
    appdetect.py        # NSWorkspace frontmost -> AppIdentity
    hotkey.py           # pynput PTT + darwin_intercept delivery hotkey
    autostart.py        # LaunchAgent plist
    catalog.py          # Mac app catalogs for per-app formatting
scripts/launch_mac.py   # entry point -> platform_mac.menubar:run
```
Work on a `macos` branch. Keep Windows-only deps (`pywin32`/`comtypes`) out of
the Mac import path (they're already lazy/guarded).

---

## 8. Packaging

- Build a `.app` with **py2app** (Mac-native) or **PyInstaller** `--windowed`.
- Bundle `faster-whisper`/`ctranslate2` like the Windows build does
  (`--collect-all`). The speech model still downloads to `~/.config/VibeFlow`
  (or `~/Library/Application Support/VibeFlow`) on first run — not bundled.
- **Distribution** needs a **Developer ID** signature + **notarization** (Apple
  Developer account) or users get Gatekeeper warnings. For development, an
  unsigned `.app` opens via right-click → Open.
- Auto-update: the Windows Inno-Setup/Redirection-Guard machinery is Windows-only.
  On Mac use **Sparkle** (the standard macOS auto-update framework) later.

---

## 9. Build sequence (milestones)

- **M0 — Console proof:** clone, venv, `pip install -r requirements.txt`, run a
  tiny script that records 3s from the mic and prints `transcriber` output. Proves
  audio + engine on the Mac.
- **M1 — Menu-bar shell:** a `rumps` app with a status item + Quit; wire the
  push-to-talk listener (pynput) to start/stop recording; on stop, run the full
  `core` pipeline and **copy the result to the clipboard** (skip insertion).
- **M2 — Type anywhere:** add focus detection (AX) + paste (Cmd+V) so it inserts
  in place, clipboard fallback otherwise. This is the killer feature working.
- **M3 — Parity menu:** port the tray menu (output mode, filler removal, per-app
  formatting toggle + Starter Pack, snippets via config, history open/clear,
  Personalized AI). Add Mac per-app detection + catalog (§4).
- **M4 — Polish:** delivery hotkey (`darwin_intercept`), autostart (LaunchAgent),
  first-run permission guidance, overlay/notifications.
- **M5 — Package:** `.app` bundle; (later) sign + notarize + Sparkle updates.

Keep tests green: the `core` tests run identically on macOS (`pytest -q`).

---

## 10. Hand-off

On the Mac, after cloning and setting up the venv, tell Claude Code:

> Build the macOS app per `docs/MACOS_PORT.md`, reusing `vibeflow.core`. Start at
> milestone **M0** and work up. Do **not** modify anything under
> `src/vibeflow/core/`. Keep `pytest -q` green.

That's everything needed to start with zero context loss.
