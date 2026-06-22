# Changelog

All notable changes to VibeFlow are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project uses [Semantic Versioning](https://semver.org/).

## [1.17.0] — 2026-06-22

### Added
- **VibeFlow for Mac.** The macOS app is now real, and Windows and Mac ship their
  own releases from the same project. Each platform updates only to its own
  builds, so a Mac release will never be offered to your Windows PC (or the other
  way round).

### Changed
- **The Windows updater now follows the Windows release track.** It looks at every
  published release, keeps only the Windows ones (the new `win-…` builds and all
  the existing ones), and offers you the newest installer it can actually run. A
  Mac-only release can no longer leave the tray stuck on a "new version available"
  you'd have no way to install. Updates stay hands-free, exactly as before.



### Added
- **"Email" formatting outcome — dictate a note, get a real email.** When you
  dictate into an email app, VibeFlow now drafts a **proper email** — a brief
  greeting, your message stated clearly in your own first-person voice, and a
  polite closing/sign-off — instead of just polishing the wording. It won't
  invent recipients, names, or facts you didn't say. The one-click **Starter
  Pack** now points email apps at this: native apps (Outlook, Thunderbird…) by
  process, **and Gmail/Outlook in the browser by tab title** (so webmail works
  too, since the browser process alone is ambiguous). "Make it professional"
  stays available for polished-but-not-an-email contexts.
  - Note: if you set up smart formatting before this release, re-run **tray →
    Adapt formatting to each app → Set up smart formatting** to pick up the new
    email rules. (Needs AI formatting on.)

## [1.15.1] — 2026-06-21

### Internal
- **Extracted `vibeflow.core`** — the platform-agnostic "brain" (per-app
  formatting resolver, transcript cleanup/fillers, snippets, local-LLM
  formatting/tone/persona/teach-back, vocabulary, dictation history) now lives in
  its own dependency-free package, separated from the Windows-specific layers
  (hotkey, typing, focus detection, tray, audio). No user-facing change — this is
  the reusable foundation for the planned macOS / Android / iOS apps.

## [1.15.0] — 2026-06-21

### Added
- **Dedicated "Deliver here" hotkey — Ctrl+Shift+V.** Dictate with nothing
  focused (the text goes to your clipboard), then click into any app and press
  **Ctrl+Shift+V** to place it there, **restructured for that app** (the status
  shows *"Restructuring for Slack…"*). The hotkey is **contextual**: it only
  intercepts Ctrl+Shift+V for ~60 seconds after such a dictation — the rest of
  the time it stays out of the way and Ctrl+Shift+V works as your normal "paste
  without formatting." It also waits for you to release the keys before placing
  the text, so the held Ctrl+Shift can't corrupt it. (The tray's *Re-insert last
  dictation → Formatted for this app* still does the same thing.)

## [1.14.2] — 2026-06-21

### Changed
- **English-only for now; the language picker is removed.** The multilingual
  auto-detect was unreliable in the packaged build, so VibeFlow now defaults to
  **English** and the Language menus (tray + Settings) are gone. The root cause of
  the "transcription error" is fixed: a UI **label** ("Auto-detect") was reaching
  the engine as a language code; the transcriber now sanitises any
  empty/`auto`/unknown value to English so a bad setting can never crash
  transcription. (A valid language code set by hand in `config.yaml` still works.)

## [1.14.1] — 2026-06-21

### Fixed
- **Auto-detect language no longer hard-fails.** On some setups, choosing
  *Language → Auto-detect* could throw a "transcription error" even for plain
  English. VibeFlow now **falls back to English** if automatic detection fails,
  so dictation always works, and it **logs the real cause** to `vibeflow.log`
  (previously the error was swallowed) so the underlying multilingual detection
  issue can be pinned down and fixed properly.

## [1.14.0] — 2026-06-21

### Added
- **Settings window (stays open).** The tray's right-click menu is a native
  Windows menu that always closes after a single click — annoying when you want
  to flip several options. New **tray → "Settings (stays open)…"** opens one
  panel with the language picker, where-text-goes mode, and all the on/off
  switches (filler removal, per-app formatting, Personalized AI, learn-from-edits,
  save history, on-screen status, sounds, detailed logging, start-with-Windows).
  It stays open until you close it, and changes **apply live** — the running app
  watches `config.yaml` and re-applies within a second or two, no restart. (Speech
  accuracy and the AI tier remain in the tray since they download/reload a model.)

## [1.13.0] — 2026-06-21

