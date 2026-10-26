# 🎙️ VibeFlow — Talk. It types.

**VibeFlow turns your voice into text anywhere on your computer.** Press a
keyboard shortcut, speak normally, and your words appear right where your cursor
is — in your email, a chat box, a document, a search bar, anywhere. If you're
*not* in a text box, VibeFlow quietly puts the text on your clipboard so you can
paste it wherever you like.

It runs **100% on your own machine**. No internet, no sign-up, no subscription,
nothing sent to the cloud. Your voice never leaves your computer.

> Think of it as your own private, offline version of tools like Wispr Flow.

---

## ✨ What it does

- 🔌 **Completely offline & private.** After a one-time setup, it works with your
  Wi-Fi turned off. Your audio is never uploaded anywhere.
- ⌨️ **Type anywhere with a hotkey.** Default: **`Ctrl + Win`** (hold Ctrl and tap the Windows key 🪟). Press
  once to start listening, press again to stop — your text is inserted instantly.
- 📋 **Smart clipboard fallback.** If no text field is selected, the text is
  copied to your clipboard automatically (with a little pop-up to tell you).
- 🖐️ **Two trigger styles.** *Toggle* (tap on/off) or *Push-to-talk* (hold a key
  while you speak) — your choice.
- 🌍 **Many languages.** Automatically detects your language, or lock it to one.
- 🪟 **Lives in your system tray.** The VibeFlow logo sits by the clock with a
  small **red** dot while listening and **amber** while it works.
- 🔒 **Just one, always.** Only a single VibeFlow runs at a time — no accidental
  duplicates if you click twice.
- 🚀 **Starts with Windows (optional).** Flip *Start with Windows* in the tray menu
  (or let the installer set it up) so it's always ready.

---

## ⬇️ Install in one click (easiest)

