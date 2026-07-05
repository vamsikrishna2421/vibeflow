# VibeFlow — Speech-to-Text (ASR) Strategy

_Reference for accuracy (esp. in noise) and near-instant latency, across all four
platforms. Compiled 2026-07 from a cross-repo audit + a 2025–2026 research sweep.
Treat cross-model WER as directional (different benchmarks), and re-verify the
"very recent" models' licenses before shipping._

---

## 1. The problem, per platform

| Platform | Engine today | Verdict |
|---|---|---|
| **iOS** | Apple `SFSpeechRecognizer` (on-device) | ✅ ~90% in real use — good |
| **Android** | Google `SpeechRecognizer` (online → on-device → Vosk); **diverts to on-device Whisper-small in noise** (`Settings.noiseModel="whisper"`) | ✅ great in quiet; ⚠️ noise path is Whisper-**small** (the ceiling of on-device) |
| **Desktop (Win/Mac)** | `faster-whisper`, default **`base`**, **batch after stop** (not streaming) | ❌ `base` is weak; ❌ latency ∝ clip length |

Two distinct problems, two distinct fixes:
- **Accuracy in noise** → a noise front-end + a stronger/right-sized model.
- **Perceived latency** → **streaming** (transcribe *during* speech).

Field data (Vamsi, fan on high): **Whisper-small beat Google-online AND the system
recognizer in heavy noise** — so the Android "divert to Whisper in noise" design is
*correct*; the lever is a *better* noise path, not switching back to Google.

---

## 2. What Wispr Flow actually does (and what we can copy)

