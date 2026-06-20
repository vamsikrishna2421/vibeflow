# VibeFlow — Getting Started (for beta testers)

VibeFlow turns your voice into text **anywhere** on Windows. Hold a hotkey,
speak, release — your words appear where your cursor is (or land on your
clipboard if there's no text box). Everything runs **on your PC**.

---

## 1. Install

1. Download **`VibeFlowSetup.exe`**.
2. Double-click it. Click **Next → Next → Finish**.

> **⚠️ "Windows protected your PC" / "Unknown publisher"?**
> VibeFlow isn't code-signed yet (it's a beta), so Windows SmartScreen may warn
> you. It's safe — click **More info → Run anyway**.

During setup you can tick:
- *Start VibeFlow automatically when I sign in* (recommended)
- *Enable adaptive vocabulary learning* (optional — uses a local AI model)

## 2. First launch

The **first time** it runs, VibeFlow downloads its speech model (~150 MB). This
happens **once** and needs internet. After that, dictation works **fully
offline**. You'll see *"Downloading speech model…"* then *"Ready."*

## 3. Use it

- **Hold `Ctrl` + `Windows` key**, speak, then **release**.
- Your text is typed where your cursor is — in a browser, document, chat, or a
  terminal. If no text field is focused, it's copied to your clipboard.
- A small pill at the bottom of the screen shows *Listening → Transcribing →
  Completed*.

## 4. Make it smarter (optional)

Right-click the **VibeFlow tray icon** (near the clock):

- **AI formatting** → pick a tier to have a local AI tidy your dictation.
  *Balanced (qwen2.5:3b)* is recommended — it keeps your exact words.
- **Personalized AI** → on by default; it quietly learns your domain and tone
  from your own dictation so formatting sounds like *you*. *View my profile…* or
  *Forget my writing style* any time.
- **My vocabulary…** → see, add, or remove the names and jargon it has learned.
- **Learn from my edits** → when you fix a transcript and copy the whole line,
  it learns the correct spelling.

## 5. Privacy

Everything stays on your computer — no account, no cloud. Personalized AI keeps a
small, capped sample of recent dictation **locally** to build your profile; you
can view or clear it from the tray at any time.

## 6. Updates

VibeFlow checks for new versions automatically and will offer **Install update**
in the tray. You can also choose **Check for updates** any time.

## 7. Something not working?

Tray → **Report a problem…**. It opens your VibeFlow folder — please attach
**`vibeflow.log`** to your report (it helps a lot). For a specific mis-hearing,
turn on **Detailed logging (troubleshooting)** first, reproduce it, then send the
log.

## 8. Uninstall

Uninstall *VibeFlow* from Windows "Add or remove programs". It will ask whether
to also remove the local AI runtime (Ollama), the downloaded AI models (several
GB), and your VibeFlow data — choose **Yes** for a full cleanup, or **No** to
keep them.
