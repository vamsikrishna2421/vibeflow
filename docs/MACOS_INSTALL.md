# VibeFlow for macOS — install & share

Two ways to get VibeFlow onto a Mac. **Option A** (share the `.app`) is best for
everyone; **Option B** (run from source) is best for developers.

The release build is **signed with a Developer ID and notarized by Apple**, so it
opens on any Mac with **no Gatekeeper warning** — just unzip and open. Everything
runs locally on the Mac (no internet, no account) except a one-time speech-model
download (~150 MB) on first use.

---

## Option A — Share the app bundle (`.app`)

### You (once): build, sign, notarize

```bash
# from the repo root, inside the venv — produces a signed + notarized build,
# installs it to ~/Applications, and refreshes the shareable zip on your Desktop
VIBEFLOW_NOTARIZE=1 ./scripts/build_mac_app.sh
```

This yields **`~/Desktop/VibeFlow-mac.zip`** — the file you share. (A plain
`./scripts/build_mac_app.sh` still signs but skips the few-minute notarization;
use that for quick local rebuilds.)

> The build signs into **`~/Applications`** (not the iCloud-synced Desktop) on
> purpose — iCloud re-tags framework folders with metadata that breaks
> `codesign --deep`. Signing + notarization credentials are already set up on this
> machine (a dedicated `build/signing` keychain + the `vibeflow-notary` profile);
> see `docs/MACOS_PORT.md` if they ever need recreating.

Send `VibeFlow-mac.zip` however you like (AirDrop, Drive, Slack, …).

### Them: install and first-run

1. **Unzip** `VibeFlow-mac.zip` and drag **VibeFlow.app** into **Applications**.
2. **Double-click to open.** It launches straight away — no warning, no
   right-click trick (it's notarized).
3. A **🎙 microphone** appears in the **menu bar** (there's no Dock icon — it's a
   menu-bar app). On first launch VibeFlow asks for two permissions:
   - **Microphone** — a prompt appears → click **Allow**.
   - **Accessibility** — VibeFlow opens System Settings → turn the **VibeFlow
     toggle ON**. (This is the one manual step macOS requires of *every* app of
     this kind — it can't be automated, by Apple's design.)
   VibeFlow detects the toggle automatically — **no quitting or reopening.** You'll
   see a "✓ Setup complete" pill.
4. **Use it:** hold **Right ⌘ (Command)** and speak; release to drop the text into
   whatever field is focused. If nothing is focused, it's copied to the clipboard —
   click into any app within ~60 s and press **⌘⇧V** to place it there.

> If you ever need to re-run setup, use the menu **🎙 → "Set Up VibeFlow
> (permissions)…"**.

---

## Option B — Run from source (developers)

```bash
# 1. Toolchain (once)
brew install python@3.12 git

# 2. Get the project
git clone https://github.com/vamsikrishna2421/vibeflow
cd vibeflow
git checkout macos

# 3. Environment
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip        # important: old pip tries to *compile*
                                            # pyobjc and fails; new pip grabs wheels
pip install -r requirements.txt

# 4. Run it
python scripts/launch_mac.py
```

Grant **Microphone** + **Accessibility** via the menu-bar **"Set Up VibeFlow"** item.

> **Dev-only quirk:** when launched from source, macOS attaches the
> Microphone / Accessibility grants to the **interpreter** (your
> `.venv/bin/python`, or the Terminal/IDE that started it) — not to "VibeFlow". So
> grant them to *that*. The packaged `.app` (Option A) has its own signed identity
> and is the clean path for real use.

First, prove the mic + engine work without any GUI:

```bash
python scripts/mac_proof.py --seconds 3      # records 3 s and prints the transcript
```

---

## What to tell users about privacy & permissions

- **Two permissions, once.** *Microphone* (to record) and *Accessibility* (to type
  into the focused field and detect which app it is, for per-app formatting). Both
  are standard for a dictation tool and revocable anytime in System Settings.
  Input Monitoring is **not** needed — Accessibility covers the hold-to-talk key.
- **Why the manual Accessibility toggle?** macOS forbids *any* app from granting
  itself Accessibility (anti-malware design). It's one toggle, one time — and
  because the app is signed, it **persists across updates** (no re-granting).
- **Offline:** audio is transcribed on-device with Whisper; nothing is uploaded.
  The only network use is the one-time model download on first launch.
- **Per-app formatting:** terminals & code editors get your words **verbatim**;
  turn on **menu → Adapt formatting → Set up smart formatting** to make email come
  out polished and chat stay casual.

## Notes

- **Architecture:** the build is Apple-Silicon (arm64). For Intel Macs, build on
  an Intel machine (or add a universal2 build later).
- **Auto-update:** not wired up yet. The standard macOS approach is **Sparkle**;
  a future enhancement.
- **Signing identity:** the release is signed/notarized under the Apple Developer
  account it was built with; distributing under a borrowed account ties the app to
  that account's identity.