Wispr is **cloud + proprietary** (doesn't work offline). Best-sourced picture — a
**pipeline**, not one model:
1. Cloud GPU inference (they name OpenAI + Meta cloud among processors).
2. **Dynamic per-language engine selection** — an *ensemble* of ASR backends; they claim >½ WER cut.
3. **Streaming** during speech → latency is *network*-bound (per their own docs) → "instant when you stop."
4. **LLM formatter** — fixes fillers/punctuation/false-starts, learns from your edits.

**We can copy 3 of the 4 without a cloud:** streaming (#3), a strong single model
(#2, on-device), and the LLM cleanup (#4 — **we already have the AI-polish layer**).
Only #1 (cloud GPU) we skip by design — **offline is our wedge** (Wispr can't do it).

---

## 3. Open-source model landscape (mobile · noise · streaming · license)

| Model | Size | ~EN WER | Streaming | On-device mobile | License | Commercial |
|---|---|---|---|---|---|---|
| **whisper.cpp** tiny/base/small | 39–244M | small ~8.6% | via chunking | ✅ (tiny/base near-RT) | MIT | ✅ |
| **faster-whisper** (CTranslate2) | = Whisper | = Whisper | chunking | desktop strong | MIT | ✅ |
| **distil-large-v3** | 756M | ~7.4% | chunking | borderline / desktop | MIT | ✅ |
| **large-v3-turbo** | 809M | ~7.4% | chunking (216× RTFx GPU) | desktop yes; mobile heavy | MIT | ✅ |
| **NVIDIA Parakeet-TDT 0.6B v3** | 600M | **~6.3%** (top) | native RNN-T (naive chunk → 12.8%) | GPU-oriented | CC-BY-4.0 | ✅ attrib. |
| **NVIDIA Canary 1B / Qwen-2.5B** | 1–2.5B | 7.1% / **5.6%** | mostly batch | ❌ GPU | CC-BY-4.0 | ✅ attrib. |
| **Moonshine v2** (Useful Sensors) | 27–245M | Med **6.65%** | ✅ streaming encoder | ✅ **built for edge** (~50–260 ms) | MIT code (⚠️ weights) | ✅ verify |
| **NVIDIA Nemotron 0.6B** (int4 0.67GB) | 600M | 8.2% | ✅ native | ✅ **7.2× RT on CPU** | via MS Foundry (⚠️) | ⚠️ verify |
| **Kyutai STT** (delayed streams) | 1–2.6B | ~Whisper | ✅ native | ❌ server/GPU | weights CC-BY-4.0 | ✅ attrib. |
| **Vosk / Kaldi** | ~50MB | ~20% worse | ✅ native, zero-latency | ✅ tiny CPU | Apache-2.0 | ✅ |
| **SeamlessM4T v2** | large | −56% vs Whisper-v2; **+38% noise** | streaming variant | ❌ GPU | CC-BY-**NC** | ❌ **avoid** |

**Standouts for us:** **Moonshine v2** (mobile streaming, edge-built) · **faster-whisper
turbo/distil** (safe MIT desktop) · **Parakeet** (max accuracy, GPU/cloud tier) ·
**Nemotron 0.6B** (best CPU-streaming *if* license clears). Avoid **SeamlessM4T**
(non-commercial) despite its noise strength.

---

## 4. Noise front-end (pairs *before* any ASR) — the fan fix

| Front-end | Real-time on phone? | Steady fan | CPU | License |
|---|---|---|---|---|
| **RNNoise** | ✅ | good (its sweet spot) | very low | BSD |
| **WebRTC APM** (HPF+NS+AGC) | ✅ (phone-call grade) | good; +gain/VAD | very low | BSD |
| **DeepFilterNet 3** | ✅ (<20 ms) | **best on variable noise** | low-mod | MIT/Apache |
| **Silero VAD** | ✅ (ONNX mobile) | (endpointing, not denoise) | very low | MIT |
| Meta Denoiser/Demucs | ⚠️ heavy | very high quality | high | MIT (code) |

**Recommended stack:** `WebRTC APM` **or** `RNNoise` (steady fan) **+ `Silero VAD`**
(endpointing); upgrade to **`DeepFilterNet3`** for variable noise (café/TV). All
commercial-safe. `RealTimeCutVAD` libs already bundle Silero VAD + WebRTC APM for
**both iOS and Android** — drops into the keyboard extension.

> ⚠️ Over-cleaning can *hurt* ASR (strips speech detail → mishears). It's an A/B tune.

**Bandpass note (Vamsi's idea):** keeping only ~80 Hz–8 kHz (like a phone line)
removes *out-of-band* noise (rumble/hiss) cheaply — but a fan is *broadband* and
overlaps the voice band, so bandpass alone can't remove it; that's what the
spectral/ML stages above are for. Both are worth stacking.

---

## 5. Latency — how "ready the instant you stop" works

The trick is **transcribe during speech**, so on release only a ~0.5 s tail remains.
Techniques: chunk+overlap · **LocalAgreement-n** (commit a prefix once N chunks
agree — turns Whisper into a stable streamer, ~3.3 s long-form latency) · native
RNN-T/TDT (Parakeet) · delayed-streams (Kyutai) · purpose-built streaming encoders
(Moonshine, Nemotron — near-zero batch→stream penalty).

**Reusable OSS:** `whisper_streaming` (UFAL, LocalAgreement ref) · `WhisperLive`
(Collabora) · `WhisperLiveKit` · faster-whisper chunking · NeMo cache-aware streaming.

**VibeFlow design rule:** VAD-gated streaming while the key is held → commit stable
prefixes → on release, flush the short tail + run the fast text-cleanup. Reproduces
Wispr's feel **without a cloud**.

---

## 6. Roadmap (biggest-bang-first)

- **Now:** desktop 5-model bake-off (base/small/medium/**turbo**/**distil**) + a runtime readout → pick the desktop model empirically. _(shipped: win-v1.22.2)_
- **Phase 1 — Noise front-end** (band-pass + spectral, offline). Cheapest, every platform, kills the fan. _(desktop: shipping win-v1.22.3)_
- **Phase 1b — Moonshine eval** in the desktop bake-off (validate the edge-streaming candidate).
- **Phase 2 — Streaming** (LocalAgreement) → the latency win, on-device.
- **Phase 3 — Mobile model upgrade**: Moonshine (or bigger on-device Whisper) in the Android noise path; add DeepFilterNet3 for variable noise.
- **Cross-cutting:** the AI-polish layer is already our #4 — keep leaning on it.
- **Optional Pro tier:** cloud Parakeet/Canary on GPU for max noise accuracy — but keep on-device the default (offline wedge).

## 7. License cheat-sheet
- ✅ **Permissive (ship freely):** whisper.cpp / faster-whisper / distil / turbo (MIT), RNNoise / WebRTC APM (BSD), DeepFilterNet (MIT/Apache), Silero VAD (MIT), Vosk (Apache-2.0), Moonshine *code* (MIT).
- ✅ **OK w/ attribution (CC-BY-4.0):** Parakeet, Canary, Kyutai STT weights.
- ❌ **Avoid:** SeamlessM4T (CC-BY-NC); some MMS/Silero-STT checkpoints (check each).
- ⚠️ **Verify before depending:** Moonshine *weights*; Nemotron-0.6B via MS Foundry Local.
