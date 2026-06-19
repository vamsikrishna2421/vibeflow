# Changelog

All notable changes to VibeFlow are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project uses [Semantic Versioning](https://semver.org/).

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
