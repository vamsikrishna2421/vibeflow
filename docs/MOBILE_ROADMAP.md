# VibeFlow Mobile Roadmap — FINAL (merged with adversarial review)

> This version supersedes the proposed plan. Where the original plan was optimistic, this document says so plainly and adjusts architecture, sequence, effort, or scope. Every blocker and high-severity finding is resolved in-line; mediums/lows carry explicit mitigations. Facts below were verified against the repo (`src/vibeflow/core/`, `src/vibeflow/config.py`, `CHANGELOG.md`, git history) on 2026-06-22.

---

## 0. The two decisions that reshape everything (verified, not asserted)

Two of the reviewers' blockers are factually correct and change the *shape* of the roadmap, not just its numbers. Both were verified against the repo:

1. **The spec is in violent churn — DO NOT snapshot golden vectors yet.** Git shows a single author, 49 commits across **4 calendar days** (2026-06-19 → 06-22). `vibeflow.core` was extracted *yesterday* and the `email` appmode outcome — the single most product-differentiating piece — was added *today*. `appmode.resolve_outcome` is the fastest-changing code in the brain and the thing the plan most wants to port. Snapshotting golden vectors now encodes a spec that changes again next week, then maintained as a 3-way (Python/Swift/Kotlin) divergence against a moving target. **This is a hard gate, not a soft "when."**

2. **The team is one Python developer with zero shipped native-mobile code.** "Finished desktop" is Windows Python + a macOS pyobjc port. Production Kotlin `InputMethodService` (with NDK/JNI) and production Swift keyboard-extension work are **both greenfield**. The original "single-dev, 7-9 wk Android / 6-9 wk iOS" estimates implicitly price expert velocity in two unfamiliar toolchains. They are not credible as written.

**Consequence:** front-load a *spec-freeze gate* and a *ship-macOS-first* step (the cheap experiment before the expensive ones), re-baseline estimates with explicit learning-curve and store-review line items, and demote the iOS keyboard from "primary flow" to "only if a de-risking spike proves it." The brain is re-counted: **~1,497 lines total** in `core/` (curate 120, appmode 283, text 114, vocabulary 299, persona 128, ai_format 374, history 142) — not the "~430" the plan claimed. The v1-portable subset (curate + text + appmode) is ~520 lines, plus a hand-written per-platform app-detection catalog (~100-150 lines each) that golden vectors do **not** cover.

---

## 1. Recommended architecture — "Same brain, two native bodies, one private promise"

- **Native per platform** (Swift on iOS, Kotlin on Android) re-implementing the pure brain, validated against language-neutral **golden vectors** extracted from the pytest suite. On-device Whisper via **whisper.cpp** (the engine is already C++ — the one fact that drives everything).
- **Do NOT** port Python/faster-whisper to mobile; **do NOT** use Flutter/KMP for v1; **do NOT** run any cloud or Ollama LLM by default.

**Shared core:** the brain is 3× bigger than first claimed and will be maintained as **three hand-synced copies** (Python + Kotlin + Swift) through the highest-churn period. A Rust/C++ shared core is over-engineering *at v1*, but the decision is explicitly revisited at the macOS-sync checkpoint and before iOS (whisper.cpp already pays the FFI cost). The spec-freeze gate is what makes 3-way sync survivable.

**Per-platform detection catalog is real work** (not a free win). `appmode` is host-coupled; the macOS port already needed a 142-line `catalog.py`. Android needs a package-name catalog; iOS a bundle-ID/host-context catalog — **each gets its own task and test fixtures.**

### Speech engine per platform (ggml model sizes, corrected)

| Model | fp16 (.bin) | Q5 quantized | Desktop parity? |
|-------|-------------|--------------|-----------------|
| tiny  | ~75 MB      | ~31 MB       | below desktop |
| base  | ~142 MB     | ~57 MB       | **= desktop default** |
| small | ~466 MB     | ~180 MB      | best accuracy; flagship/≥4GB only |