**[⬇️ Download VibeFlowSetup.exe](https://github.com/vamsikrishna2421/vibeflow/raw/main/installer/VibeFlowSetup.exe)**
(~70 MB) — then double-click it and click **Next → Next → Finish**.

- ✅ Installs **just for you** — no admin password needed.
- ✅ Optional **Start with Windows**; lives in the system tray with the VibeFlow logo.
- ✅ Windows shows *"Microphone in use by: **VibeFlow**"*.
- ✅ Only **one** VibeFlow ever runs at a time (no accidental duplicates).
- ✅ Clean **uninstall** any time via *Settings → Apps → VibeFlow*.

> On first launch, VibeFlow downloads the speech model once (about 160 MB),
> then runs **fully offline**. With the installer you don't need Python at all.

After installing, press **`Ctrl + Win`**, speak, then press it again — your words
appear wherever your cursor is. 🎉

---

## 🛠️ Run from source instead (developers)

> You need **Windows 10 or 11**, a **microphone**, and **Python 3.9+**
> ([download here](https://www.python.org/downloads/) — tick *"Add python.exe to
> PATH"* during install). That's the only prerequisite; the installer does the rest.

1. **Install** — double-click **`Install-VibeFlow.bat`**.
   A window opens and sets everything up automatically (a few minutes the first
   time, including a one-time model download). When it says *"VibeFlow is
   installed!"*, you're done.

2. **Start** — double-click **`Start-VibeFlow.bat`**.
   The VibeFlow logo appears near your clock (click the **^** to show hidden
   icons). That's VibeFlow running.

3. **Talk** — click into any text box, press **`Ctrl + Win`**, say a
   sentence, then press **`Ctrl + Win`** again. Your words appear. 🎉

👉 New to this? Read the **[Step-by-step User Guide](docs/USER_GUIDE.md)** — it's
written for everyone, with no jargon.

---

> 📦 **Want to hand VibeFlow to other people as one file?** Build a single
> **`VibeFlowSetup.exe`** (double-click → next → next → finish, with optional
> start-at-login and a clean uninstaller). It also makes Windows show
> *"Microphone in use by: VibeFlow"*. See
> [Developer Guide → Packaging](docs/DEVELOPERS.md#packaging--distribution-single-file-installer).

---

## 🧠 How it works (the 10-second version)

```
                You press the hotkey
                        │
                        ▼
        ┌───────────────────────────────┐
        │   VibeFlow records your voice  │   🎙️  (microphone)
        └───────────────┬───────────────┘
                        │  you press the hotkey again
                        ▼
        ┌───────────────────────────────┐
        │  Speech model turns it to text │   🧠  (runs on YOUR computer)
        └───────────────┬───────────────┘
                        ▼
            Is a text box selected?
            ├─ Yes →  ⌨️  types it right there
            └─ No  →  📋  copies it to your clipboard
```

Everything in that diagram happens **on your laptop**. Nothing is sent online.

---

## 🎚️ Choosing a speech model

VibeFlow runs its speech model on your own computer. Pick one any time from the
tray menu → **Speech model** (or `model: size:` in the settings file).

| Model                | Speed on an ordinary laptop | Good for                                    |
|----------------------|-----------------------------|---------------------------------------------|
| `phonon-2`           | ⚡⚡⚡ near-instant            | **Default.** English dictation on any PC    |
| `small` (Whisper)    | ⚡ a few seconds             | Other languages; the automatic fallback     |
| `medium` (Whisper)   | 🐢 slow without a GPU        | Rare jargon and names, if you can wait      |

**Phonon-2** (by Fermion Research, based on NVIDIA's Parakeet) is English only
and downloads once (about 160 MB). Its raw output spells most numbers out, so
VibeFlow writes them as digits for you ("503", "2.5 liters", "2:45 PM"). If
Phonon-2 can't run on a PC, VibeFlow uses Whisper automatically (`model: fallback:`).
Switching between Phonon-2 and Whisper restarts VibeFlow, because their engines
can't share one process. Measured results are in
[benchmarks/asr_results.md](benchmarks/asr_results.md).

---

## ⚙️ Settings, in plain English

Open the tray icon's menu and choose **"Open settings file"**. It's a plain text
file you can edit in Notepad. The most useful options:

- **Trigger style** — `toggle` (tap on/off) or `push_to_talk` (hold to talk).
- **The hotkey** — e.g. `ctrl+win`, or a hold key like `ctrl_r`.
- **Where text goes** — `auto` (smart), `type` (always type), or `clipboard`.
- **Language** — `auto`, or a code like `en`, `es`, `hi`, `fr`, `de`.

After editing, choose **"Reload settings"** in the tray menu. Full details are in
the [User Guide](docs/USER_GUIDE.md#settings).

---

## 🆘 Quick troubleshooting

| Problem | Try this |
|--------|----------|
| Nothing happens when I press the hotkey | Make sure the 🎙️ icon is in the tray. Run a check: open the project folder and run `scripts\run.ps1 --doctor`. |
| It typed nothing / "No speech detected" | Speak a little longer and closer to the mic. Check your microphone in `--doctor`. |
| Text went to the clipboard instead of typing | The app couldn't confirm a text box was selected (safe default). Click directly inside the text field first, or set output to `type`. |
| It's slow | Use a smaller model (`base` or `tiny`) in settings. |

More help: **[User Guide → Troubleshooting](docs/USER_GUIDE.md#troubleshooting)**.

---

## 🔒 Privacy

VibeFlow is built to be private by default:

- The speech model runs **locally** on your computer.
- **No audio or text is ever sent over the internet.**
- The only time it needs internet is the **one-time model download** during
  installation. After that, you can stay fully offline.

---

## 📱 What about mobile?

This package is a complete, production-ready **Windows desktop** tool. Phones use
a different kind of software that can't share this code directly, so a true
mobile app is a separate project. The realistic options (including using your
phone keyboard's built-in offline dictation today) are written up in
**[docs/DEVELOPERS.md → Mobile roadmap](docs/DEVELOPERS.md#mobile-roadmap)**.

---

## 📚 Documentation

- **[User Guide](docs/USER_GUIDE.md)** — for everyone: install, use, settings,
  troubleshooting, FAQ.
- **[Developer Guide](docs/DEVELOPERS.md)** — how it's built, how to run from
  source, build a `.exe`, run tests, and the mobile roadmap.
- **[Changelog](CHANGELOG.md)** — what's new.

---

## 🧰 For developers (the short version)

```bash
# From the project folder, with Python 3.9+
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"

python -m vibeflow --doctor    # check the setup
python -m vibeflow             # run the tray app
pytest                         # run the tests
```

Project layout: `src/vibeflow/` (the app), `tests/` (unit tests),
`scripts/` (install & build), `docs/` (guides).

---

## 📄 License

MIT — see [LICENSE](LICENSE). Speech recognition is provided by
[Phonon-2](https://huggingface.co/FermionResearch/Phonon-2) by Fermion Research
(CC BY 4.0, derived from NVIDIA's parakeet-tdt-0.6b-v3) through the
[fermion-research](https://github.com/fermionresearch/phonon) package, and by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) using OpenAI's
Whisper models. VibeFlow bundles none of these weights; they are downloaded from
their official sources on first use.
