# Changelog

All notable changes to VibeFlow are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project uses [Semantic Versioning](https://semver.org/).

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