- **Faithful "VibeFlow quality" = base default, small for high accuracy**, tiny = low-end fallback.
- **Android:** whisper.cpp (ggml, Q5) is the core engine, tiered by device class, push-to-talk/batch only (matches the desktop hold-release model). Android `SpeechRecognizer` = optional "lite" fallback.
- **iOS:** **default to whisper.cpp (base), NOT Apple SpeechTranscriber** — that's iOS-26-only and the `SFSpeechRecognizer` fallback can silently go to Apple's servers, breaking the offline promise. Apple Speech becomes an optional, OS-gated zero-download tier later.
- **CoreML/ANE is optional acceleration**, never the accuracy tier's dependency — must ship a working Metal/CPU-ggml fallback.

### AI formatting policy (decided): v1 = curate-only on both platforms
Ollama can't run on a phone; `ai_format.py` is unusable as-is. v1 = deterministic curate + per-app appmode formatting (exactly what desktop does when Ollama is absent). On-device LLM rewriting (llama.cpp ~1.5B Q4, or Apple Foundation Models) is a later **opt-in, device-class-aware "Pro"** add-on. **Never** silently send text to a cloud LLM.

### Positioning correction (important)
**iOS 26 ships on-device dictation in the OS** → "on-device transcription" is table stakes on iOS, not a differentiator. So: the offline wedge **survives on Android** (weak vendor STT) — why Android is first — but is **weak on iOS** (why iOS is gated). Everywhere, lead with what Apple Speech *can't* do: voice-preserving AI formatting, per-app Modes, teach-back vocabulary, persona.

---

## 2. Sequencing
**Spec-freeze gate → ship macOS → golden vectors → Android → (gated) iOS.**

1. **macOS ships first** — it reuses `core/` wholesale (CPython), so it's the near-zero-cost experiment that proves the extraction is clean and that the team can sustain even *two* builds before committing to four.
2. **Spec-freeze gate** — no public-behavior changes to `curate.py`/`appmode.py`/`text.py` for **4-6 consecutive weeks** before extracting golden vectors. The macOS-sync exercise is the instrument that measures it.

Android is first among re-implemented platforms (its IME maps ~1:1 onto the desktop press-speak-insert flow; Transcribro is a near-exact OSS reference). iOS is second **and gated**.

---

## 3. Phased milestones (HOW) — re-baselined (single Python dev, serial)

- **Phase G — Spec freeze + ship macOS** (predecessor/gating). Close pytest coverage gaps; pre-write privacy-policy/Data-Safety artifacts. Budget ≥4-6 wk freeze window.
- **Phase F — Golden vectors + cross-language CI harness — ~2-3 wk.** Input→expected JSON for curate/text/appmode; Unicode/locale adversarial cases (ICU vs java.util.regex vs Python `re`); CI green on a trivial Kotlin echo-impl before any real port.
- **Phase A0 — Android engine proof — ~1-2 wk.** whisper.cpp base via JNI/NDK; measure peak RSS on low/mid/flagship.
- **Phase A1 — Android IME, clipboard-only — ~2-3 wk.**
- **Phase A2 — Android "type anywhere" + per-app formatting — ~2-3 wk** (`commitText`; Kotlin appmode; Android detection catalog as its own task).
- **Phase A-LAT — latency/device-matrix — ~2 wk** (bar: p90 < 2.5s for a 15s utterance per tier).
- **Phase A-MDL — model delivery & tiering — ~2-3 wk** (CDN + manifest + resumable/integrity download + disk mgmt).
- **Phase A-A11Y — accessibility — ~1-2 wk** (TalkBack, Dynamic Type, contrast).
- **Phase A-SHIP — ship + store review — ~2-3 wk feature + 2-4 wk wall-clock review** (≥2 round-trips). **→ ANDROID v1 LIVE.**
- **Phase I-SPIKE — iOS handoff de-risking (GO/NO-GO) — ~1-2 wk.** Prototype keyboard→App Intent→containing-app→capture→App-Group→return→insert. **Kill criterion:** round-trip > ~1.5s, or unreliable auto-return, or >48MB keyboard-extension jetsam cap → **iOS keyboard concept is dead**; fall back to **Shortcuts/Action-Button** as the *primary* iOS entry (closer to the desktop one-gesture model, no Full-Access warning).
- **Phase I0 — iOS containing-app proof — ~1-2 wk** (whisper.cpp base, Swift brain; gate small+CoreML to ≥4GB; audit `SFSpeechRecognizer` server-fallback footgun).
- **Phase I-CML / I-KBD / I-MDL / I-LAT / I-A11Y / I-SHIP** — CoreML compile spike, keyboard+App-Group handoff (only if I-SPIKE=GO), model delivery, latency, accessibility, parity + store review (open-source the thin keyboard extension as a trust artifact). **→ iOS v1 LIVE** (or Shortcuts-only if NO-GO).
- **Phase P (optional) — opt-in on-device "Pro" AI formatting + v2 brain (vocab/persona) — ~3-4 wk.** Revisit the shared Rust/C++ core decision here.

