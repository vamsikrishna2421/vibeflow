# VibeFlow — Competitive Analysis & Feature Backlog

_Snapshot: June 2026. Built from research across three market segments (AI/cloud
dictation, enterprise/accessibility, and OSS/offline). Treat star counts, prices
and "type-anywhere" claims as fast-moving — re-verify before quoting publicly._

## VibeFlow in one line
A **free, fully-offline, Windows** voice-to-text app that types **anywhere**,
**learns your jargon** (teach-back) and **personalizes formatting to your own
voice** with a **local** LLM — installable and self-updating for non-technical
users.

## Why that positioning is strong
- The **premium AI tier is cloud-only** (Wispr Flow, Aqua Voice) — VibeFlow's
  offline stance is a real differentiator.
- The **best offline/local tools skew Mac/Apple-Silicon** (superwhisper, VoiceInk,
  Dictato, Spokenly-local). On **Windows**, the offline-local field is thin
  (Handy, OpenWhispr, WhisperWriter) and mostly **lacks AI-cleanup polish**.
- So VibeFlow sits in a relatively **uncontested square: Windows + offline +
  local-LLM personalization + non-technical polish**.

---

## Comparison matrix (decision-relevant features)

Legend: ✅ yes · ⚠️ partial / basic · ❌ no

| Feature | **VibeFlow** | Wispr Flow | superwhisper | Dragon Pro | Win Voice Access | Handy (OSS) | VoiceInk (OSS) |
|---|---|---|---|---|---|---|---|
| Platform | Win | Win/Mac/iOS/Android | Mac/Win/iOS | Win | Win 11 | Win/Mac/Linux | Mac |
| Fully offline | ✅ | ❌ cloud | ⚠️ Mac only | ✅ | ✅ | ✅ | ✅ |
| Free | ✅ | ⚠️ freemium | ⚠️ freemium | ❌ $699 | ✅ | ✅ | ⚠️ |
| Type anywhere | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Clipboard fallback | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Local-LLM AI formatting | ✅ | ✅ (cloud) | ✅ | ❌ | ❌ | ⚠️ | ✅ |
| **Preserves your voice/POV** | ✅ (guarded) | ⚠️ | ⚠️ | n/a | n/a | n/a | ⚠️ |
| Personalized style learning | ✅ local persona | ✅ cloud | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |
| Self-learning vocab (teach-back) | ✅ | ⚠️ | ❌ | ⚠️ trains | ❌ | ❌ | ⚠️ dict |
| Custom vocabulary UI | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ | ✅ |
| **Per-app / per-task profiles ("Modes")** | ❌ | ⚠️ app-aware | ✅ signature | ❌ | ❌ | ❌ | ✅ Power Mode |
| **Filler-word removal (um/uh)** | ❌ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ⚠️ |
| **Text snippets / macros** | ❌ | ✅ | ⚠️ | ✅ | ❌ | ❌ | ❌ |
| Recording modes (PTT/toggle/VAD/hands-free) | ⚠️ PTT only | ✅ | ✅ | ✅ | ✅ | ✅ multi | ✅ |
| **Cancel-in-progress hotkey** | ❌ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Voice editing commands ("delete that") | ⚠️ new line/para | ✅ Command Mode | ⚠️ | ✅ Select-and-Say | ✅ | ❌ | ⚠️ |
| Multi-language / auto-detect | ⚠️ set lang | ✅ 100+ auto | ✅ | ✅ dialects | ✅ | ✅ auto (Parakeet) | ✅ |
| Alt engine (Parakeet, CPU-fast) | ❌ Whisper only | n/a | ❌ | proprietary | n/a | ✅ | ❌ |
| Searchable dictation history | ❌ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| On-screen status overlay | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ toggleable | ✅ |
| Zero-touch managed AI setup | ✅ | n/a | ⚠️ | n/a | n/a | ⚠️ manual | ⚠️ manual |
| Auto-update | ✅ | ✅ | ✅ | ⚠️ | ✅ (Windows) | ✅ | ✅ |
| Hands-free full OS control | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Cross-platform | ❌ Win only | ✅ | ⚠️ | ❌ | ❌ | ✅ | ❌ |

---

## ✅ Where VibeFlow is AHEAD (defend & market these)

1. **Offline + Windows + local-LLM personalization in one** — essentially no
   direct competitor occupies this exact square.
2. **Voice-preserving AI formatting** — we explicitly guard your first-person
   voice and exact words. Wispr/superwhisper/VoiceInk tend to over-polish; this
   is a genuine, demonstrable edge.
3. **Teach-back self-learning vocabulary** — learns the *right* spelling from your
   own corrections. Only a couple of niche OSS apps attempt this; ours is robust.
4. **Local persona profiling** — learns your domain/tone on-device. Wispr does
   style-learning but in the cloud; offline tools generally don't do it at all.
5. **Zero-touch managed local-LLM setup** — we install Ollama + the model for the
   user. OSS rivals make you do this by hand.
6. **Non-technical polish for an offline tool** — single installer, branded tray,
   auto-update, "Report a problem", view/clear windows. Most offline tools are
   developer-grade.

## ❌ Where VibeFlow is LAGGING (the backlog)

| Gap | Who has it | Value | Effort |
|---|---|---|---|
| **Per-app / per-task "Modes"** (formatting/tone/model per app) | superwhisper, VoiceInk, Wispr | ⭐⭐⭐ very high (segment-defining) | High |
| **Filler-word removal** (um, uh, like) | Wispr, Willow | ⭐⭐⭐ high, daily | **Low** |
| **More recording modes** — hands-free VAD auto start/stop | Whispering, Handy, all | ⭐⭐ high (table stakes) | Med |
| **Cancel-in-progress hotkey** | Handy, most | ⭐⭐ | **Low** |
| **Text snippets / phrases** ("my email" → expands) | Dragon, Wispr | ⭐⭐ | Med |
| **Voice editing/commands** ("scratch that", "select X") | Dragon, Voice Access, Wispr | ⭐⭐ | Med–High |
| **Searchable dictation history** | Wispr, superwhisper, VoiceInk | ⭐⭐ | Med |
| **Parakeet (NVIDIA) engine option** — fast CPU, auto-language | Handy, OpenWhispr | ⭐⭐ | Med |
| **Tone presets** (formal/casual quick toggle) | Wispr | ⭐ (we have persona) | Low |
| **"Notes → full passage" expansion mode** | Willow, Wispr | ⭐ niche | Med |
| **Multi-language + auto-switch** | most | ⭐⭐ (we just set EN default) | Med |
| Cross-platform (Mac/Linux), file transcription, full OS control | various | strategic, later | High |

---

## Recommended next features (ordered)

1. **Filler-word removal** — small, high daily value, fits our deterministic
   curation, on-by-default-able, and one of Wispr Flow's most-loved behaviors.
   Great first feature to ship through the new auto-update pipeline.
2. **Per-app "Modes"** — the strategic play; matches the segment's signature
   feature using our existing persona/AI-formatting plumbing (per-app override of
   tone/format/model). Bigger; do it as a focused follow-up.
3. **Cancel hotkey + hands-free VAD mode** — closes the "recording modes" gap
   cheaply.
4. **Text snippets** and **searchable history** — retention features.

_Research by three parallel agents (AI/cloud, enterprise/accessibility, OSS/offline);
full feature taxonomies and sources captured in the session transcript._
