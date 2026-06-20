"""Benchmark Whisper speech-accuracy tiers (base / small / large-v3 / distil).

For each model and each hard audio clip: transcribe, measure latency, and
compute Word Error Rate (WER) against the known reference. Writes
asr_results.json + asr_results.md (with every transcription so you can see the
mistakes). Models cache into the VibeFlow models folder, so anything downloaded
here is reused by the app.

    python benchmarks/asr_bench.py
"""

import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")

# The 3 app tiers + distil-large-v3 (faster large) as a bonus.
MODELS = ["base", "small", "large-v3", "distil-large-v3"]
SIZE = {
    "base": "~150 MB", "small": "~500 MB",
    "large-v3": "~3 GB", "distil-large-v3": "~1.5 GB",
}


def _words(text: str):
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate via word-level Levenshtein distance."""
    r, h = _words(reference), _words(hypothesis)
    n, m = len(r), len(h)
    if n == 0:
        return 0.0 if m == 0 else 1.0
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m] / n


def _cases():
    with open(os.path.join(HERE, "asr_cases.json"), encoding="utf-8") as f:
        return json.load(f)


def _save(results):
    with open(os.path.join(HERE, "asr_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def _write_md(results):
    cases = _cases()
    lines = ["# VibeFlow speech-accuracy (Whisper) benchmark\n",
             "Hard sentences (numbers, acronyms, names, homophones, jargon) rendered "
             "as FAST TTS to stress the models.\n",
             "## Accuracy + speed summary\n",
             "| Model (tier) | Size | clips | avg WER | median WER | avg sec/clip |",
             "|---|---|---|---|---|---|"]
    tier = {"base": "Fast", "small": "Balanced", "large-v3": "Accurate",
            "distil-large-v3": "(bonus)"}
    for model, rows in results.items():
        wers = sorted(r["wer"] for r in rows if "wer" in r)
        secs = [r["seconds"] for r in rows if "seconds" in r]
        if not wers:
            lines.append(f"| {model} | {SIZE.get(model,'?')} | 0 | - | - | - |")
            continue
        avg = sum(wers) / len(wers)
        med = wers[len(wers) // 2]
        lines.append(
            f"| {model} ({tier.get(model,'')}) | {SIZE.get(model,'?')} | {len(wers)} | "
            f"{avg*100:.1f}% | {med*100:.1f}% | {sum(secs)/len(secs):.1f} |"
        )
    lines.append("\n_WER = Word Error Rate (lower is better). 0% = perfect._\n")
    lines.append("## Transcriptions by case\n")
    for case in cases:
        lines.append(f"### Case {case['id']}\n")
        lines.append(f"**Reference:** {case['text']}\n")
        for model, rows in results.items():
            row = next((r for r in rows if r["id"] == case["id"]), None)
            if not row:
                continue
            if "error" in row:
                lines.append(f"- **{model}** — ERROR: {row['error']}")
            else:
                lines.append(
                    f"- **{model}** (WER {row['wer']*100:.0f}%, {row['seconds']}s): "
                    f"{row['hyp']}"
                )
        lines.append("")
    with open(os.path.join(HERE, "asr_results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    from faster_whisper import WhisperModel

    try:
        from vibeflow.config import models_dir
        cache = str(models_dir())
    except Exception:
        cache = None

    cases = _cases()
    results = {}
    for model_name in MODELS:
        print(f"=== loading {model_name} ({SIZE.get(model_name)}) ===", flush=True)
        try:
            model = WhisperModel(
                model_name, device="cpu", compute_type="int8", download_root=cache
            )
        except Exception as exc:
            print(f"  load failed: {exc}", flush=True)
            results[model_name] = [{"id": c["id"], "error": str(exc)} for c in cases]
            _save(results)
            continue

        rows = []
        for case in cases:
            wav = os.path.join(AUDIO, f"{case['id']}.wav")
            if not os.path.exists(wav):
                continue
            t0 = time.time()
            try:
                segments, _info = model.transcribe(wav, language="en", beam_size=5)
                hyp = "".join(s.text for s in segments).strip()
                secs = time.time() - t0
                e = wer(case["text"], hyp)
                rows.append({"id": case["id"], "ref": case["text"], "hyp": hyp,
                             "wer": round(e, 3), "seconds": round(secs, 2)})
                print(f"  [{model_name}] case {case['id']:>2}: WER {e*100:4.0f}%  "
                      f"{secs:5.1f}s", flush=True)
            except Exception as exc:
                rows.append({"id": case["id"], "error": str(exc)})
                print(f"  [{model_name}] case {case['id']:>2}: ERROR {exc}", flush=True)
        results[model_name] = rows
        _save(results)
        _write_md(results)

    _write_md(results)
    print("DONE -> benchmarks/asr_results.json + asr_results.md", flush=True)


if __name__ == "__main__":
    main()
