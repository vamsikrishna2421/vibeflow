# 📖 VibeFlow User Guide

Welcome! This guide is written for **everyone** — you don't need to be technical.
Take it step by step and you'll be dictating in a few minutes.

## Contents

- [What is VibeFlow?](#what-is-vibeflow)
- [Before you start](#before-you-start)
- [Installing VibeFlow](#installing-vibeflow)
- [Starting VibeFlow & the tray icon](#starting-vibeflow--the-tray-icon)
- [Your first dictation](#your-first-dictation)
- [Push-to-talk (hold to speak)](#push-to-talk-hold-to-speak)
- [Where your text goes](#where-your-text-goes)
- [Settings](#settings)
- [Changing the hotkey](#changing-the-hotkey)
- [Languages](#languages)
- [Tips for the best accuracy](#tips-for-the-best-accuracy)
- [Start VibeFlow automatically with Windows](#start-vibeflow-automatically-with-windows)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)
- [FAQ](#faq)

---

## What is VibeFlow?

VibeFlow lets you **type with your voice**. You press a keyboard shortcut, talk,
and your spoken words are turned into text and placed wherever you're working —
an email, a chat, a document, a web form. If you're not in a text box, the words
are copied to your clipboard so you can paste them yourself.

It does all of this **on your own computer**, with **no internet connection
required** after setup. Your voice and your words are never uploaded anywhere.

---

## Before you start

You need:

- A **Windows 10 or 11** computer.
- A working **microphone** (your laptop's built-in mic is fine).
- **Python 3.9 or newer** installed. This is a free, safe, one-time install:
  1. Go to <https://www.python.org/downloads/> and click the big **Download**
     button.
  2. Run the downloaded file.
  3. **Important:** on the first screen, tick the box **"Add python.exe to
     PATH"**, then click **Install Now**.
  4. When it finishes, close the window.

That's the only thing you install by hand. VibeFlow's installer handles
everything else.

---

## Installing VibeFlow

1. Open the **VibeFlow** folder (the one containing `Install-VibeFlow.bat`).
2. **Double-click `Install-VibeFlow.bat`.**
   - If Windows shows a blue *"Windows protected your PC"* box, click
     **More info → Run anyway**. (This appears for any new program; the script
     is plain text you can open and read.)
3. A black window opens and shows its progress:
   - `[1/4]` finds Python
   - `[2/4]` creates a private space for VibeFlow (a "virtual environment")
   - `[3/4]` installs VibeFlow and the pieces it needs
   - `[4/4]` downloads the speech model **(this one-time step needs internet)**
4. Wait until you see **"VibeFlow is installed!"**, then press **Enter** to
   close the window.

> 💡 The first install downloads a few hundred megabytes (the speech model and
> supporting libraries). After that, VibeFlow never needs the internet again.

---

## Starting VibeFlow & the tray icon

**Double-click `Start-VibeFlow.bat`.** Nothing obvious happens — that's normal!
VibeFlow runs quietly in the background. Look at the bottom-right of your screen,
near the clock, for a small **microphone icon** 🎙️.

> Don't see it? Click the little upward arrow (**˄**) near the clock to show
> hidden icons. You can drag VibeFlow's icon out so it's always visible.

The icon changes colour to tell you what's happening:

| Colour      | Meaning                                  |
|-------------|------------------------------------------|
| 🔵 **Blue** | Ready and waiting                        |
| 🔴 **Red**  | Listening to you right now               |
| 🟡 **Amber**| Thinking — turning your speech into text |

**Right-click** the icon any time for the menu (settings, trigger style, output
choice, and Quit).

---

## Your first dictation

VibeFlow starts in **Toggle** mode, which works like this:

1. Click inside any text box — try the search bar, a new email, or Notepad.
2. Press **`Ctrl + Alt + Space`**. You'll hear a short rising beep and the tray
   icon turns 🔴 red. VibeFlow is now listening.
3. Speak naturally: *"Hello, this is my first sentence with VibeFlow."*
4. Press **`Ctrl + Alt + Space`** again. You'll hear a falling beep; the icon
   turns 🟡 amber for a moment, then your text appears in the box. ✨

That's it! Press the shortcut, talk, press it again.

> 🗣️ You can speak punctuation: say *"comma"*, *"period"* (or *"full stop"*),
> *"question mark"*, *"new line"*, and the model will usually add it for you.

---

## Push-to-talk (hold to speak)

Prefer holding a key while you talk, like a walkie-talkie? Switch to
**Push-to-talk**:

1. Right-click the 🎙️ tray icon → **Trigger → Push-to-talk (hold key)**.
2. Now **press and hold the right Ctrl key**, speak, then **let go**. Your text
   appears when you release.

You can change which key to hold in [Settings](#settings) (`push_to_talk_key`).

---

## Where your text goes

VibeFlow is smart about where to put your words. By default (**Auto** mode):

- ✅ **If a text box is selected**, it **types** the text right there.
- 📋 **If no text box is selected**, it **copies** the text to your clipboard and
  shows a small pop-up like *"Copied to clipboard"*. Press **`Ctrl + V`** to
  paste it wherever you want.

This is exactly the behaviour you asked for: it writes into the text field when
there is one, and uses the clipboard when there isn't.

You can force a specific behaviour in the tray menu under **Output**:

- **Auto** — the smart behaviour above (recommended).
- **Always type** — always insert at the cursor.
- **Always clipboard** — always copy; you paste yourself.

---

## Settings

Open the tray menu → **Open settings file**. It opens a plain text file (YAML) in
your editor. Edit it, save, then choose **Reload settings** in the tray menu.

The file lives at: `C:\Users\<you>\AppData\Roaming\VibeFlow\config.yaml`

Here is every setting, explained simply:

### Speech model (`model`)
| Setting        | What it does | Options |
|----------------|--------------|---------|
| `size`         | Accuracy vs. speed of recognition | `tiny`, `base` *(default)*, `small`, `medium`, `large-v3` |
| `language`     | The language you speak | `auto` *(detect)*, or `en`, `es`, `fr`, `de`, `hi`, … |
| `device`       | Where it runs | `auto` *(use GPU if present)*, `cpu`, `cuda` |
| `compute_type` | Internal precision | `auto` *(recommended)* |

### Trigger (`hotkey`)
| Setting             | What it does | Options / examples |
|---------------------|--------------|--------------------|
| `mode`              | How you trigger it | `toggle` *(tap on/off)*, `push_to_talk` *(hold)* |
| `toggle_combo`      | The shortcut for toggle mode | `ctrl+alt+space`, `ctrl+shift+d`, `f9` |
| `push_to_talk_key`  | The key you hold in push-to-talk mode | `ctrl_r`, `alt_r`, `f8`, `caps_lock` |

### Output (`output`)
| Setting             | What it does | Options |
|---------------------|--------------|---------|
| `mode`              | Where text goes | `auto`, `type`, `clipboard` |
| `insertion`         | How it types | `paste` *(fast, reliable)*, `keystroke` |
| `restore_clipboard` | Put your old clipboard back after pasting | `true` / `false` |
| `trailing_space`    | Add a space after each dictation | `true` / `false` |
| `auto_fallback`     | In Auto mode, what to do when it's unsure a text box is focused | `clipboard` *(safe)*, `type` |

### Audio (`audio`)
| Setting        | What it does | Notes |
|----------------|--------------|-------|
| `sample_rate`  | Audio quality for the model | Leave at `16000` |
| `input_device` | Which microphone to use | `default`, or a name fragment / number from `--list-devices` |
| `min_seconds`  | Ignore ultra-short blips | Default `0.4` |
| `max_seconds`  | Safety cap per recording | Default `120` |

### Feedback (`feedback`)
| Setting         | What it does |
|-----------------|--------------|
| `sounds`        | Beep when recording starts/stops |
| `notifications` | Small pop-up messages |

### Text tidy-up (`text`)
| Setting                  | What it does |
|--------------------------|--------------|
| `strip`                  | Trim spaces around the result |
| `capitalize_first`       | Capitalise the first letter |
| `remove_trailing_period` | Remove a trailing `.` (handy for chat apps) |

---

## Changing the hotkey

Open the settings file and edit `toggle_combo` (or `push_to_talk_key`). Combine
keys with `+`. Some ideas:

```yaml
hotkey:
  mode: toggle
  toggle_combo: ctrl+shift+space     # try this if Ctrl+Alt+Space clashes
  # toggle_combo: f9                 # a single function key
  # toggle_combo: ctrl+alt+v
```

Key names you can use: `ctrl`, `alt`, `shift`, `cmd` (the Windows key), `space`,
`enter`, `tab`, `f1`–`f12`, single letters/numbers, and side-specific keys like
`ctrl_r`, `alt_r`, `shift_r`. Save the file, then **Reload settings**.

> If your chosen shortcut is already used by another app, pick a different one.

---

## Languages

By default `language: auto` lets VibeFlow detect what you're speaking. If you
always use one language, setting it explicitly is a little faster and more
accurate:

```yaml
model:
  language: en      # English. Use es, fr, de, hi, it, pt, ja, zh, …
```

The `base` model understands many languages. For the best results in non-English
languages, try `size: small` or `medium`.

---

## Tips for the best accuracy

- 🎤 **Get reasonably close to the mic** and speak at a normal, steady pace.
- 🤫 **Quieter rooms** help a lot.
- 🧠 **Use a bigger model** (`small` or `medium`) if your computer can handle it.
- 🌐 **Set your language** explicitly if you always speak the same one.
- 🗣️ **Speak in full phrases.** The model uses context, so a whole sentence comes
  out better than one word at a time.

---

## Start VibeFlow automatically with Windows

Want the 🎙️ icon to be there every time you turn on your PC?

1. Press **`Windows + R`**, type **`shell:startup`**, and press Enter. A folder
   opens.
2. **Right-click `Start-VibeFlow.bat`** (in the VibeFlow folder) → **Copy**.
3. In the Startup folder, **right-click → Paste shortcut**.

Now VibeFlow starts quietly whenever you sign in. (To stop this, delete the
shortcut from that Startup folder.)

---

## Troubleshooting

First, run the built-in check. Open the VibeFlow folder, then in the address bar
type `cmd` and press Enter to get a command window, and run:

```
scripts\run.ps1 --doctor
```

This prints your settings, lists your microphones, and confirms each piece is
installed.

| Problem | What's happening | Fix |
|--------|------------------|-----|
| **Nothing happens on the hotkey** | VibeFlow may not be running, or the shortcut clashes with another app | Check for the 🎙️ tray icon. If missing, run `Start-VibeFlow.bat`. Try a different `toggle_combo`. |
| **"No speech detected"** | The recording was too quiet or too short | Speak longer and closer to the mic. Confirm the right mic in `--doctor` / `--list-devices`. |
| **Text goes to clipboard, not the box** | VibeFlow couldn't confirm a text field was focused (it plays it safe) | Click *inside* the text field first. Or set `output: mode: type`. |
| **Wrong microphone is used** | The default device isn't the one you want | Set `audio: input_device:` to a name fragment or number from `--list-devices`. |
| **It's slow to transcribe** | The model is large for your CPU | Use `model: size: base` (or `tiny`). A short delay is normal on first use while the model loads. |
| **Beeps are annoying** | — | Set `feedback: sounds: false`. |
| **Install failed at "finding Python"** | Python isn't installed or wasn't added to PATH | Reinstall Python and tick *"Add python.exe to PATH"*. |
| **Accented/other-language words are off** | Model too small for that language | Try `size: small` or `medium`, and set `language` explicitly. |

Still stuck? See the [Developer Guide](DEVELOPERS.md) or run from a console with
`scripts\run.ps1` (instead of the `.bat`) to see detailed messages.

---

## Uninstalling

VibeFlow doesn't spread files across your system. To remove it:

1. **Quit** VibeFlow (tray icon → **Quit**).
2. **Delete the VibeFlow folder.**
3. *(Optional)* Delete your settings and downloaded model at
   `C:\Users\<you>\AppData\Roaming\VibeFlow`.
4. *(Optional)* If you added it to startup, delete the shortcut from
   `shell:startup`.

---

## FAQ

**Is my voice sent to the internet or any company?**
No. Recognition runs entirely on your computer. The only internet use is the
one-time model download during installation.

**Does it work with the internet off?**
Yes — that's the whole point. After installation you can disable Wi-Fi and it
keeps working.

**Which apps does it work in?**
Any app where you can type: browsers, Word, email, Slack/Teams/Discord, search
boxes, code editors, and more. If an app blocks simulated input, VibeFlow falls
back to the clipboard so you can paste.

**Can it run when I'm not looking / in the background?**
Yes. It sits in the tray and only listens while you hold/press the trigger.

**Does it listen all the time?**
No. It only records between you starting and stopping with the hotkey. The rest
of the time the microphone is not being recorded.

**Can I use it on my phone?**
Not this exact program — phones need a different kind of app. See the
[Mobile roadmap](DEVELOPERS.md#mobile-roadmap) for the options, including using
your phone keyboard's built-in offline dictation today.

**How do I make it more accurate?**
Use a larger model (`small`/`medium`), set your language, and speak clearly in a
quiet room. See [Tips](#tips-for-the-best-accuracy).

**Is it free?**
Yes. VibeFlow is open-source under the MIT license, and the speech models are
free to use.
