"""Benchmark VibeFlow's speech models on hard sentences (numbers, names, jargon).

Every model runs through VibeFlow's own Transcriber, so the results match the
app: Whisper with the vocabulary prompt and lead-in, Phonon-2 with its digit
clean-up. For each clip it records the Word Error Rate (WER) against the known
sentence and the transcription time. If the audio folder also holds long.wav +
long.txt (all sentences read in one go), it times that passage too, which shows
speed as a multiple of real time. Models load from the VibeFlow models folder,
so anything downloaded here is reused by the app.

    python benchmarks/asr_bench.py                       # phonon-2, small, medium
    python benchmarks/asr_bench.py --audio DIR phonon-2 medium

Make the clips first: gen_audio.ps1 on Windows, or macOS `say` (see asr_results.md).
Writes asr_results.json + asr_results.md next to this file.
"""

import argparse
import json
import os
import platform
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

DEFAULT_MODELS = ["phonon-2", "small", "medium"]
SIZE = {
    "phonon-2": "~160 MB", "phonon-2.5-en": "~160 MB", "base": "~150 MB",
    "small": "~500 MB", "medium": "~1.5 GB", "large-v3": "~3 GB",
    "distil-large-v3": "~1.5 GB",
}
LABEL = {
    "phonon-2": "Phonon-2", "phonon-2.5-en": "Phonon-2.5 English",
    "base": "Whisper base", "small": "Whisper small", "medium": "Whisper medium",
    "large-v3": "Whisper large-v3", "distil-large-v3": "Whisper distil",
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


def _audio(path):
    """16 kHz mono float32 (the app's input) from a 16-bit PCM WAV of any rate."""
    import wave

    import numpy as np

    with wave.open(path, "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    x = pcm.astype("float32") / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if rate != 16000:  # e.g. Windows text-to-speech writes 22.05 kHz
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(16000, rate)
        x = resample_poly(x, 16000 // g, rate // g).astype("float32")
    return x


def _machine() -> str:
    cpu = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        import subprocess

        try:
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True).stdout.strip() or cpu
        except Exception:
            pass
    return f"{cpu}, {os.cpu_count()} threads, {platform.system()}"


def _save(results):
    with open(os.path.join(HERE, "asr_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def _write_md(results, machine):
    cases = _cases()
    lines = [
        "# VibeFlow speech-accuracy benchmark\n",
        "Hard sentences (numbers, acronyms, names, homophones, jargon) rendered as "
        "fast text-to-speech in several accents, run through VibeFlow's own "
        f"Transcriber. Machine: {machine}.\n",
        "## Accuracy + speed summary\n",
        "| Model | Size | clips | avg WER | median WER | avg sec/clip | long passage |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, res in results.items():
        rows = res["clips"]
        wers = sorted(r["wer"] for r in rows if "wer" in r)
        secs = [r["seconds"] for r in rows if "seconds" in r]
        name = f"{LABEL.get(model, model)} ({model})"
        if not wers:
            lines.append(f"| {name} | {SIZE.get(model, '?')} | 0 | - | - | - | - |")
            continue
        long = res.get("long")
        long_txt = (f"{long['seconds']}s for {long['audio_s']}s, "
                    f"{long['realtime']}x realtime, WER {long['wer']*100:.1f}%") if long else "-"
        lines.append(
            f"| {name} | {SIZE.get(model, '?')} | {len(wers)} | "
            f"{sum(wers) / len(wers) * 100:.1f}% | {wers[len(wers) // 2] * 100:.1f}% | "
            f"{sum(secs) / len(secs):.2f} | {long_txt} |"
        )
    lines.append("\n_WER = Word Error Rate (lower is better). 0% = perfect. Formatting "
                 "counts: \"18.7%\" vs \"18.7 percent\" or \"4,500\" vs \"4500\" is an "
                 "error for every engine._\n")
    lines.append("## Transcriptions by case\n")
    for case in cases:
        lines.append(f"### Case {case['id']}\n")
        lines.append(f"**Reference:** {case['text']}\n")
        for model, res in results.items():
            row = next((r for r in res["clips"] if r["id"] == case["id"]), None)
            if not row:
                continue
            if "error" in row:
                lines.append(f"- **{model}** — ERROR: {row['error']}")
            else:
                lines.append(f"- **{model}** (WER {row['wer']*100:.0f}%, "
                             f"{row['seconds']}s): {row['hyp']}")
        lines.append("")
    with open(os.path.join(HERE, "asr_results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _bench_model(model_name, cases, audio_dir, models_dir):
    from vibeflow.core.vocabulary import Vocabulary
    from vibeflow.transcriber import Transcriber

    prompt = Vocabulary().prompt()  # the app's always-on starter vocabulary
    t = Transcriber(size=model_name, language="en", models_dir=models_dir,
                    fallback_size=None)  # measure the model asked for, never a fallback
    t0 = time.perf_counter()
    t.load()
    print(f"  loaded in {time.perf_counter() - t0:.1f}s", flush=True)
    rows = []
    for case in cases:
        wav = os.path.join(audio_dir, f"{case['id']}.wav")
        if not os.path.exists(wav):
            continue
        audio = _audio(wav)
        t1 = time.perf_counter()
        try:
            hyp = t.transcribe(audio, prompt=prompt).strip()
        except Exception as exc:  # noqa: BLE001 - record and keep going
            rows.append({"id": case["id"], "error": str(exc)})
            print(f"  [{model_name}] case {case['id']:>2}: ERROR {exc}", flush=True)
            continue
        secs = time.perf_counter() - t1
        e = wer(case["text"], hyp)
        rows.append({"id": case["id"], "ref": case["text"], "hyp": hyp,
                     "wer": round(e, 3), "seconds": round(secs, 2)})
        print(f"  [{model_name}] case {case['id']:>2}: WER {e*100:4.0f}%  {secs:5.2f}s",
              flush=True)
    result = {"clips": rows}
    long_wav, long_txt = (os.path.join(audio_dir, n) for n in ("long.wav", "long.txt"))
    if os.path.exists(long_wav) and os.path.exists(long_txt):
        audio = _audio(long_wav)
        with open(long_txt, encoding="utf-8") as f:
            ref = f.read()
        t1 = time.perf_counter()
        hyp = t.transcribe(audio, prompt=prompt)
        secs = time.perf_counter() - t1
        dur = len(audio) / 16000
        result["long"] = {"seconds": round(secs, 1), "audio_s": round(dur, 1),
                          "realtime": round(dur / secs, 1), "wer": round(wer(ref, hyp), 3)}
        print(f"  [{model_name}] long passage: {dur:.0f}s audio in {secs:.1f}s", flush=True)
    return result


def _run_one(model_name, audio_dir, out_path):
    """Benchmark one model in this process and write its result as JSON."""
    try:
        from vibeflow.config import models_dir
        cache = str(models_dir())
    except Exception:
        cache = None
    try:
        result = _bench_model(model_name, _cases(), audio_dir, cache)
    except Exception as exc:  # noqa: BLE001
        print(f"  load failed: {exc}", flush=True)
        result = {"clips": [{"id": c["id"], "error": str(exc)} for c in _cases()]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("models", nargs="*", default=DEFAULT_MODELS)
    p.add_argument("--audio", default=os.path.join(HERE, "audio"),
                   help="folder with <case id>.wav clips (and optional long.wav/long.txt)")
    p.add_argument("--one-out", help=argparse.SUPPRESS)  # internal: one model, JSON here
    args = p.parse_args()
    if args.one_out:
        _run_one(args.models[0], args.audio, args.one_out)
        return

    import subprocess
    import tempfile

    machine = _machine()
    results = {}
    for model_name in args.models:
        # Each model gets its own process: Phonon (PyTorch) and Whisper
        # (CTranslate2) can't share one, and it keeps the timings independent.
        print(f"=== {model_name} ({SIZE.get(model_name, '?')}) ===", flush=True)
        fd, out = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            subprocess.run([sys.executable, os.path.abspath(__file__), model_name,
                            "--audio", args.audio, "--one-out", out], check=False)
            with open(out, encoding="utf-8") as f:
                results[model_name] = json.load(f)
        except Exception as exc:  # noqa: BLE001 - e.g. the child crashed
            results[model_name] = {"clips": [{"id": c["id"], "error": str(exc)}
                                             for c in _cases()]}
        finally:
            os.remove(out)
        _save(results)
        _write_md(results, machine)
    print("DONE -> benchmarks/asr_results.json + asr_results.md", flush=True)


if __name__ == "__main__":
    main()
