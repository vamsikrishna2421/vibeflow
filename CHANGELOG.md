# Changelog

All notable changes to VibeFlow are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project uses [Semantic Versioning](https://semver.org/).

## [1.4.2] — 2026-06-20

### Fixed
- **Teach-back now actually fires and learns correctly.** Two bugs: (1) the
  clipboard watcher cleared the remembered "last output" the moment it saw
  VibeFlow's own copy, so your correction had nothing to diff against; (2) the
  "safe frequency" learner read the *raw* transcript and therefore learned the
  *mistakes* (e.g. "CubeCTL") and biased Whisper toward them. The vocabulary now
  grows **only** from your verified corrections (teach-back) — never from raw
  output — and teach-back attempts are logged for transparency.

## [1.4.1] — 2026-06-20

### Added
- **Adaptive vocabulary** (`vocabulary.py`): VibeFlow learns your names/jargon and
  biases Whisper toward them (Whisper `initial_prompt`), so they transcribe
  correctly over time. Two learning signals:
  - **Teach-back** — when you edit VibeFlow's output and copy/cut the corrected
    text, it diffs old vs new and learns the *correct* spelling (deterministic, no
    LLM, never learns the mistake). Toggle in the tray: "Learn from my edits".
  - **Safe frequency** — recurring term-like words (CamelCase, ACRONYMs,
    identifiers, things with digits) from your dictations, with a gibberish gate.
  - Seed/edit terms via `text.vocabulary`; stored in `%APPDATA%\VibeFlow\
    vocabulary.json`.

### Changed
- Speech tiers trimmed to **Fast (base)** and **Balanced (small)**; large-v3 was
  dropped (impractical on CPU — see `benchmarks/asr_results.md`). The "Fast"
  options (base speech, qwen2.5:1.5b AI) are now marked **recommended**.

## [1.4.0] — 2026-06-20

### Added
- **Zero-touch local AI setup** (`ai_setup.py`). Pick an AI tier from the tray and
  VibeFlow does everything itself — finds or silently installs the Ollama runtime,
  starts its server, downloads the model with progress, and enables AI. No
  terminal, no manual steps. Also scriptable: `--setup-ai fast|balanced|best`.
- **AI model tiers**, chosen by a 20-case benchmark of 7 local models (see
  `benchmarks/`): Fast = `qwen2.5:1.5b` (1 GB), Balanced = `qwen2.5:3b` (2 GB),
  Best = `gemma2:2b` (1.6 GB). The default model is now `qwen2.5:1.5b`.
- **Speech-accuracy tiers** in the tray: Fast (`base`), Balanced (`small`),
  Accurate (`large-v3`) — to fix accent/pronunciation at the ASR layer (where it
  has to be fixed), not in the text model.
- The local-LLM benchmark harness and full results under `benchmarks/`.

### Changed
- The tray "AI formatting" control is now a managed tier picker
  (Off / Fast / Balanced / Best) instead of a plain on/off toggle.

## [1.3.0] — 2026-06-19

### Fixed
- **Packaged app now types into the focused text field (not only the clipboard).**
  The generated UI Automation wrapper wasn't in the bundle and couldn't be created
  in the read-only app folder, so focus detection failed and everything fell back
  to the clipboard. The wrapper is now bundled and code-generation is redirected
  to a writable folder.

### Changed
- **Output now always copies to the clipboard *and* pastes into the focused
  field.** The transcript is always left on your clipboard (paste it anywhere),
  and additionally inserted into the text box when one is focused.

### Added
- **Stage 4 — offline text curation** (`curate.py`): capitalises sentences, fixes
  the lone pronoun "i" → "I", tidies spacing/punctuation, and supports spoken
  layout commands ("new line", "new paragraph"). Configurable via `text.*`.
- **Optional local-LLM AI formatting** (`ai_format.py`): set `ai.enabled` (or use
  the tray "AI formatting (local LLM)" toggle) to have a local **Ollama** model
  rewrite dictation into clean prose — fully offline, **off by default**, and it
  silently falls back to plain text if no LLM is available. Test with `--check-ai`.

## [1.2.0] — 2026-06-19

### Added
- **On-screen status overlay (HUD).** A small pill near the bottom of the screen
  shows *"VibeFlow · Listening…"*, *"Transcribing…"*, *"Completed successfully"*,
  or *"Copied to clipboard"*, then auto-hides — so you don't have to watch the
  tray. It's a non-activating, click-through window, so it never steals keyboard
  focus from the field you're dictating into. Toggle via the tray ("Show
  on-screen status") or `feedback.overlay` in settings.

### Changed
- **Push-to-talk is the only trigger now** (toggle on/off is disabled for now to
  keep things simple). Default: **hold `Ctrl+Win`** to talk, release to
  transcribe. Push-to-talk now supports key *combos* (e.g. `ctrl+win`), not just
  single keys.

## [1.1.1] — 2026-06-19

### Fixed
- **Packaged app showed "Model failed to load."** The windowed `VibeFlow.exe`
  has no console, so `sys.stdout`/`sys.stderr` are `None`; libraries that wrote
  to them while loading the speech model crashed. Output is now routed to a log
  file and the streams are always valid.
- **Truly offline startup.** The model now loads from the local cache *without*
  contacting huggingface.co (only the very first run downloads it). Faster, and
  fully offline as intended.

### Added
- **File logging** at `%APPDATA%\VibeFlow\vibeflow.log` — makes the windowed app
  diagnosable (great for beta feedback: "send me your vibeflow.log").

## [1.1.0] — 2026-06-19

### Added
- **Single-instance lock** — only one VibeFlow can run at a time. Launching it
  again shows a friendly reminder and exits, instead of stacking a second tray
  icon. Fixes accidental double-starts.
- **Branded tray icon** — the VibeFlow logo replaces the plain microphone, with
  a small red/amber status dot for recording/transcribing.
- **"Start with Windows"** toggle in the tray menu (per-user; no admin needed).
- **Enterprise installer** — `scripts\build_installer.ps1` produces a single
  `VibeFlowSetup.exe` (Inno Setup) with a next-next-finish wizard, optional
  auto-start at login, a Start-Menu shortcut, and a proper uninstaller.
- **Branded executable** — `VibeFlow.exe` embeds the logo and version metadata,
  so Windows shows "VibeFlow" (e.g. *"Microphone in use by: VibeFlow"*) instead
  of "Python". An explicit AppUserModelID is set for notification/taskbar
  grouping.

### Changed
- Application state is now shown via the logo's status dot and the tray tooltip.

## [1.0.1] — 2026-06-19

### Changed
- Default **toggle** hotkey is now **Ctrl + Win** (the Windows key); previously
  `Ctrl + Alt + Space`.
- Default **push-to-talk** key remains **right Ctrl** (`ctrl_r`).

You can still set any combo you like in the settings file (`toggle_combo` /
`push_to_talk_key`) and choose *Reload settings* from the tray menu.

## [1.0.0] — 2026-06-19

First production release.

### Added
- **Offline speech-to-text** powered by `faster-whisper`. The model downloads
  once, then everything runs locally — no internet, accounts, or cloud.
- **Global hotkey trigger** with two styles: *toggle* (tap to start/stop) and
  *push-to-talk* (hold to speak).
- **Smart output routing**: types the transcript into the focused text field,
  or copies it to the clipboard when no text field is active. Powered by
  Windows UI Automation with a Win32 fallback.
- **System-tray app** with a colour-changing icon (blue/red/amber), trigger and
  output switches, and one-click access to settings.
- **Friendly settings file** (commented YAML) in `%APPDATA%\VibeFlow`.
- **Self-test** (`python -m vibeflow --doctor`) and device listing for easy
  troubleshooting.
- One-click Windows installer/launcher scripts and a PyInstaller build script
  for producing a standalone `VibeFlow.exe`.
- User Guide, Developer Guide, and mobile roadmap documentation.
- Unit tests for text cleanup, config merging, output routing, and hotkey
  parsing.