---

## 4. Honest calendar (single Python dev, serial)

| Segment | Original | Re-baselined |
|---|---|---|
| Android learning curve (first Kotlin + NDK/JNI) | none | +2-3 wk |
| Android v1 (F + A0…A-SHIP) | ~7-9 wk | **~14-20 wk** |
| Android store review | none | +2-4 wk |
| iOS learning curve (first Swift + extensions) | none | +2-3 wk |
| iOS v1 (spike + I0…I-SHIP) | ~6-9 wk | **~14-22 wk** |
| iOS store review | none | +2-4 wk |

**Serial single-dev reality: ~7-9 months to Android v1, +~4-6 months to iOS — on the order of a year for both**, *after* macOS ships and the spec freezes. The original "13-18 weeks for both" assumed expertise and zero review/ramp/infra time. To hit the shorter numbers, staffing must change to **one experienced native dev per platform** (then iOS overlaps Android, +10-15% coordination overhead).

---

## 5. START TRIGGERS (WHEN)
1. **Spec frozen (HARD GATE):** no public-behavior change to curate/appmode/text for 4-6 weeks.
2. **macOS shipped and kept in sync with Windows** — cheap proof `core/` is truly portable.
3. **pytest core suite green & comprehensive** (golden-vector source).
4. **AI-formatting policy locked = curate-only for v1.**
5. **Business question answered** (Section 6) before the build question.
6. **Staffing named explicitly** — single-dev serial (long calendar) OR one native dev per platform. Apple/Google dev-program enrollment is a week-0 prerequisite (1-2 wk lead).
7. **Market timing:** the offline wedge is strongest on Android *now*; on iOS, OS-level dictation already eroded it — don't over-wait, don't rush past the freeze gate.

---

## 6. Open product decisions (resolve, don't defer)
- **D1 — Revenue bet or brand bet?** Persona + vocabulary are deferred to v2 and Pro AI is flagship-only/opt-in, so **at v1 there is nothing to charge for**. Either accept mobile as top-of-funnel/brand (resource it smaller, Android-only, ship-and-learn) OR pull a paywall-able feature (vocab teach-back or persona) into v1.
- **D2 — Opportunity cost vs desktop.** ~7-9 months of mobile (free, crowded, on-device-commoditized on iOS) vs the same months deepening the *uncontested* Windows-offline square (+macOS) with real users and code reuse. Mobile must beat that alternative to proceed.
- **D3 — iOS primary entry:** keyboard handoff vs Shortcuts — defer to the I-SPIKE go/no-go; pre-commit to the kill criterion.
- **D4 — Diagnostics with no telemetry.** "No data collected" removes the crash-analytics net; decide an opt-in local-logs story early (debugging two codebases blind is a hidden sink).
- **D5 — Live dictation expectation.** Batch push-to-talk matches the beloved desktop flow but may read as dated; frame it ("hold to talk, release to insert — like a walkie-talkie") and track adoption in early Android testing.

---

## 7. Top risks (full register in the workflow output)
- Spec churn poisons golden vectors → **spec-freeze gate** (blocker, resolved).
- Single dev, zero native experience → **+ramp, re-baselined calendar** (blocker, resolved).
- Store review under-modeled → **discrete 2-4 wk review milestone/platform** (blocker, resolved).
- iOS wedge commoditized by iOS 26 → **Android-first, iOS gated, reposition on formatting/Modes** (blocker, resolved).
- iOS keyboard 48MB cap + fragile handoff → **I-SPIKE go/no-go + Shortcuts fallback** (high, resolved).
- Containing-app RAM OOM on 3GB devices → **peak-RSS budget; gate small+CoreML to ≥4GB** (high, resolved).
- Nothing to monetize at v1 → **product decision D1** (high, must decide).