### Added
- **Language picker.** A new tray **"Language"** menu lets you dictate in
  English, Spanish, French, German, Hindi, or **Auto-detect** (VibeFlow figures
  out the language each time). It takes effect immediately — the bundled
  base/small speech models are multilingual, so there's no download or restart.

## [1.12.0] — 2026-06-21

### Added
- **Searchable dictation history (opt-in).** Turn on **tray → Dictation history →
  "Save my dictations"** and VibeFlow keeps a local, capped log (most recent 500)
  of what you dictate. **"Open history…"** shows a clean, **searchable** page in
  your browser; **"Clear history"** wipes it. Off by default — nothing is stored
  until you enable it, everything stays on your PC, and you can clear it anytime
  (same privacy posture as VibeFlow's other learning features). Closes a gap vs.
  Wispr Flow, superwhisper and VoiceInk.

## [1.11.0] — 2026-06-21

### Added
- **Text snippets.** Say a short phrase and VibeFlow inserts canonical text for
  it — e.g. *"my email"* → your address, *"my address"* → your mailing address,
  *"sig"* → your signature block. Define them under `snippets:` in `config.yaml`
  (a point-and-click editor is on the roadmap). Matching is whole-phrase and
  case-insensitive, longer phrases win over shorter ones, and the replacement is
  inserted exactly as written. Empty by default, so it changes nothing until you
  add a snippet. (A common feature in Dragon and Wispr Flow that VibeFlow lacked.)

## [1.10.1] — 2026-06-21

### Added
- **Re-insert last dictation (recovery + deliver-anywhere).** New tray submenu
  under *Copy last transcript*: re-deliver your last dictation **exactly as
  spoken**, **cleaned up**, or **formatted for the app you're now in**. Two uses:
  (1) a one-tap fix when an app's automatic choice wasn't what you wanted — e.g.
  you dictated prose into a code editor (kept verbatim) and want it cleaned up,
  or AI reworded something and you want it back exactly as spoken; (2) **dictate
  with nothing focused, then click into any app and "Formatted for this app"** to
  place it there, restructured for that destination — the on-screen status shows
  *"Restructuring for Slack…"* while it works. (A dedicated delivery hotkey is on
  the roadmap; this tray action ships the capability safely today.)

## [1.10.0] — 2026-06-21

### Added
- **Per-app formatting — one-click Starter Pack.** A new tray submenu, **"Adapt
  formatting to each app,"** lets you turn the feature on/off and, with a single
  click (**"Set up smart formatting"**), have VibeFlow automatically make your
  **emails professional** (Outlook, Thunderbird…), keep your **chats casual**
  (Slack, Teams, WhatsApp, Discord…), and leave **terminals & code exactly as
  spoken** — no settings to learn. **"Clear my app rules"** undoes it instantly.
  Rules for apps you don't have simply never fire, and only the executable name
  is stored — never window titles.
- The first time you dictate into a recognised email or chat app, VibeFlow shows
  a one-time tip offering the Starter Pack (nothing changes until you accept it).

## [1.9.0] — 2026-06-21

### Added
- **Per-app formatting (foundation).** VibeFlow now adapts how it formats your
  dictation to the app you're speaking into. Out of the box, **terminals and
  code editors keep your words exactly as spoken** (so commands and code aren't
  reworded), while every other app formats as before. The on-screen status names
  the destination for every dictation — e.g. *"As spoken — Windows Terminal"* or
  *"Restructuring for Outlook…"* — so the behaviour is never a mystery. Toggle it
  any time via the tray's **"Adapt formatting to each app."**
  - Outcomes per app: *leave as spoken* / *make it professional* / *make it
    casual* (default = normal clean-up). Custom per-app rules are read from
    `config.yaml` now; a point-and-click manager and one-click Starter Pack land
    next.
  - **Safety:** an elevated/unidentifiable window (e.g. an administrator
    terminal) is always left exactly as spoken — never AI-rewritten. And VibeFlow
    re-checks the target window right before typing, so if your focus moves while
    it's transcribing, the text waits on your clipboard instead of landing in the
    wrong app. This design was reviewed and approved by four independent
    adversarial architecture reviews (safety, privacy, dev-tools, UX).

## [1.8.5] — 2026-06-20

### Fixed
- **Auto-update no longer breaks dictation — true root cause found and fixed.**
  After a silent update the speech model failed to load until a manual restart.
  It was never a file lock (1.8.2/1.8.3 lengthened a retry that could never have
  helped). The real cause: Inno Setup 6.3+ enables Windows' **Redirection Guard**
  process mitigation on the installer, and it is **inherited by every child
  process**. The relaunched VibeFlow therefore refused to traverse the symlink
  the Hugging Face cache uses for the model file (`model.bin` → blob), failing
  with `ERROR_UNTRUSTED_MOUNT_POINT` (WinError 448) — even though the file was
  perfectly readable by any normal process. The installer now relaunches VibeFlow
  via **Explorer**, so it runs in the normal shell context, outside the
  installer's mitigated process tree, and symlink traversal works exactly like a
  manual launch. Verified across repeated silent-update cycles.

## [1.8.3] — 2026-06-20

### Fixed
- **Auto-update reliably loads the speech model (real fix).** 1.8.2's retry was
  too short *and* too slow: right after a silent update, antivirus rescans the
  ~hundreds-of-MB model file for ~10s, and each retry wastefully fell through to
  a network reload, so only ~5 attempts fit in ~9s — about a second short, and
  the model stayed unloaded until a manual restart. The retry is now **offline-
  only** (each attempt is a fast local open, no network) and polls for up to
  **45 s**, comfortably outlasting the lock. The tray shows "Loading model…" and
  recovers on its own — no restart needed.

## [1.8.2] — 2026-06-20

### Fixed
- **Auto-update no longer leaves the speech model unloaded.** After a silent
  update relaunched the new version, the just-closed previous instance could
  still hold the model file open for a moment, so the model failed to load until
  a manual restart. The model load now retries for a couple of seconds, clearing
  that race — auto-updates are fully hands-free end to end (silent install, no
  close-error, no browser, no manual restart).

## [1.8.1] — 2026-06-20

### Fixed
- **Hands-free auto-update — for real this time.** The first auto-update had two
  rough edges, both fixed:
  1. **Installer couldn't close the tray app** ("Setup was unable to
     automatically close all applications"). VibeFlow has no main window, so
     Windows' Restart Manager couldn't close it. The installer now **force-closes
     VibeFlow before installing** (and **relaunches it** after a silent update).
  2. **Clicking "Install update" opened the browser** and required a manual
     download + click-through. Causes: the release asset was still uploading at
     check time (the app now **re-checks** before any page fallback), and the
     installer ran with its wizard (the updater now runs it **silently**). So
     "Install update" downloads and installs in the background and the app
     reappears — no browser, no Next-Next.

## [1.8.0] — 2026-06-20

### Added
- **Filler-word removal (opt-in) — done right, via a 4-architect design review.**
  Turn on "Remove filler words (um, uh)" in the tray to strip vocalized fillers.
  It's **tiered**: when AI formatting is on, the local LLM removes them
  *context-aware* (it keeps "er" in "metoprolol er", "uh-huh", etc. — things a
  regex can't); when AI is off, a conservative offline regex strips only the
  unambiguous standalone cases. **Off by default.** Your unedited text is always
  recoverable via the new tray **"Copy last transcript (unedited)"**, and an
  all-filler utterance is never silently dropped (your raw words are inserted).
  - The design was hardened through three rounds of adversarial review by four
    solution architects (fintech, healthcare, consumer-UX, dev-tools), which
    closed 2 blockers + 3 majors and steered the approach from regex-only to the
    tiered LLM+regex design (regex can't disambiguate er/ER, lists, mis-segments).

### Fixed
- Sentence capitalization no longer corrupts case-bearing tokens at a sentence
  start — **iOS, pH, eBay, tPA** are preserved (previously "iOS" → "IOS").
- Vocabulary/persona reload-on-change is now robust to edits that land within the
  same filesystem timestamp tick (compares size as well as mtime).

## [1.7.0] — 2026-06-20

Beta-readiness release.

### Added
- **Automatic updates.** VibeFlow checks GitHub for a newer release shortly after
  startup and offers **Install update** in the tray (plus **Check for updates**
  any time). Choosing it downloads that release's installer and runs it
  (`update_check.py`).
- **Report a problem…** in the tray — opens your VibeFlow folder (with
  `vibeflow.log`) and the GitHub issues page, so beta reports come with the log.
- **First-run guidance** — a one-time welcome + privacy note, and a clear
  *"downloading the speech model (~150 MB, once)"* message on a fresh machine.
- **Docs for testers/maintainers:** `docs/GETTING_STARTED.md` (install incl. the
  SmartScreen step, usage, privacy, updates, uninstall) and `docs/CODE_SIGNING.md`;
  an **optional code-signing step** in the build scripts (set `VIBEFLOW_PFX`); and
  a **CI workflow** that runs the test suite on every push.

### Changed
- **Default speech language is now English (`en`).** Auto-detect occasionally
  misfired on short clips; set `model.language` back to `auto` (or another code)
  any time.
- **Uninstall can fully clean up.** It now offers to also remove the local AI
  runtime (Ollama), all downloaded AI models (several GB), and your VibeFlow data
  — or keep them if you decline.
- The vocabulary and Personalized-AI windows are now **high-DPI aware** (crisp on
  scaled displays).

## [1.6.5] — 2026-06-20

### Fixed
- **AI formatting keeps your voice *and* your words.** Following the
  point-of-view bug, the 1.5b model was still rewriting first-person dictation
  into the second person ("I did…" → "You conducted…") and over-formalizing it.
  Three changes:
  1. The formatter prompt is now **conservative** — light cleanup only (no
     paraphrasing, rewording, or formalizing), at temperature 0.
  2. A **deterministic voice guard** rejects any AI output that drops your
     first-person voice and falls back to your plain (deterministically-curated)
     words — so a weak model can never change your point of view.
  3. The default AI-formatting model is now **qwen2.5:3b**, which keeps your
     exact words; `qwen2.5:1.5b` (faster but paraphrases) is no longer the
     recommended tier for formatting. The persona is scoped to terminology only.

## [1.6.4] — 2026-06-20

### Fixed
- **AI formatting now keeps your point of view.** With Personalized AI on, the
  model could rewrite your first-person dictation ("I checked…") into the third
  person about "the user" ("The user has seen…"), because the persona profile
  (phrased "The user is…") bled into the output's voice. The formatter now
  explicitly preserves the speaker's pronouns/voice, and the persona is used
  *only* to guide word choice and tone — never the point of view.

### Added
- **Opt-in detailed logging** (tray → "Detailed logging (troubleshooting)", or
  `text.debug_log`). When on, the raw transcript and your before/after correction
  text (truncated) are written to `vibeflow.log`, so a specific mis-hearing can
  be pinpointed. Off by default; it stores dictation snippets, so use it only
  while investigating.

## [1.6.3] — 2026-06-20

### Added
- **Interactive "Personalized AI" window.** Tray → Personalized AI ▸ "View my
  profile…" now opens a window instead of a text file: view and **edit** your
  writing profile, **Regenerate** it on demand from your recent dictation, see
  and **delete** the stored samples (full transparency/privacy), or **Forget
  everything**. Runs as its own process; the app reloads the profile when it
  changes (`Persona.reload_if_changed`).

## [1.6.2] — 2026-06-20

### Added
- **Interactive vocabulary window.** Tray → "My vocabulary…" now opens a real
  window with a checkbox per learned word — tick the ones to forget and click
  **Delete selected** (or **Add word…** to teach one directly). It runs as its
  own lightweight process so it never disturbs the tray app or your hotkey, and
  the running app applies the changes immediately. (The editable text-file list
  remains as an automatic fallback.)

### Changed
- **Personalized AI is ON by default.** Learning your style is a core VibeFlow
  feature, so it's enabled out of the box — it quietly builds a small, **local**
  profile of your domain and tone from your dictation and personalizes
  AI-formatted output. It's still a simple on/off in the tray ("Personalized AI
  ▸ Match my writing style"); turn it off anytime, and view or clear what it
  learned.

## [1.6.1] — 2026-06-20

### Fixed
- **The AI-formatting tray menu now updates immediately.** Picking a model tier
  really did turn AI formatting on (and saved it), but the menu kept showing
  "Off" because the tray menu wasn't being redrawn after the change — so it
  looked like the choice reverted. The menu is now refreshed (`update_menu()`)
  whenever settings change, so the selected AI tier and the other toggles always
  show their true state. Also added AI-setup logging for easier diagnosis.

## [1.6.0] — 2026-06-20

### Added
- **Personalized AI formatting (opt-in).** VibeFlow can learn your domain and
  tone from your own dictation and format text more like *you*. A local LLM
  periodically distils a short profile (e.g. *"DevOps/cloud background;
  professional, concise; uses terms like kubectl, Postgres"*) which is fed to the
  AI formatter so it keeps your voice and terminology. Turn it on under the tray
  "Personalized AI ▸ Match my writing style"; view it ("View my profile…") or
  reset it ("Forget my writing style") anytime.
  - **Private by design:** only a small, capped rolling window of recent
    transcripts is kept locally (`%APPDATA%\VibeFlow\persona.json`); nothing is
    uploaded, and the profile is regenerated on-device. Off by default; works
    alongside AI formatting.
  - New `persona.py` (sample window + profile state) and
    `ai_format.build_persona_profile`; config key `text.persona`.

## [1.5.3] — 2026-06-20

### Added
- **See and prune your vocabulary.** The tray menu now has
  "My vocabulary (N words)…" — it opens a clean, editable list of every word
  VibeFlow has learned. Delete a line to make it forget a word, add your own
  words to teach them directly, then save; changes apply automatically (no
  restart). Stored at `%APPDATA%\VibeFlow\my_vocabulary.txt`.

### Fixed
- **Dictation now types into terminals/consoles** — Windows Terminal,
  PowerShell/cmd, and CLI tools running in them. Terminals accept pasted input
  but don't expose an editable UI Automation field, so VibeFlow had been falling
  back to clipboard-only there (you had to paste manually). They're now detected
  by window class and typed into directly, like any other text field.

## [1.5.2] — 2026-06-20

### Fixed
- **Push-to-talk no longer mis-fires on plain Ctrl (e.g. Ctrl+C).** The Windows
  key often swallows its own key-release (it opens the Start menu), so `Win` got
  "stuck" in the internally-tracked held-keys set — after which any lone Ctrl
  press satisfied the Ctrl+Win combo and started a phantom recording ("Listening
  → Transcribing → no words found"). Those phantom recordings also hijacked the
  on-screen overlay, hiding the "Learned" confirmation. Push-to-talk now asks
  the OS for the **real, physical** key state (`GetAsyncKeyState`) at trigger
  time instead of trusting the tracked set, so a stuck/missed release can't
  cause a false trigger. With the phantom recordings gone, the "Learning…/
  Learned" pills display reliably.

## [1.5.1] — 2026-06-20

### Fixed
- **You can now actually *see* when VibeFlow learns.** The "Learned from your
  edit" confirmation only went to a Windows tray balloon, which Win10/11 quietly
  suppresses — so learning worked but felt invisible (it was firing several
  seconds late too, after the local model warmed up). The confirmation now shows
  on the **on-screen overlay** (the pill you already see for Listening/Completed):
  a live "Learning your terms…" pill while the model works, then
  "Learned: kubectl, Atlan, …" in green. The tray notification still fires as a
  secondary channel.

## [1.5.0] — 2026-06-20

### Added
- **AI-powered adaptive learning (opt-in).** When you fix a transcript and copy
  the whole corrected line, a **local** LLM reads it and pulls out the technical
  terms worth remembering (product names, tools, commands, jargon) — no need to
  select single words. Those terms then bias future transcription so they come
  out right. Picks the most accurate *installed* model (prefers `qwen2.5:3b`,
  which in testing nailed every term with zero false positives). The
  deterministic offline learner remains as a precise safety net, so nothing
  regresses when no LLM is present.
- **Optional at install, with full disclosure.** A new (unchecked) installer
  checkbox — and a tray toggle, "Adaptive learning (AI)" — turns it on. Both
  state the cost up front: one-time ~1.8 GB model download; ~2 GB RAM **only
  while learning** (freed when idle; it runs only when you edit and copy a
  transcript). Ticking the box sets the model up automatically on first run
  (zero-touch, with progress). Off by default.
- Config: `text.ai_learning` (opt-in flag) and `text.teach_back_model`
  (extraction model, default `qwen2.5:3b`).

### Changed
- Teach-back no longer needs single-word selection — **just copy the whole
  corrected text**. The LLM (or the offline learner) finds the terms for you.

## [1.4.4] — 2026-06-20

### Fixed
- **Teach-back now learns the right term — and nothing else.** The old
  positional diff mis-aligned sentences and learned *unchanged*/ordinary words
  (in the field it stored "the", "tool", and the fragment "alation" instead of
  the user's real term). Learning is now alignment-free: a word is learned only
  when it is **not already in our output** *and* it is either a real term
  (CamelCase / ACRONYM / has-digit / dotted) or the corrected spelling of a
  **similar-looking mistake** it replaced (e.g. `kubectl` ← `CubeCTL`,
  `Kubernetes` ← `Cubernetis`). Stop-words, fragments and ordinary words are
  ignored, so the vocabulary never fills with noise.

### Added
- **Single-word corrections.** You no longer have to copy the whole sentence —
  fix the one mis-heard term, select just that word, and copy it. VibeFlow
  recognises it as a correction of your last dictation and learns it.

## [1.4.3] — 2026-06-20

### Fixed
- Vocabulary is no longer saved on quit (only on each learn), so a stale/older
  instance can't overwrite good vocabulary with old data.

### Changed
- Added detailed **teach-back diagnostics** to `vibeflow.log` (output armed,
  clipboard changes, similarity ratio, learned terms) so the feature is fully
  observable while we validate it.

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
